"""清理阅读窗口、保留同源上下文，并按输入预算切片。"""

from __future__ import annotations

import json
from typing import Any

from searchos.harness.middleware.extraction.core.models import ExtractionConfig


class ObservationPreparer:
    """每个协调器独享的窗口历史；不调用模型、不写入证据。"""

    def __init__(self, config: ExtractionConfig, trajectory_logger: Any = None) -> None:
        self._config = config
        self._trajectory_logger = trajectory_logger
        self._source_window_history: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}

    @staticmethod
    def _strip_extraction_noise(text: str) -> str:
        """Strip the search-agent's render scaffolding (show_page header,
        L<N>: line prefixes, END OF PAGE footer). Markdown link sugar
        is left intact — regex strip breaks on URLs with escaped parens."""
        import re

        if text.startswith("[Now viewing local source]") and "\n\n" in text:
            return text.split("\n\n", 1)[1]

        out: list[str] = []
        for line in text.split("\n"):
            stripped = line.lstrip()
            if (
                stripped.startswith("[Now viewing]")
                or stripped.startswith("URL: ")
                or stripped.startswith("**viewing lines")
                or stripped.startswith("[END OF PAGE")
            ):
                continue
            m = re.match(r"^L\d+:\s?", line)
            if m:
                line = line[m.end() :]
            out.append(line)
        return "\n".join(out)

    def _clean_window(self, item: dict[str, Any]) -> dict[str, Any]:
        return {
            **item,
            "content": self._strip_extraction_noise(item.get("content", "") or ""),
            "observation_text": item.get("observation_text", item.get("content", "") or ""),
            "content_hashes": [item["content_hash"]] if item.get("content_hash") else [],
        }

    def prepare_pages(
        self,
        items: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Clean pages and attach bounded same-source context.

        URL/size-triggered batches can still split a long page across flushes.
        Keep a rolling history on this per-sub-agent Extraction so a continuation
        can see the preceding table rows/header. Only web PAGE observations
        participate; agent summaries, local documents, findings and skills
        retain their original semantics.
        """
        grouped: dict[str, list[dict[str, Any]]] = {}
        order: list[str] = []
        agent_items: list[dict[str, Any]] = []
        for it in items:
            url = it.get("source_url", "") or ""
            content = self._strip_extraction_noise(it.get("content", "") or "")
            hashes = [h for h in [it.get("content_hash", "")] if h]
            target_table = it.get("target_table", "") or ""
            local_source_metadata = it.get("local_source_metadata")
            source_kind = str(it.get("source_kind", "") or "")
            if (
                url.startswith(("agent://", "local://"))
                or it.get("result_mode") == "findings"
                or (source_kind and source_kind != "page")
            ):
                agent_items.append(self._clean_window(it))
                continue
            cleaned = {
                **it,
                "source_url": url,
                "content": content,
                "content_hashes": list(hashes),
                "target_table": target_table,
                "local_source_metadata": local_source_metadata,
            }
            if url not in grouped:
                grouped[url] = []
                order.append(url)
            grouped[url].append(cleaned)

        prepared: list[dict[str, Any]] = []
        for url in order:
            current = grouped[url]
            first = current[0]
            key = (
                str(first.get("task_id", "") or ""),
                str(first.get("target_table", "") or ""),
                str(first.get("result_mode", "") or ""),
                url,
            )
            current_hashes = list(
                dict.fromkeys(h for item in current for h in item.get("content_hashes", []) if h)
            )
            current_hash_set = set(current_hashes)
            prior = [
                item
                for item in self._source_window_history.get(key, [])
                if item.get("content_hash") not in current_hash_set
            ]
            selected_prior = self._select_source_context(prior, current)
            windows = selected_prior + current
            if len(windows) == 1:
                merged_content = windows[0]["content"]
            else:
                parts = []
                prior_count = len(selected_prior)
                for index, window in enumerate(windows):
                    role = "retained context" if index < prior_count else "current viewport"
                    parts.append(f"--- ({role} on same page) ---\n{window['content']}")
                merged_content = "\n\n".join(parts)
            prepared.append(
                {
                    **first,
                    "content": merged_content,
                    "observation_text": merged_content,
                    # Settle only observations in this flush. Historical hashes
                    # may already be committed and must not be released on a later
                    # parse failure.
                    "content_hashes": current_hashes,
                }
            )
            self._remember_source_windows(key, prior + current)
        return prepared + agent_items

    def _select_source_context(
        self,
        prior: list[dict[str, Any]],
        current: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Choose the newest prior windows that fit beside this flush."""
        max_windows = max(0, int(self._config.source_context_max_windows))
        budget = min(
            max(0, int(self._config.source_context_char_budget)),
            max(0, int(self._config.chunk_char_budget)),
        )
        if max_windows == 0 or budget == 0:
            return []
        remaining_windows = max(0, max_windows - len(current))
        remaining_chars = max(0, budget - sum(len(it.get("content", "") or "") for it in current))
        chosen: list[dict[str, Any]] = []
        for item in reversed(prior):
            content = item.get("content", "") or ""
            if len(chosen) >= remaining_windows or len(content) > remaining_chars:
                break
            chosen.append(item)
            remaining_chars -= len(content)
        chosen.reverse()
        return chosen

    def _remember_source_windows(
        self,
        key: tuple[str, str, str, str],
        windows: list[dict[str, Any]],
    ) -> None:
        """Store a deduplicated, bounded tail for this agent/source."""
        unique: list[dict[str, Any]] = []
        positions: dict[str, int] = {}
        for item in windows:
            content_hash = str(item.get("content_hash", "") or "")
            if content_hash and content_hash in positions:
                unique[positions[content_hash]] = item
            else:
                if content_hash:
                    positions[content_hash] = len(unique)
                unique.append(item)
        max_windows = max(0, int(self._config.source_context_max_windows))
        budget = min(
            max(0, int(self._config.source_context_char_budget)),
            max(0, int(self._config.chunk_char_budget)),
        )
        kept: list[dict[str, Any]] = []
        chars = 0
        for item in reversed(unique):
            content = item.get("content", "") or ""
            if len(kept) >= max_windows or chars + len(content) > budget:
                break
            kept.append(item)
            chars += len(content)
        kept.reverse()
        if kept:
            self._source_window_history[key] = kept
        else:
            self._source_window_history.pop(key, None)

    def chunk_items(
        self,
        items: list[dict[str, Any]],
    ) -> list[list[dict[str, Any]]]:
        """Group flush items into judge-call chunks, splitting any item whose
        content exceeds the char budget (skill JSON payloads can be huge).

        Short items stay together as a single chunk, so when nothing is
        oversized this returns ``[items]`` — byte-for-byte the pre-split
        behavior. Each returned chunk is fed to one extract_rows call."""
        budget = self._config.chunk_char_budget
        max_records = self._config.chunk_max_records
        if all(
            len(it.get("content", "") or "") <= budget
            and not self._json_exceeds_record_limit(it.get("content", "") or "", max_records)
            for it in items
        ):
            return [items]
        chunks: list[list[dict[str, Any]]] = []
        short: list[dict[str, Any]] = []
        for it in items:
            content = it.get("content", "") or ""
            if len(content) <= budget and not self._json_exceeds_record_limit(content, max_records):
                short.append(it)
            else:
                chunks.extend(
                    [seg] for seg in self._split_oversized_item(it, budget, max_records=max_records)
                )
        if short:
            chunks.append(short)
        return chunks or [items]

    def _split_oversized_item(
        self,
        item: dict[str, Any],
        budget: int,
        *,
        max_records: int,
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
        target_table = item.get("target_table", "") or ""
        segs = self._split_skill_json(content, budget, max_records=max_records)
        if segs is None:
            header = self._context_header(content, url)
            segs = self._split_by_chars(content, budget, header=header)
        if self._trajectory_logger and len(segs) > 1:
            self._trajectory_logger._append_raw(
                {
                    "type": "harness",
                    "kind": "extraction_input_split",
                    "source": url[:200],
                    "orig_chars": len(content),
                    "segments": len(segs),
                }
            )
        return [
            {
                "source_url": url,
                **item,
                "content": s,
                "content_hashes": hashes,
                "target_table": target_table,
            }
            for s in segs
        ]

    @staticmethod
    def _split_skill_json(
        content: str,
        budget: int,
        *,
        max_records: int,
    ) -> list[str] | None:
        """Structure-aware split of a skill JSON payload along its longest
        array field. Returns None when the content is not a JSON object with a
        splittable (len > 1) array — the caller then falls back to char windows.
        Never splits below one array element, so a segment can exceed budget if a
        single element is itself huge (still preferable to broken JSON)."""
        import json as _json

        if not content.lstrip().startswith(("{", "[")):
            return None
        try:
            data = _json.loads(content)
        except Exception:
            return None

        def chunk_meta(
            *,
            split_field: str,
            chunk_index: int,
            chunk_count: int,
            record_start: int,
            records_in_chunk: int,
            total_records: int,
        ) -> dict[str, Any]:
            return {
                "split_field": split_field,
                "chunk_index": chunk_index,
                "chunk_count": chunk_count,
                "record_start_1based": record_start,
                "record_end_1based": record_start + records_in_chunk - 1,
                "records_in_chunk": records_in_chunk,
                "total_records": total_records,
            }

        if isinstance(data, list):
            groups: list[list[Any]] = []
            cur: list[Any] = []
            cur_len = 2
            for row in data:
                row_len = len(_json.dumps(row, ensure_ascii=False)) + 1
                if cur and (len(cur) >= max_records or cur_len + row_len > budget):
                    groups.append(cur)
                    cur, cur_len = [], 2
                cur.append(row)
                cur_len += row_len
            if cur:
                groups.append(cur)
            if len(groups) <= 1:
                return None
            total_records = len(data)
            chunk_count = len(groups)
            segs: list[str] = []
            record_start = 1
            for idx, group in enumerate(groups, start=1):
                wrapped = {
                    "_searchos_chunk": chunk_meta(
                        split_field="<root>",
                        chunk_index=idx,
                        chunk_count=chunk_count,
                        record_start=record_start,
                        records_in_chunk=len(group),
                        total_records=total_records,
                    ),
                    "records": group,
                }
                segs.append(_json.dumps(wrapped, ensure_ascii=False))
                record_start += len(group)
            return segs if len(segs) > 1 else None
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
        groups: list[list[Any]] = []
        cur: list[Any] = []
        cur_len = 0
        for r in rows:
            rlen = len(_json.dumps(r, ensure_ascii=False)) + 1
            if cur and (len(cur) >= max_records or base + cur_len + rlen > budget):
                groups.append(cur)
                cur, cur_len = [], 0
            cur.append(r)
            cur_len += rlen
        if cur:
            groups.append(cur)
        if len(groups) <= 1:
            return None
        total_records = len(rows)
        chunk_count = len(groups)
        segs: list[str] = []
        record_start = 1
        for idx, group in enumerate(groups, start=1):
            payload = {
                **meta,
                "_searchos_chunk": chunk_meta(
                    split_field=str(array_key),
                    chunk_index=idx,
                    chunk_count=chunk_count,
                    record_start=record_start,
                    records_in_chunk=len(group),
                    total_records=total_records,
                ),
                array_key: group,
            }
            segs.append(_json.dumps(payload, ensure_ascii=False))
            record_start += len(group)
        return segs if len(segs) > 1 else None

    @staticmethod
    def _json_exceeds_record_limit(content: str, max_records: int) -> bool:
        """Return whether a JSON object's longest top-level array needs splitting."""
        import json as _json

        if not content.lstrip().startswith(("{", "[")):
            return False
        try:
            data = _json.loads(content)
        except Exception:
            return False
        if isinstance(data, list):
            return len(data) > max_records
        return isinstance(data, dict) and any(
            isinstance(value, list) and len(value) > max_records for value in data.values()
        )

    @classmethod
    def count_records_in_chunks(
        cls,
        chunks: list[list[dict[str, Any]]],
    ) -> int | None:
        counts = [cls.count_records_in_items(chunk) for chunk in chunks]
        counts = [c for c in counts if c is not None]
        return sum(counts) if counts else None

    @classmethod
    def count_records_in_items(
        cls,
        items: list[dict[str, Any]],
    ) -> int | None:
        counts = [cls._count_structured_records(item.get("content", "") or "") for item in items]
        counts = [c for c in counts if c is not None]
        return sum(counts) if counts else None

    @staticmethod
    def _count_structured_records(content: str) -> int | None:
        """Best-effort count of records inside a structured skill payload.

        Prefer the longest top-level array length. For split skill JSON this
        counts the per-chunk array length (e.g. 50 + 50), not metadata such as
        ``items_count=100`` duplicated into every segment.
        """
        if not content.lstrip().startswith(("{", "[")):
            return None
        try:
            data = json.loads(content)
        except Exception:
            return None
        if isinstance(data, list):
            return len(data)
        if not isinstance(data, dict):
            return None
        array_lens = [len(value) for value in data.values() if isinstance(value, list)]
        if array_lens:
            return max(array_lens)
        for key in ("items_count", "total_items", "count", "total"):
            value = data.get(key)
            if isinstance(value, int) and value >= 0:
                return value
        return None

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

    def _split_by_chars(self, content: str, budget: int, header: str = "") -> list[str]:
        """Fallback split into budget-sized windows, cutting on a newline near
        the window end when possible and overlapping segments slightly so a
        record straddling a cut survives in at least one segment. Every segment
        after the first is prefixed with ``header`` (the leading metadata) so it
        keeps province/year/url context — the head budget shrinks to compensate
        so a segment+header still fits."""
        overlap = max(0, self._config.chunk_overlap_chars)
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


_UNEXTRACTABLE_PATTERNS = (
    "404 not found",
    "page not found",
    "页面不存在",
    "页面未找到",
    "403 forbidden",
    "access denied",
    "permission denied",
    "please sign in",
    "please log in",
    "login required",
    "请登录",
    "cloudflare",
    "are you human",
    "verify you are human",
    "captcha",
    "just a moment...",
    "service unavailable",
    "503 service",
)


def is_extractable_page(content: str) -> bool:
    """False on clearly-error / auth-wall / captcha stubs or body
    shorter than a sentence. Conservative — borderline pages still
    reach the judge."""
    if not content:
        return False
    body = content
    header_end = body.find("\n")
    if header_end > 0 and header_end < 300:
        body = body[header_end + 1 :]
    if len(body.strip()) < 80:
        return False
    lower = content.lower()
    for pat in _UNEXTRACTABLE_PATTERNS:
        if pat in lower:
            # Require the marker in the first 600 chars (where error
            # pages put their headline) — a long article that just
            # mentions "captcha" in passing shouldn't be filtered.
            if lower.find(pat) < 600:
                return False
    return True


class OriginalWindowPreparer(ObservationPreparer):
    """逐个保留原始观察，不合并跨次阅读的上下文。"""

    def prepare_pages(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [self._clean_window(item) for item in items]
