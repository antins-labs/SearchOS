"""EvidenceExtractionMiddleware: automatic structured extraction from tool results.

After each open() call, a cheap judge model extracts
(entity, attribute, value, source, confidence) tuples from the page and
writes them to the evidence graph + coverage map. The search agent only
searches and reads; this middleware handles recording.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, Callable

from langchain.agents.middleware.types import AgentMiddleware

from searchos.harness.middleware._shared import extract_tool_name, unwrap_ai_message
from searchos.harness.middleware.extraction.prompts import (
    build_coverage_aware_row_prompt,
    build_discover_row_prompt,
    build_fill_row_prompt,
)
from searchos.harness.middleware.extraction.unit_normalize import normalize_value
from searchos.socm.strategy import record_source_antipattern
from searchos.socm import (
    SearchState,
    TableSchema,
)
logger = logging.getLogger(__name__)

# Values that mean "no value" when they are the WHOLE cell — never ingested as
# a finding. Includes bare missing-markers (a explore that fills "missing as '/'"
# must not create a filled cell, else coverage falsely hits 100% and the
# orchestrator skips searching). Matched on the full stripped value, so real
# values containing these chars ("2020/01/01", "Jean-Paul") are unaffected.
_NULL_VALUES = {"", "none", "null", "n/a", "/", "-", "–", "—", "--"}


def _provenance_fields(page_text: str, snippet: str) -> tuple[tuple[int, int] | None, str]:
    """Return (anchored span of snippet in page_text, sha1 text_hash).
    Tolerant matching — _extract_context collapses whitespace and judge
    excerpts arrive reflowed, so a raw find() never anchored in practice."""
    import hashlib

    from searchos.util.span_match import find_span

    if not snippet:
        return None, ""
    text_hash = f"sha1:{hashlib.sha1(snippet.encode('utf-8')).hexdigest()}"
    if not page_text:
        return None, text_hash
    span, _tier = find_span(page_text, snippet)
    return span, text_hash


def _anchored_excerpt(
    page_text: str, llm_excerpt: str, value: str, entity: str, attribute: str = "",
) -> tuple[str, tuple[int, int] | None, str]:
    """Excerpt to persist: the LLM-provided one if it anchors, else the
    harness-extracted context window when THAT anchors (LLM copies reflow
    or paraphrase too far to recover)."""
    excerpt = llm_excerpt or _extract_context(page_text, value, entity, attribute)
    span, text_hash = _provenance_fields(page_text, excerpt)
    if span is None and llm_excerpt:
        ctx = _extract_context(page_text, value, entity, attribute)
        if ctx:
            ctx_span, ctx_hash = _provenance_fields(page_text, ctx)
            if ctx_span is not None:
                return ctx, ctx_span, ctx_hash
    return excerpt, span, text_hash


def _fold_digits(s: str) -> str:
    """NFKC-fold and strip thousand separators so page and value numbers
    compare on digits alone ("673,622,371" == "673622371", full-width too)."""
    import unicodedata

    s = unicodedata.normalize("NFKC", s or "")
    return s.replace(",", "").replace("，", "")


def _ungrounded_number(page_text: str, value: str) -> str | None:
    """Reason string when a value's significant numbers are nowhere on the page.

    The zh_016 failure mode — one templated price ("全价票100元/人") stamped
    onto dozens of rows whose cited page is a name-list with no prices —
    satisfies every prompt-side rule but cannot satisfy this one. Only tokens
    of >=3 digits are checked: short tokens (day-of-month, list indexes,
    "3.5" split by the decimal point) false-positive; the observed
    fabrications are prices / counts / amounts. Values without such tokens
    pass (textual cells are governed by the excerpt rules instead)."""
    tokens = [t for t in re.findall(r"\d+", _fold_digits(value)) if len(t) >= 3]
    if not tokens:
        return None
    page = _fold_digits(page_text)
    missing = [t for t in tokens if t not in page]
    if missing:
        return "number_not_on_page:" + ",".join(missing[:3])
    return None


def _extract_context(page_text: str, value: str, entity: str, attribute: str = "", window: int = 120) -> str:
    """Return a short text window around the fact for offline verification.

    The window centers on the value occurrence NEAREST an entity mention, not
    the first one on the page: short generic values ("5A", "朝阳区",
    "9:00-18:00") recur across a page, and the first hit is routinely another
    entity's statement."""
    if not page_text:
        return ""
    haystack = page_text

    def _positions(needle: str) -> list[int]:
        if not needle or len(needle) < 2:
            return []
        pos = [m.start() for m in re.finditer(re.escape(needle), haystack)]
        if pos:
            return pos
        lowered = haystack.lower()
        return [m.start() for m in re.finditer(re.escape(needle.lower()), lowered)]

    def _window_at(idx: int, length: int) -> str:
        start = max(0, idx - window)
        end = min(len(haystack), idx + length + window)
        return " ".join(haystack[start:end].split())

    # Scraped pages carry a "Title: … URL Source: … Markdown Content:"
    # preamble; anything worth quoting is restated in the body, and viewers
    # strip the preamble — so prefer body occurrences when any exist.
    m = re.search(r"Markdown Content:\s*", haystack)
    body_start = m.end() if m else 0

    def _prefer_body(pos: list[int]) -> list[int]:
        body = [p for p in pos if p >= body_start]
        return body or pos

    val_pos = _prefer_body(_positions(value))
    ent_pos = _prefer_body(_positions(entity))
    if val_pos and ent_pos:
        idx = min(val_pos, key=lambda v: min(abs(v - e) for e in ent_pos))
        return _window_at(idx, len(value))
    if val_pos:
        return _window_at(val_pos[0], len(value))
    if ent_pos:
        return _window_at(ent_pos[0], len(entity))
    return ""


class EvidenceExtractionMiddleware(AgentMiddleware):
    """Intercepts search tool results and auto-extracts evidence."""

    name: str = "EvidenceExtractionMiddleware"

    @staticmethod
    def _add_nodes_and_fill_cells(state: SearchState, nodes: list[Any]) -> int:
        """Write new evidence and immediately project it into coverage cells.

        Live views poll ``search_state.json`` directly. If extraction only
        appends EvidenceNodes, the table stays stale until the sub-agent
        completion path runs a later fill pass. Keeping the projection in the
        same atomic update makes valid extracted evidence visible immediately.
        """
        added = []
        for node in nodes:
            if state.evidence_graph.add_node(node):
                added.append(node)
        if not added:
            return 0
        return state.coverage_map.fill_from_evidence(added)

    def __init__(
        self,
        judge_model: Any,
        workspace: Any,
        trajectory_logger: Any = None,
        batch_n: int = 5,
        alias_resolver_model: Any = None,
    ) -> None:
        self._judge = judge_model
        # Orphan-resolver model — used only for non-PK (findings-model) tables.
        self._alias_resolver = alias_resolver_model or judge_model
        self._workspace = workspace
        self._trajectory_logger = trajectory_logger
        self._extraction_count = 0

        # Node ids this instance committed. One instance per sub-agent, so it's
        # the authoritative per-agent extraction tally the completion report
        # reads instead of a concurrency-polluted global pre/post graph diff.
        self._added_node_ids: set[str] = set()

        self._extracted_content_hashes: set[str] = set()
        # hash → 失败重试次数；抽取失败（解析/judge 异常）时释放 hash 允许
        # 一次重试，达到上限后永久封锁（gisa#29：一次失败永久锁页）。
        self._hash_attempts: dict[str, int] = {}

        # batch_n is the buffer threshold that triggers a background flush
        # spawn — NOT a judge-call batch size. Per-page concurrency caps
        # actual judge calls via _flush_semaphore.
        self._batch_n = max(1, int(batch_n))
        self._pending_buffer: list[dict[str, Any]] = []
        from searchos.config.settings import settings as _settings
        self._flush_semaphore: asyncio.Semaphore = asyncio.Semaphore(
            max(1, int(_settings.extraction_flush_concurrency))
        )
        self._flush_tasks: set[asyncio.Task] = set()
        self._buffer_lock: asyncio.Lock = asyncio.Lock()
        # Serializes snapshot→extract→ingest per table so concurrent flushes
        # don't render stale snapshots and emit duplicate rows.
        self._table_flush_locks: dict[str, asyncio.Lock] = {}
        self._flush_in_flight_count: int = 0
        self._report_pending()

        self._pending_feedback: str = ""

    _EXTRACTABLE_TOOLS = {"open", "find"}

    async def await_pending_flushes(self, timeout: float = 5.0) -> int:
        """Block until in-flight background flushes complete (or timeout).
        Returns the number of tasks still pending. Best-effort: never raises."""
        if not self._flush_tasks:
            return 0
        pending = list(self._flush_tasks)
        try:
            done, still_pending = await asyncio.wait(pending, timeout=timeout)
        except Exception:
            logger.warning("await_pending_flushes: asyncio.wait raised", exc_info=True)
            return len(self._flush_tasks)
        if still_pending:
            logger.warning(
                "await_pending_flushes: %d/%d flush tasks still pending after %.1fs",
                len(still_pending), len(pending), timeout,
            )
        return len(still_pending)

    async def finalize(self, *, timeout: float = 30.0) -> int:
        """Drain extraction before the orchestrator computes this agent's
        report: await background flushes, then flush the residual buffer.
        Unlike await_pending_flushes (background tasks only) this also flushes
        the buffer — the loss point when an agent is interrupted mid-tool-call
        and never reaches a final turn. Idempotent / best-effort."""
        if self._flush_tasks:
            try:
                await asyncio.wait(list(self._flush_tasks), timeout=timeout)
            except Exception:  # noqa: BLE001
                logger.warning("finalize: asyncio.wait raised", exc_info=True)
        async with self._buffer_lock:
            snapshot = list(self._pending_buffer)
            self._pending_buffer.clear()
        self._report_pending()
        if snapshot:
            await self._flush_snapshot(snapshot, reason="finalize")
        return len(snapshot)

    def _spawn_background_flush(self, reason: str) -> None:
        """Fire-and-forget flush. Snapshot happens inside the task to keep
        awrap_tool_call sync and cheap; semaphore caps judge concurrency."""
        if not self._pending_buffer:
            return

        async def _run() -> None:
            async with self._buffer_lock:
                if not self._pending_buffer:
                    return
                snapshot = list(self._pending_buffer)
                self._pending_buffer.clear()
            snapshot_size = len(snapshot)
            self._flush_in_flight_count += snapshot_size
            self._report_pending()
            try:
                async with self._flush_semaphore:
                    await self._flush_snapshot(snapshot, reason=reason)
            except Exception:  # noqa: BLE001
                logger.warning(
                    "Background extraction flush failed (reason=%s)",
                    reason, exc_info=True,
                )
            finally:
                self._flush_in_flight_count -= snapshot_size
                self._report_pending()

        task = asyncio.create_task(_run())
        self._flush_tasks.add(task)
        task.add_done_callback(self._flush_tasks.discard)

    async def _extract_skill_now(
        self, item: dict[str, Any], source_url: str, *, reason: str,
    ) -> list[Any]:
        """Flush a SINGLE skill item synchronously and return the evidence nodes
        it added for this source. Synchronous (not fire-and-forget) because the
        agent's tool result is rebuilt from these nodes — it must wait for them.
        A skill result is already structured, so it extracts on its own, never
        diluted by page snapshots in a shared judge call. Bumps in-flight count
        for stall detection."""
        self._flush_in_flight_count += 1
        self._report_pending()
        try:
            pre = {n.id for n in self._workspace.load_state().evidence_graph.nodes}
            async with self._flush_semaphore:
                await self._flush_snapshot([item], reason=reason)
            nodes = self._workspace.load_state().evidence_graph.nodes
            return [n for n in nodes if n.id not in pre and n.source == source_url]
        except Exception:  # noqa: BLE001
            logger.warning(
                "Synchronous skill extraction failed (reason=%s)",
                reason, exc_info=True,
            )
            return []
        finally:
            self._flush_in_flight_count -= 1
            self._report_pending()

    def _report_pending(self) -> None:
        """Publish in-flight count (buffered + snapshotted-but-not-yet-written)
        so LoopSensor mode-5 doesn't declare stall mid-flush."""
        try:
            total = len(self._pending_buffer) + self._flush_in_flight_count
            self._workspace.report_extraction_pending(self, total)
        except Exception:  # noqa: BLE001
            pass

    async def awrap_tool_call(
        self,
        request: Any,
        handler: Callable,
    ) -> Any:
        result = await handler(request)

        tool_name = self._extract_tool_name(request)
        is_skill = tool_name.startswith("skill_")
        if tool_name not in self._EXTRACTABLE_TOOLS and not is_skill:
            return result

        content = self._get_result_content(result)
        if not content or len(content) < 50:
            return result

        state = self._workspace.load_state()
        schema = state.coverage_map.table_schema
        if not schema.attributes:
            return result

        if is_skill:
            # Skill tools return a JSON dict of already-structured data. Feed
            # it to the judge like any page, attributing evidence to the
            # skill's own ``url`` field (page-marker / extractability heuristics
            # don't apply to JSON, so they're skipped).
            extracted = self._skill_extraction_input(content)
            if extracted is None:
                return result
            content, source_url = extracted
            if not source_url:
                source_url = f"skill://{tool_name[len('skill_'):]}"
        else:
            from searchos.tools.simple_browser import FETCH_ERROR_SENTINEL
            if FETCH_ERROR_SENTINEL in content[:200]:
                src = self._extract_source_url(content) or "<unknown>"
                self._record_source_skip(src, "fetch_error")
                if self._trajectory_logger:
                    self._trajectory_logger._append_raw({
                        "type": "harness",
                        "kind": "extraction_skipped",
                        "reason": "fetch_error",
                        "source": src[:200],
                    })
                return result

            source_url = self._extract_source_url(content)
            if tool_name == "find" and source_url:
                source_url = source_url.split("/find?")[0]

            if not self._is_extractable_page(content):
                self._record_source_skip(source_url, "unextractable_page")
                if self._trajectory_logger:
                    self._trajectory_logger._append_raw({
                        "type": "harness",
                        "kind": "extraction_skipped",
                        "reason": "unextractable_page",
                        "source": source_url[:200],
                    })
                return result

        import hashlib as _hashlib
        content_hash = _hashlib.sha1(
            (content[:2000] or "").encode("utf-8", errors="ignore")
        ).hexdigest()
        # Check-then-set under buffer_lock so concurrent calls can't both
        # pass the 'not seen' check and double-extract.
        async with self._buffer_lock:
            if content_hash in self._extracted_content_hashes:
                if self._trajectory_logger:
                    self._trajectory_logger._append_raw({
                        "type": "harness",
                        "kind": "extraction_skipped",
                        "reason": "duplicate_content",
                        "source": source_url[:200],
                    })
                return result
            self._extracted_content_hashes.add(content_hash)

        item = {
            "content": content,
            "source_url": source_url,
            "content_hash": content_hash,
        }
        if is_skill:
            # Skill result → extract synchronously, then REPLACE the agent's
            # tool result with the stitched findings. The agent waits for the
            # judge; what it gets back is the structured extraction (with a
            # provenance header + "returned N / extracted M" so scope is clear),
            # not the raw payload. Empty extraction keeps the raw payload so the
            # agent is never handed nothing.
            added = await self._extract_skill_now(item, source_url, reason="skill_call")
            rendered = self._render_skill_findings_for_agent(content, added, source_url)
            if rendered is not None and hasattr(result, "content"):
                try:
                    result.content = rendered
                except (AttributeError, TypeError):
                    pass
        else:
            self._pending_buffer.append(item)
            self._report_pending()
            if len(self._pending_buffer) >= self._batch_n:
                self._spawn_background_flush("buffer_full")


        if self._pending_feedback:
            fb = self._pending_feedback
            self._pending_feedback = ""
            result = self._inject_feedback(result, fb)

        return result

    def _record_source_skip(self, source_url: str, reason: str) -> None:
        """Persist source-level skips as session anti-patterns."""
        try:
            record_source_antipattern(
                self._workspace,
                source_url,
                reason=reason,
                created_by="extraction",
            )
        except Exception:
            logger.debug(
                "strategy_log source write failed for %s",
                source_url[:100], exc_info=True,
            )

    async def awrap_model_call(
        self,
        request: Any,
        handler: Callable,
    ) -> Any:
        """End-of-turn: capture the sub-agent's final summary as a
        synthesized agent:// page, drain in-flight flushes, then flush
        the buffer synchronously so orchestrator sees full state."""
        response = await handler(request)

        is_final_turn = not self._response_has_tool_calls(response)
        if is_final_turn:
            if self._flush_tasks:
                try:
                    await asyncio.gather(
                        *list(self._flush_tasks),
                        return_exceptions=True,
                    )
                except Exception:  # noqa: BLE001
                    pass
            self._buffer_final_assistant_message(response)

        if not self._pending_buffer:
            return response

        if is_final_turn:
            await self._flush_pending(reason="sub_agent_final_turn")

        return response

    def _buffer_final_assistant_message(self, response: Any) -> None:
        """Add the sub-agent's terminal AI message to the extraction buffer
        as an ``agent://`` page; access-skill dispatcher skips this scheme."""
        msg = self._unwrap_ai_message(response)
        text = getattr(msg, "content", None)
        if isinstance(text, list):
            text = "\n".join(
                part.get("text", "") if isinstance(part, dict)
                else str(part)
                for part in text
            )
        text = (text or "").strip()
        if len(text) < 50:
            return

        agent_id = ""
        try:
            from searchos.tools.search_state import _current_agent_var
            agent_id = _current_agent_var.get() or ""
        except Exception:
            pass
        synthetic_url = f"agent://{agent_id or 'sub_agent'}/final_summary"

        self._pending_buffer.append({
            "content": text,
            "source_url": synthetic_url,
        })
        self._report_pending()
        if self._trajectory_logger:
            self._trajectory_logger._append_raw({
                "type": "harness",
                "kind": "final_message_buffered",
                "agent": agent_id,
                "chars": len(text),
            })

    # ---- extraction-input cleaning ------------------------------------

    @staticmethod
    def _strip_extraction_noise(text: str) -> str:
        """Strip the search-agent's render scaffolding (show_page header,
        L<N>: line prefixes, END OF PAGE footer). Markdown link sugar
        is left intact — regex strip breaks on URLs with escaped parens."""
        import re
        out: list[str] = []
        for line in text.split("\n"):
            stripped = line.lstrip()
            if (stripped.startswith("[Now viewing]")
                    or stripped.startswith("URL: ")
                    or stripped.startswith("**viewing lines")
                    or stripped.startswith("[END OF PAGE")):
                continue
            m = re.match(r"^L\d+:\s?", line)
            if m:
                line = line[m.end():]
            out.append(line)
        return "\n".join(out)

    def _prepare_extraction_pages(
        self, items: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Clean each item then merge items sharing a source_url.
        Sub-agents commonly open one long document at multiple viewports —
        sending each slice as a separate judge call triples cost for no
        gain. ``agent://`` items are never merged."""
        merged: dict[str, dict[str, Any]] = {}
        order: list[str] = []
        agent_items: list[dict[str, Any]] = []
        for it in items:
            url = it.get("source_url", "") or ""
            content = self._strip_extraction_noise(it.get("content", "") or "")
            hashes = [h for h in [it.get("content_hash", "")] if h]
            if url.startswith("agent://"):
                agent_items.append({
                    "source_url": url, "content": content,
                    "content_hashes": hashes,
                })
                continue
            if url not in merged:
                merged[url] = {
                    "source_url": url, "content": content,
                    "content_hashes": list(hashes),
                }
                order.append(url)
            else:
                merged[url]["content"] += (
                    "\n\n--- (next viewport on same page) ---\n\n" + content
                )
                merged[url]["content_hashes"].extend(hashes)
        return [merged[u] for u in order] + agent_items

    # ---- oversized-input segmentation ---------------------------------

    def _chunk_long_items(
        self, items: list[dict[str, Any]],
    ) -> list[list[dict[str, Any]]]:
        """Group flush items into judge-call chunks, splitting any item whose
        content exceeds the char budget (skill JSON payloads can be huge).

        Short items stay together as a single chunk, so when nothing is
        oversized this returns ``[items]`` — byte-for-byte the pre-split
        behavior. Each returned chunk is fed to one _run_row_judge call."""
        from searchos.config.settings import settings as _settings
        budget = max(1000, int(_settings.extraction_chunk_char_budget))
        if all(len(it.get("content", "") or "") <= budget for it in items):
            return [items]
        chunks: list[list[dict[str, Any]]] = []
        short: list[dict[str, Any]] = []
        for it in items:
            if len(it.get("content", "") or "") <= budget:
                short.append(it)
            else:
                chunks.extend([seg] for seg in self._split_oversized_item(it, budget))
        if short:
            chunks.append(short)
        return chunks or [items]

    def _split_oversized_item(
        self, item: dict[str, Any], budget: int,
    ) -> list[dict[str, Any]]:
        """Split one oversized item into budget-sized segments. Skill JSON →
        structure-aware split on its longest array field (each segment stays
        valid JSON with the top-level metadata preserved); anything else →
        overlapping char windows, each carrying the leading metadata header so
        later segments keep province/year/url context (a truncated skill JSON
        fails json.loads and lands here). Each segment inherits the source_url
        and the original item's content_hashes (settle stays keyed to the whole
        page)."""
        content = item.get("content", "") or ""
        url = item.get("source_url", "") or ""
        hashes = list(item.get("content_hashes") or [])
        segs = self._split_skill_json(content, budget)
        if segs is None:
            header = self._context_header(content, url)
            segs = self._split_by_chars(content, budget, header=header)
        if self._trajectory_logger and len(segs) > 1:
            self._trajectory_logger._append_raw({
                "type": "harness",
                "kind": "extraction_input_split",
                "source": url[:200],
                "orig_chars": len(content),
                "segments": len(segs),
            })
        return [
            {"source_url": url, "content": s, "content_hashes": hashes}
            for s in segs
        ]

    @staticmethod
    def _split_skill_json(content: str, budget: int) -> list[str] | None:
        """Structure-aware split of a skill JSON payload along its longest
        array field. Returns None when the content is not a JSON object with a
        splittable (len > 1) array — the caller then falls back to char windows.
        Never splits below one array element, so a segment can exceed budget if a
        single element is itself huge (still preferable to broken JSON)."""
        import json as _json
        if not content.lstrip().startswith("{"):
            return None
        try:
            data = _json.loads(content)
        except Exception:
            return None
        if not isinstance(data, dict):
            return None
        array_key = None
        best_len = 0
        for k, v in data.items():
            if isinstance(v, list) and len(v) > best_len:
                array_key, best_len = k, len(v)
        if array_key is None or best_len <= 1:
            return None
        rows = data[array_key]
        meta = {k: v for k, v in data.items() if k != array_key}
        base = len(_json.dumps(meta, ensure_ascii=False))
        segs: list[str] = []
        cur: list[Any] = []
        cur_len = 0
        for r in rows:
            rlen = len(_json.dumps(r, ensure_ascii=False)) + 1
            if cur and base + cur_len + rlen > budget:
                segs.append(_json.dumps({**meta, array_key: cur}, ensure_ascii=False))
                cur, cur_len = [], 0
            cur.append(r)
            cur_len += rlen
        if cur:
            segs.append(_json.dumps({**meta, array_key: cur}, ensure_ascii=False))
        return segs if len(segs) > 1 else None

    @staticmethod
    def _context_header(content: str, url: str) -> str:
        """Best-effort metadata header to prepend onto char-split segments.

        For a JSON-ish payload the top-level metadata precedes the first array,
        so everything up to the first ``[`` is the header (capped). Falls back
        to a source_url line. Empty when neither applies. Char segments are
        already invalid JSON, so this is context for the judge, not valid JSON.
        """
        s = content.lstrip()
        if s.startswith("{"):
            i = content.find("[")
            if 0 < i <= 2000:
                head = content[:i].rstrip().rstrip(",").rstrip()
                if head:
                    return head
        if url:
            return f'{{"source_url": "{url}"}}'
        return ""

    @staticmethod
    def _split_by_chars(content: str, budget: int, header: str = "") -> list[str]:
        """Fallback split into budget-sized windows, cutting on a newline near
        the window end when possible and overlapping segments slightly so a
        record straddling a cut survives in at least one segment. Every segment
        after the first is prefixed with ``header`` (the leading metadata) so it
        keeps province/year/url context — the head budget shrinks to compensate
        so a segment+header still fits."""
        from searchos.config.settings import settings as _settings
        overlap = max(0, int(getattr(_settings, "extraction_chunk_overlap_chars", 200)))
        n = len(content)
        if n <= budget:
            return [content]
        prefix = (header + "\n") if header else ""
        # Reserve room for the header on non-first segments; never let the body
        # budget collapse below a sane floor.
        body_budget = max(1000, budget - len(prefix))
        segs: list[str] = []
        start = 0
        while start < n:
            end = min(n, start + body_budget)
            if end < n:
                nl = content.rfind("\n", start + int(body_budget * 0.9), end)
                if nl > start:
                    end = nl
            body = content[start:end]
            segs.append(body if not segs else prefix + body)
            if end >= n:
                break
            start = max(end - overlap, start + 1)
        return segs

    async def _flush_pending(self, *, reason: str) -> None:
        """Synchronous final-turn flush. Background path uses
        _spawn_background_flush which snapshots inside the task body."""
        async with self._buffer_lock:
            if not self._pending_buffer:
                return
            snapshot = list(self._pending_buffer)
            self._pending_buffer.clear()
        self._report_pending()
        await self._flush_snapshot(snapshot, reason=reason)

    async def _flush_snapshot(
        self,
        snapshot: list[dict[str, Any]],
        *,
        reason: str,
    ) -> None:
        """Extract a buffer snapshot via per-page concurrent judge calls.
        Caller owns the snapshot; this method must NOT touch _pending_buffer."""
        if not snapshot:
            return

        items = self._prepare_extraction_pages(snapshot)

        state = self._workspace.load_state()
        # Multi-table routing via target_table context var.
        try:
            from searchos.tools.search_state import _current_table_var
            target_tid = _current_table_var.get()
        except Exception:
            target_tid = ""
        if target_tid and target_tid in state.coverage_map.tables:
            schema = state.coverage_map.tables[target_tid]
        else:
            schema = state.coverage_map.table_schema
        if not schema.attributes:
            # No schema yet (explore). Stash agent:// summaries for
            # create_schema to replay post-commit.
            agent_items = [
                {
                    "source_url": it.get("source_url", "") or "",
                    "content": it.get("content", "") or "",
                }
                for it in items
                if (it.get("source_url", "") or "").startswith("agent://")
            ]
            if agent_items:
                def _stash(s: Any) -> Any:
                    s.pending_agent_summaries.extend(agent_items)
                    return s
                self._workspace.atomic_update_state(_stash)
                if self._trajectory_logger:
                    self._trajectory_logger._append_raw({
                        "type": "harness",
                        "kind": "pending_summary_stashed",
                        "count": len(agent_items),
                        "reason": reason,
                    })
            return

        if self._trajectory_logger:
            self._trajectory_logger._append_raw({
                "type": "harness",
                "kind": "extraction_flush",
                "reason": reason,
                "items": len(items),
            })

        pre_evidence_ids = {n.id for n in state.evidence_graph.nodes}

        if getattr(schema, "primary_key", None):
            await self._extract_and_ingest_table(items, schema.table_id)
            backfill = self._related_backfill_tables(state, schema.table_id)
            if backfill and self._trajectory_logger:
                self._trajectory_logger._append_raw({
                    "type": "harness",
                    "kind": "cross_table_backfill",
                    "target_table": schema.table_id,
                    "backfill_tables": backfill,
                    "items": len(items),
                })
            for rel_tid in backfill:
                await self._extract_and_ingest_table(items, rel_tid)

        self._pending_feedback = self._build_feedback(pre_evidence_ids)

    @staticmethod
    def _related_backfill_tables(state: Any, tid: str) -> list[str]:
        """Relation-linked tables to extract from the same pages as ``tid``
        — a table the orchestrator never targets still gets fed (its rows
        grow via discover-mode / orphan promotion). Runs for the whole
        session regardless of how filled the linked table is: pages keep
        carrying cross-table facts after the row set stabilizes, and the
        ingest-time dedup absorbs re-extraction of known values."""
        from searchos.config.settings import settings as _settings

        if not _settings.extraction_cross_table_backfill or not tid:
            return []
        cmap = state.coverage_map
        linked: list[str] = []
        for rel in cmap.relations:
            other = ""
            if rel.from_table == tid:
                other = rel.foreign_key.target_table
            elif rel.foreign_key.target_table == tid:
                other = rel.from_table
            if other and other != tid and other not in linked:
                linked.append(other)
        return [
            other for other in linked
            if (schema := cmap.tables.get(other)) is not None
            and schema.attributes and schema.primary_key
        ]

    # ---- Coverage-aware row path (extraction + fill) -----------------------

    @staticmethod
    def _render_coverage_snapshot_via_view(tid: str, state: Any) -> str:
        from searchos.socm.views import SearchStateSnapshot
        from searchos.socm.views import render_extraction_snapshot
        snap = SearchStateSnapshot.from_state(state)
        return render_extraction_snapshot(snap, tid)

    def _table_lock(self, tid: str) -> asyncio.Lock:
        lock = self._table_flush_locks.get(tid)
        if lock is None:
            lock = asyncio.Lock()
            self._table_flush_locks[tid] = lock
        return lock

    @staticmethod
    def _plan_judge_calls(tid: str, state: Any) -> list[tuple[str, str]]:
        """Decide which judge calls this flush makes: list of (mode, view).

        Dual mode splits the merged coverage-aware prompt into two
        single-purpose calls that BOTH run on every flush — FILL
        (incomplete-row view only, fill MISSING) and DISCOVER (PK
        inventory only, new rows only). The merged snapshot is a
        "待填表单" that under load induces the judge to copy a nearby
        visible value into a listed row; each split prompt can carry
        hard counter-rules instead. The FILL call is dropped whenever
        there is nothing to fill — an empty table, or every existing
        row already has all its cells filled — since render_fill_snapshot
        returns "" in both cases.
        """
        from searchos.config.settings import settings as _settings
        from searchos.socm.views import SearchStateSnapshot
        from searchos.socm.views import (
            render_extraction_snapshot,
            render_fill_snapshot,
            render_known_pk_list,
        )
        snap = SearchStateSnapshot.from_state(state)
        if not _settings.extraction_dual_mode:
            return [("merged", render_extraction_snapshot(snap, tid))]
        calls: list[tuple[str, str]] = []
        fill_view = render_fill_snapshot(snap, tid)
        if fill_view:  # "" = empty table OR all cells already filled → skip FILL
            calls.append(("fill", fill_view))
        calls.append(("discover", render_known_pk_list(snap, tid)))
        return calls

    async def _extract_and_ingest_table(
        self, items: list[dict[str, Any]], tid: str,
    ) -> int:
        """Run the flush's judge call(s) (fill/discover in dual mode, one
        merged call in legacy mode), then ingest every returned row in a
        single atomic update.

        Held under a per-table lock so the snapshot reflects rows committed by
        a prior flush for this same table — concurrent same-table flushes would
        otherwise render stale snapshots and emit duplicate new rows. State is
        re-loaded fresh inside the lock for the same reason. Within one flush,
        the judge calls run concurrently."""
        if not tid:
            return 0
        async with self._table_lock(tid):
            fresh = self._workspace.load_state()
            schema = fresh.coverage_map.tables.get(tid)
            if schema is None or not schema.attributes:
                return 0
            calls = self._plan_judge_calls(tid, fresh)
            # Oversized inputs (esp. skill JSON) are split into segments so no
            # single judge call overruns the input/output window; each
            # (segment × mode) runs concurrently and all bundles ingest once.
            chunks = self._chunk_long_items(items)
            results = await asyncio.gather(*(
                self._run_row_judge(chunk, schema, view, fresh, mode=mode)
                for chunk in chunks
                for mode, view in calls
            ))
            # Hash settling is per-flush, not per-call: release for retry
            # unless every call parsed cleanly (re-extraction redoes both
            # modes; ingest-time dedup absorbs the overlap).
            all_ok = all(ok for _b, ok in results)
            for it in items:
                self._settle_content_hashes(it, success=all_ok)
            bundles = [b for bl, _ok in results for b in bl]
            # results is now (segments × modes), so a positional zip with calls
            # no longer holds — aggregate counts from each bundle's own mode tag.
            mode_counts: dict[str, int] = {}
            for _b in bundles:
                _m = _b[3] if len(_b) > 3 else "merged"
                mode_counts[_m] = mode_counts.get(_m, 0) + 1
            # Cross-mode dedup: both modes can emit the same PK (fill
            # echoing an existing row the discover call also re-found, or
            # fill violating its no-new-rows rule) — keep the fuller row.
            # A kept fill bundle whose PK the discover call also emitted
            # inherits discover's row-creation right, so the row isn't
            # lost to the fill_mode_new_row rejection at ingest.
            if len(results) > 1 and bundles:
                def _pk(row: dict[str, Any]) -> str:
                    return "|".join(str(row.get(k, "")) for k in schema.primary_key)
                discover_pks = {_pk(b[0]) for b in bundles if b[3] == "discover"}
                by_id = {id(b[0]): b for b in bundles}
                deduped_rows = self._dedup_rows([b[0] for b in bundles], schema)
                bundles = []
                for r in deduped_rows:
                    b = by_id[id(r)]
                    if b[3] == "fill" and _pk(r) in discover_pks:
                        b = (b[0], b[1], b[2], "discover")
                    bundles.append(b)
            if not bundles:
                return 0
            written = {"v": 0}
            rejected = {"v": []}
            committed_ids: dict[str, list[str]] = {"v": []}

            def _merge(s: Any) -> Any:
                nodes, rej = self._ingest_rows(bundles, tid, s)
                written["v"] = len(nodes)
                committed_ids["v"] = [n.id for n in nodes]  # last retry wins
                rejected["v"] = rej
                return s

            self._workspace.atomic_update_state(_merge)
            self._added_node_ids.update(committed_ids["v"])
        if self._trajectory_logger:
            event = {
                "type": "harness",
                "kind": "row_extraction",
                "rows_returned": len(bundles),
                "rows_by_mode": mode_counts,
                "input_chunks": len(chunks),
                "findings_written": written["v"],
                "table_id": tid,
                "extraction_index": self._extraction_count,
            }
            if rejected["v"]:
                event["rows_rejected_by_check"] = len(rejected["v"])
                event["rejected_samples"] = rejected["v"][:5]
            self._trajectory_logger._append_raw(event)
        return written["v"]

    async def _run_row_judge(
        self, items: list[dict[str, Any]], schema: Any,
        view: str, state: Any, *, mode: str,
    ) -> tuple[list[tuple[dict[str, Any], str, str, str]], bool]:
        """One judge call over all pages in the flush. Returns
        ``(bundles, ok)`` where each bundle is (row, page_text, source_url,
        mode) and ``ok`` is False only on judge failure / unparseable output
        (a legitimate empty [] is ok=True). No state writes."""
        sub_agent_task = self._get_sub_agent_task(state)
        # Scope anchor: dispatches enumerate specific known rows ("目标院校：
        # A、B、C"), so a prompt scoped to the sub-agent task alone makes the
        # judge skip every off-list row as "out of scope" — discover then
        # never finds anything. The overall intent defines what's in scope;
        # the sub-task only says where this agent is looking.
        global_task = getattr(state, "intent", "") or sub_agent_task
        pages = [
            {"source_url": it.get("source_url", "") or "",
             "content": it.get("content", "") or ""}
            for it in items
        ]
        common = dict(
            sub_agent_task=sub_agent_task,
            primary_key=schema.primary_key,
            data_columns=schema.data_columns,
            column_desc=schema.column_desc,
            pages=pages,
        )
        if mode == "fill":
            prompt = build_fill_row_prompt(
                **common, global_task=global_task, coverage_snapshot=view)
        elif mode == "discover":
            prompt = build_discover_row_prompt(
                **common, global_task=global_task, known_pk_list=view)
        else:
            prompt = build_coverage_aware_row_prompt(**common, global_task=global_task, coverage_snapshot=view)
        try:
            raw = await self._judge_invoke_with_retry(prompt)
        except Exception:  # noqa: BLE001
            logger.warning("row extraction (%s) raised", mode, exc_info=True)
            return [], False
        rows = self._parse_findings(raw) if raw else []
        self._extraction_count += 1
        if not rows:
            reason = self._log_row_extraction_empty(
                raw, items[0] if items else {}, mode=mode,
            )
            return [], reason == "judge_returned_no_rows"
        deduped = self._dedup_rows(rows, schema)
        # One row anchors to ONE original page: page_id / span / excerpt all
        # derive from the bundled (text, url), so stamping every row with the
        # concatenated batch text + comma-joined URLs produces page_ids that
        # resolve to no stored page and excerpts anchored to whichever page
        # mentions the value first.
        return [
            (r, *self._resolve_row_page(r, pages), mode) for r in deduped
        ], True

    @staticmethod
    def _resolve_row_page(
        row: dict[str, Any], pages: list[dict[str, str]],
    ) -> tuple[str, str]:
        """The single page a row's evidence lives on → (page_text, source_url).

        Trusts the judge's ``_source_page`` (1-based "### Page N" index) when
        valid; otherwise scores each page — excerpt anchoring dominates, row
        text containment breaks ties — and takes the best (earliest on tie)."""
        if len(pages) == 1:
            return pages[0]["content"], pages[0]["source_url"]
        try:
            idx = int(str(row.get("_source_page", "")).strip())
        except (TypeError, ValueError):
            idx = 0
        if 1 <= idx <= len(pages):
            return pages[idx - 1]["content"], pages[idx - 1]["source_url"]
        from searchos.util.span_match import find_span

        excerpt = str(row.get("_source_excerpt", "") or "").strip()
        cell_texts = [
            t for k, v in row.items()
            if not str(k).startswith("_") and v is not None
            and len(t := str(v).strip()) >= 2 and t.lower() not in _NULL_VALUES
        ]
        best_i, best_score = 0, -1
        for i, p in enumerate(pages):
            content = p["content"]
            score = 0
            if excerpt and find_span(content, excerpt)[0] is not None:
                score += len(cell_texts) + 1  # outranks any containment count
            score += sum(1 for t in cell_texts if t in content)
            if score > best_score:
                best_i, best_score = i, score
        return pages[best_i]["content"], pages[best_i]["source_url"]

    def _ingest_rows(
        self, bundles: list[tuple], tid: str, s: Any,
    ) -> tuple[list[Any], list[dict[str, str]]]:
        """Rule-based ingest of extracted rows into ``s`` (runs inside an
        atomic update). Each bundle is (row, page_text, source_url[, mode]).
        For each row: build the PK entity key, resolve it to
        an existing row (exact → fuzzy) or create it, then write one
        EvidenceNode per non-null data column and project into cells. No LLM,
        no full-graph rescan — only this batch's rows are touched.
        Returns (new_nodes, rejected) — rejected rows violated a ColumnCheck,
        or came out of a FILL-mode call with a PK that resolves to no
        existing row (fill must not invent rows; that's the discover call's
        job, and an unresolvable fill row is a hallucination signal)."""
        import hashlib
        import uuid
        from searchos.socm import EvidenceNode

        cmap = s.coverage_map
        schema = cmap.tables.get(tid)
        if schema is None:
            return [], []
        null_values = _NULL_VALUES
        conf_map = {"high": 0.9, "medium": 0.6, "low": 0.3}
        new_nodes: list[Any] = []
        rejected: list[dict[str, str]] = []
        checks = {
            col: cd.check
            for col, cd in (schema.column_desc or {}).items()
            if getattr(cd, "check", None) is not None
        }

        for bundle in bundles:
            row, page_text, source_url = bundle[:3]
            mode = bundle[3] if len(bundle) > 3 else "merged"
            key_vals: dict[str, str] = {}
            ok = True
            for k in schema.primary_key:
                v = str(row.get(k, "")).strip()
                if not v or v.lower() in null_values:
                    ok = False
                    break
                key_vals[k] = v
            if not ok:
                continue
            raw_entity = TableSchema.make_entity_key(key_vals, schema.primary_key)
            if not raw_entity:
                continue
            # Hard admission rules: any checked column violating drops the row
            check_reason = None
            for col, chk in checks.items():
                check_reason = chk.violation(row.get(col))
                if check_reason:
                    rejected.append({
                        "row": raw_entity, "column": col, "reason": check_reason,
                    })
                    break
            if check_reason:
                continue
            # Canonicalize: reuse an existing row if this is a surface variant,
            # else create the row (materializes its MISSING cells).
            entity = cmap.resolve_entity(raw_entity, table_id=tid)
            if entity is None:
                if mode == "fill":
                    rejected.append({
                        "row": raw_entity, "column": "",
                        "reason": "fill_mode_new_row",
                    })
                    continue
                cmap.add_entity(raw_entity, table_id=tid)
                entity = raw_entity

            alignment = str(row.get("_alignment", "full")).strip().lower()
            if alignment not in ("full", "partial", "loose"):
                alignment = "full"
            confidence = conf_map.get(
                str(row.get("_confidence", "high")).strip().lower(), 0.9,
            )
            source_authority = str(row.get("_source_authority", "unclear")).strip().lower()
            alignment_note = str(row.get("_alignment_note", "")).strip()
            row_excerpt = str(row.get("_source_excerpt", "")).strip()
            page_id = (
                hashlib.md5(source_url.encode("utf-8")).hexdigest()[:12]
                if source_url else ""
            )

            for attr in schema.data_columns:
                val = str(row.get(attr, "")).strip()
                if not val or val.lower() in null_values:
                    continue
                # Factuality gate: the judge's value is required to be verbatim
                # (unit conversion happens below, in code), so its significant
                # numbers must literally occur on the page. Cell-level reject —
                # the row's other cells may still be grounded.
                gate_reason = _ungrounded_number(page_text, val)
                if gate_reason:
                    rejected.append({
                        "row": raw_entity, "column": attr, "reason": gate_reason,
                    })
                    continue
                fid = f"f_{uuid.uuid4().hex[:8]}"
                excerpt, span, text_hash = _anchored_excerpt(
                    page_text, row_excerpt, val, entity, attr,
                )
                # Deterministic unit fix: the judge often copies the verbatim
                # source number into a unit-pinned column without converting
                # (e.g. "$131 billion" -> "131" in a 亿美元 column). The excerpt
                # retains the original wording, so rescale in code.
                cd = (getattr(schema, "column_desc", None) or {}).get(attr)
                col_text = f"{attr} {getattr(cd, 'desc', '')}" if cd else attr
                new_val, unit_note = normalize_value(val, excerpt, col_text)
                cell_note = alignment_note
                if new_val != val:
                    val = new_val
                    cell_note = f"{alignment_note}; {unit_note}".strip("; ") \
                        if alignment_note else unit_note
                # A cell whose excerpt never anchored to the page has no
                # verifiable provenance — it must not out-vote a grounded
                # value at conflict arbitration, whatever the judge claimed.
                cell_conf = confidence if span is not None else min(confidence, 0.4)
                node = EvidenceNode(
                    id=fid,
                    finding=f"{entity} {attr}: {val}",
                    value=val,
                    source=source_url,
                    source_excerpt=excerpt,
                    confidence=cell_conf,
                    entity=entity,
                    attribute=attr,
                    alignment=alignment,
                    alignment_note=cell_note or f"row-level extraction from {source_url}",
                    source_authority=source_authority,
                    page_id=page_id,
                    span=span,
                    text_hash=text_hash,
                    table_id=tid,
                )
                if s.evidence_graph.add_node(node):
                    new_nodes.append(node)

        if new_nodes:
            # Entities are now all canonical (in schema.entities) → exact resolve.
            cmap.fill_from_evidence(new_nodes)
        return new_nodes, rejected

    def _log_row_extraction_empty(
        self, raw: str, item: dict[str, Any], *, mode: str = "",
    ) -> str:
        """Distinguish judge-empty / no-rows / parse-failure for trajectory.
        Returns the reason so callers can decide hash retryability."""
        source_url = item.get("source_url", "") or ""
        page_chars = len(item.get("content", "") or "")
        if not raw:
            reason, raw_head = "judge_returned_empty", ""
        elif raw.strip() in ("", "[]", "{}"):
            reason, raw_head = "judge_returned_no_rows", raw.strip()[:80]
        else:
            reason, raw_head = "parse_returned_no_rows", raw.strip()[:200]
        if self._trajectory_logger:
            self._trajectory_logger._append_raw({
                "type": "harness",
                "kind": "row_extraction_empty",
                "mode": mode,
                "reason": reason,
                "source": source_url[:200],
                "page_chars": page_chars,
                "raw_head": raw_head,
            })
        return reason

    _HASH_MAX_ATTEMPTS = 2

    def _settle_content_hashes(self, item: dict[str, Any], *, success: bool) -> None:
        """两段式提交的落槌：成功（含 judge 明确无相关行）→ hash 保持永久；
        解析失败/judge 异常 → 释放 hash 允许重开重抽，至多 _HASH_MAX_ATTEMPTS 次。"""
        if success:
            return
        for h in item.get("content_hashes") or []:
            n = self._hash_attempts.get(h, 0) + 1
            self._hash_attempts[h] = n
            if n < self._HASH_MAX_ATTEMPTS:
                self._extracted_content_hashes.discard(h)
                if self._trajectory_logger:
                    self._trajectory_logger._append_raw({
                        "type": "harness",
                        "kind": "extraction_hash_released",
                        "source": (item.get("source_url", "") or "")[:200],
                        "attempt": n,
                    })

    # ---- Orphan-resolver safety net (NON-PK / findings-model tables only) --

    async def _judge_invoke_with_retry(self, prompt: str) -> str:
        """One retry + factoid-prompt fallback. Returns raw content or ""
        on total failure. Trajectory events document each step."""
        import asyncio as _asyncio

        for attempt in range(2):
            try:
                response = await self._judge.ainvoke(prompt)
                return response.content if hasattr(response, "content") else str(response)
            except Exception as exc:
                if self._trajectory_logger:
                    self._trajectory_logger._append_raw({
                        "type": "harness", "kind": "judge_retry",
                        "attempt": attempt, "error": str(exc)[:200],
                    })
                logger.debug("judge attempt %d failed: %s", attempt, exc)
                await _asyncio.sleep(0.5)

        # Degraded: salvage anything via a short summary prompt.
        short = (
            "Summarize any factual claims in this text as a JSON array of "
            "{finding, entity_hint, attribute_hint, alignment, page_idx} "
            "objects. Return [] if nothing factual.\n\n" + prompt[-4000:]
        )
        try:
            response = await self._judge.ainvoke(short)
            raw = response.content if hasattr(response, "content") else str(response)
            if self._trajectory_logger:
                self._trajectory_logger._append_raw({
                    "type": "harness", "kind": "judge_degraded",
                    "raw_len": len(raw),
                })
            return raw
        except Exception as exc:
            if self._trajectory_logger:
                self._trajectory_logger._append_raw({
                    "type": "harness", "kind": "judge_failed",
                    "error": str(exc)[:200],
                    "error_type": type(exc).__name__,
                })
            logger.warning(
                "judge_invoke_with_retry: all attempts failed: %s(%s)",
                type(exc).__name__, str(exc).strip(),
            )
            return ""


    @staticmethod
    def _unwrap_ai_message(response: Any) -> Any:
        """Unwrap langchain's ModelResponse down to the AIMessage so
        getattr(response, 'tool_calls') isn't always None."""
        return unwrap_ai_message(response)

    @classmethod
    def _response_has_tool_calls(cls, response: Any) -> bool:
        msg = cls._unwrap_ai_message(response)
        tc = getattr(msg, "tool_calls", None)
        if tc:
            return True
        ak = getattr(msg, "additional_kwargs", None) or {}
        if isinstance(ak, dict) and ak.get("tool_calls"):
            return True
        return False

    @staticmethod
    def _dedup_rows(rows: list[dict[str, Any]], schema: Any) -> list[dict[str, Any]]:
        """Dedup by (PK, source page); keep the row with more filled data
        columns; ties broken by better alignment. Same-PK rows quoting
        DIFFERENT pages are corroborating statements, not duplicates — each
        anchors to its own page, and node-level dedup keys on source."""
        null_values = _NULL_VALUES
        seen: dict[str, dict[str, Any]] = {}
        for row in rows:
            key = "|".join(str(row.get(k, "")) for k in schema.primary_key)
            if not key or key == "|" * len(schema.primary_key):
                continue
            page_tag = str(row.get("_source_page", "") or "").strip()
            if page_tag:
                key = f"{key}@page{page_tag}"
            if key not in seen:
                seen[key] = row
                continue
            existing = seen[key]
            existing_filled = sum(
                1 for a in schema.attributes
                if str(existing.get(a, "")).strip().lower() not in null_values
            )
            new_filled = sum(
                1 for a in schema.attributes
                if str(row.get(a, "")).strip().lower() not in null_values
            )
            if new_filled > existing_filled:
                seen[key] = row
            elif new_filled == existing_filled:
                rank = {"full": 2, "partial": 1}
                old_r = rank.get(str(existing.get("_alignment", "")).lower(), 0)
                new_r = rank.get(str(row.get("_alignment", "")).lower(), 0)
                if new_r > old_r:
                    seen[key] = row
        return list(seen.values())

    def _build_feedback(self, pre_filled: set[str]) -> str:
        """Brief summary of what the last flush extracted (recent findings
        count + entity hints). Search agent doesn't see CoverageMap."""
        state = self._workspace.load_state()
        graph = state.evidence_graph
        if not graph.nodes:
            return ""
        recent = [n for n in graph.nodes if n.id not in pre_filled]
        if not recent:
            return ""
        parts = [f"[Extraction feedback] {len(recent)} findings recorded this batch."]
        entity_hints = sorted({n.entity for n in recent if n.entity})
        if entity_hints and len(entity_hints) <= 8:
            parts.append(f"Entities seen: {', '.join(entity_hints[:8])}")
        elif entity_hints:
            parts.append(f"Entities seen: {len(entity_hints)} unique")
        return "\n".join(parts)

    def _inject_feedback(self, result: Any, feedback: str) -> Any:
        """Append extraction feedback to tool result content."""
        if hasattr(result, "content"):
            original = str(result.content)
            new_content = original + "\n\n" + feedback
            try:
                result.content = new_content
                return result
            except (AttributeError, TypeError):
                pass
        return str(result) + "\n\n" + feedback

    def _get_sub_agent_task(self, state: Any) -> str:
        try:
            from searchos.tools.search_state import _current_task_var
            task = _current_task_var.get() or ""
        except Exception:
            task = ""
        return task or getattr(state, "intent", "") or "(no task specified)"

    @staticmethod
    def _parse_findings(raw: str) -> list[dict]:
        """Parse judge output: bare JSON array, embedded array, or single object."""
        from searchos.util.json_extract import extract_json_object
        raw = raw.strip()
        if raw.startswith("["):
            try:
                arr = json.loads(raw)
                if isinstance(arr, list):
                    return arr
            except json.JSONDecodeError:
                pass
        import re
        match = re.search(r"\[.*\]", raw, re.DOTALL)
        if match:
            try:
                arr = json.loads(match.group())
                if isinstance(arr, list):
                    return arr
            except json.JSONDecodeError:
                pass
        obj = extract_json_object(raw)
        if obj and isinstance(obj, dict) and ("finding" in obj or "entity_hint" in obj):
            return [obj]
        return []

    # Narrow patterns — false positives here = silent data loss, so we only
    # match unambiguous error / auth-wall pages.
    _UNEXTRACTABLE_PATTERNS = (
        "404 not found", "page not found", "页面不存在", "页面未找到",
        "403 forbidden", "access denied", "permission denied",
        "please sign in", "please log in", "login required", "请登录",
        "cloudflare", "are you human", "verify you are human",
        "captcha", "just a moment...",
        "service unavailable", "503 service",
    )

    @classmethod
    def _is_extractable_page(cls, content: str) -> bool:
        """False on clearly-error / auth-wall / captcha stubs or body
        shorter than a sentence. Conservative — borderline pages still
        reach the judge."""
        if not content:
            return False
        body = content
        header_end = body.find("\n")
        if header_end > 0 and header_end < 300:
            body = body[header_end + 1:]
        if len(body.strip()) < 80:
            return False
        lower = content.lower()
        for pat in cls._UNEXTRACTABLE_PATTERNS:
            if pat in lower:
                # Require the marker in the first 600 chars (where error
                # pages put their headline) — a long article that just
                # mentions "captcha" in passing shouldn't be filtered.
                if lower.find(pat) < 600:
                    return False
        return True

    @staticmethod
    def _extract_tool_name(request: Any) -> str:
        return extract_tool_name(request, default="")

    @staticmethod
    def _get_result_content(result: Any) -> str:
        if hasattr(result, "content"):
            return str(result.content)
        return str(result)

    def _skill_extraction_input(self, content: str) -> tuple[str, str] | None:
        """Prep a ``skill_<name>`` JSON result for evidence extraction.

        Returns ``(content, source_url)`` to extract, or ``None`` to skip
        (error/unsuccessful result). Skills emit already-structured data; the
        whole payload goes to the judge, attributed to the result's own
        ``url``/``source_url`` field when present.
        """
        import json as _json
        try:
            data = _json.loads(content)
        except Exception:
            return content, self._extract_source_url(content)
        if isinstance(data, dict):
            if data.get("error") or data.get("success") is False:
                return None
            for key in ("source_url", "url", "page_url"):
                v = data.get(key)
                if isinstance(v, str) and v.startswith("http"):
                    return content, v
        return content, self._extract_source_url(content)

    def _render_skill_findings_for_agent(
        self, content: str, nodes: list[Any], source_url: str,
    ) -> str | None:
        """Stitch the evidence nodes extracted from a skill result into the
        agent-facing tool result. Returns ``None`` when nothing was extracted —
        the caller then keeps the raw payload so the agent is never handed an
        empty result.

        Faithful, not lossy: every finding is listed (no grouping/dropping),
        prefixed with provenance + a "returned N / extracted M" scope line so
        the agent knows it is seeing the EXTRACTION, not the raw source, and
        won't mistake M for everything the skill found."""
        if not nodes:
            return None
        import json as _json
        title = url = ""
        total_rows: Any = None
        try:
            data = _json.loads(content)
            if isinstance(data, dict):
                title = str(data.get("title", "") or "")
                url = str(data.get("url", "") or data.get("source_url", "") or "")
                total_rows = data.get("total_rows")
        except Exception:
            pass
        url = url or source_url

        header = f"[skill extraction] {title}".rstrip()
        if url:
            header += f" — {url}"
        scope = (
            f"Source returned ~{total_rows} rows; extracted {len(nodes)} findings"
            if total_rows is not None
            else f"Extracted {len(nodes)} findings from this skill result"
        )
        scope += " (this IS the structured extraction, not the raw payload):"

        lines = [header, scope]
        for i, n in enumerate(nodes, 1):
            finding = (n.finding or "").strip()
            if not finding:
                ent, attr, val = n.entity or "", n.attribute or "", n.value or ""
                finding = f"{ent} {attr}: {val}".strip()
            lines.append(f"{i}. {finding}")
        return "\n".join(lines)

    @staticmethod
    def _extract_source_url(content: str) -> str:
        """Pull canonical URL from a page observation.
        Priority: ``<Page N> ... (https://...)`` title (reliable even with
        wrapped URL: lines) → ``URL:`` body line → bare https?:// match."""
        import re
        # Greedy to whitespace, then peel a *wrapping* ')' via balance check —
        # Wikipedia URLs like ``..._(programming_language)`` contain ')'.
        match = re.search(r"<Page \d+>[^\n]*?\((https?://\S+)", content)
        if match:
            url = match.group(1)
            while url.endswith(")") and url.count(")") > url.count("("):
                url = url[:-1]
            return url
        match = re.search(r"URL:\s*(https?://\S+)", content)
        if match:
            return match.group(1)
        match = re.search(r"https?://\S+", content)
        return match.group(0) if match else ""


async def replay_pending_summaries(
    workspace: Any,
    judge_model: Any,
    table_ids: list[str],
    *,
    trajectory_logger: Any = None,
) -> int:
    """Drain state.pending_agent_summaries and run row-extraction against
    each declared table. Used by create_schema to recover explore's final
    summary (explore runs before any schema exists, so its agent:// page
    is stashed and would otherwise be lost)."""
    state = workspace.load_state()
    pending = list(state.pending_agent_summaries or [])
    if not pending or not table_ids or judge_model is None:
        return 0

    # Snapshot-and-clear under atomic update so a second create_schema
    # call (re-plan) doesn't double-extract.
    def _drain(s: Any) -> Any:
        s.pending_agent_summaries.clear()
        return s
    workspace.atomic_update_state(_drain)

    mw = EvidenceExtractionMiddleware(
        judge_model=judge_model,
        workspace=workspace,
        trajectory_logger=trajectory_logger,
    )
    items = [
        {
            "source_url": p.get("source_url", "") or "",
            "content": p.get("content", "") or "",
        }
        for p in pending
    ]
    items = mw._prepare_extraction_pages(items)
    if not items:
        return 0

    # Row tables → batched ingest (matches live flush); others → per-page.
    async def _replay_table(tid: str) -> None:
        schema = state.coverage_map.tables.get(tid)
        if schema is not None and getattr(schema, "primary_key", None):
            await mw._extract_and_ingest_table(items, tid)

    await asyncio.gather(*[_replay_table(tid) for tid in table_ids])

    # Extraction wrote EvidenceNodes; cell-fill normally runs at sub-agent
    # termination via _compute_agent_report, but replay skips that path —
    # drive backfill directly.
    cells_filled = {"v": 0}
    def _backfill(s: Any) -> Any:
        for tid in table_ids:
            cells_filled["v"] += s.coverage_map.backfill_from_evidence(
                s.evidence_graph, table_id=tid,
            )
        return s
    workspace.atomic_update_state(_backfill)

    if trajectory_logger:
        trajectory_logger._append_raw({
            "type": "harness",
            "kind": "pending_summary_replayed",
            "items": len(items),
            "tables": table_ids,
            "cells_filled": cells_filled["v"],
        })
    return len(items)
