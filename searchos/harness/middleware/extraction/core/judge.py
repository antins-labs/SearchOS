"""规划 FILL/DISCOVER 提示词，调用模型并解析带来源的候选行。"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from searchos.harness.middleware.extraction.core.models import ExtractionConfig
from searchos.harness.middleware.extraction.core.prompts import (
    build_coverage_aware_row_prompt,
    build_discover_row_prompt,
    build_fill_row_prompt,
)
from searchos.harness.middleware.extraction.utils.grounding import _NULL_VALUES

logger = logging.getLogger(__name__)


class RowExtractor:
    """管理模型调用与候选解析；不持有 Store 或协调器。"""

    def __init__(
        self, judge_model: Any, config: ExtractionConfig, trajectory_logger: Any = None
    ) -> None:
        self._judge = judge_model
        self._config = config
        self._trajectory_logger = trajectory_logger
        self.call_count = 0
        self._call_semaphore = asyncio.Semaphore(max(1, config.flush_concurrency))

    def plan_calls(self, tid: str, state: Any) -> list[tuple[str, str]]:
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
        from searchos.socm.views import (
            SearchStateSnapshot,
            render_extraction_snapshot,
            render_fill_snapshot,
            render_known_pk_list,
        )

        snap = SearchStateSnapshot.from_state(state)
        if not self._config.dual_mode:
            return [("merged", render_extraction_snapshot(snap, tid))]
        calls: list[tuple[str, str]] = []
        fill_view = render_fill_snapshot(snap, tid)
        if fill_view:  # "" = empty table OR all cells already filled → skip FILL
            calls.append(("fill", fill_view))
        calls.append(("discover", render_known_pk_list(snap, tid)))
        return calls

    async def extract_rows(
        self,
        items: list[dict[str, Any]],
        schema: Any,
        view: str,
        state: Any,
        *,
        mode: str,
    ) -> tuple[list[tuple[dict[str, Any], str, str, Any, str]], bool]:
        """One judge call over all pages in the flush. Returns
        ``(bundles, ok)`` where each bundle is (row, page_text, source_url,
        mode) and ``ok`` is False only on judge failure / unparseable output
        (a legitimate empty [] is ok=True). No state writes."""
        sub_agent_task = next(
            (item["task_text"] for item in items if item.get("task_text")),
            getattr(state, "intent", "") or "(no task specified)",
        )
        # Scope anchor: dispatches enumerate specific known rows ("目标院校：
        # A、B、C"), so a prompt scoped to the sub-agent task alone makes the
        # judge skip every off-list row as "out of scope" — discover then
        # never finds anything. The overall intent defines what's in scope;
        # the sub-task only says where this agent is looking.
        global_task = getattr(state, "intent", "") or sub_agent_task
        pages = [
            {
                "source_url": it.get("source_url", "") or "",
                "source_urls": it.get("source_urls", []),
                "page_id": it.get("page_id", "") or "",
                "content": it.get("content", "") or "",
                "local_source_metadata": it.get("local_source_metadata"),
                "observation_text": it.get("observation_text", it.get("content", "") or ""),
            }
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
                **common, global_task=global_task, coverage_snapshot=view
            )
        elif mode == "discover":
            prompt = build_discover_row_prompt(
                **common, global_task=global_task, known_pk_list=view
            )
        else:
            prompt = build_coverage_aware_row_prompt(
                **common,
                global_task=global_task,
                coverage_snapshot=view,
            )
        rows = None
        raw = ""
        for attempt in range(3):
            retry_prompt = prompt
            if attempt:
                retry_prompt += (
                    "\n\n[JSON format correction] The previous response was not a valid JSON array of objects. "
                    "Return the complete result as valid JSON only. Quote all strings, including values "
                    "containing units or symbols. Preserve source values and excerpts; do not calculate, "
                    "drop rows or invent values to repair formatting. Return [] only when the sources support no rows."
                )
            try:
                raw = await self.invoke(retry_prompt)
            except Exception:  # noqa: BLE001
                logger.warning("row extraction (%s) raised", mode, exc_info=True)
                return [], False
            self.call_count += 1
            rows = self._parse_findings(raw) if raw else None
            if rows is not None or not raw:
                break  # invoke already bounds retries for transport failures
            if attempt < 2 and self._trajectory_logger:
                self._trajectory_logger._append_raw({
                    "type": "harness", "kind": "judge_format_retry", "mode": mode,
                    "attempt": attempt + 1, "source": items[0].get("source_url", "") if items else "",
                })
        if rows is None:
            self._log_row_extraction_empty(raw, items[0] if items else {}, mode=mode)
            return [], False
        if not rows:
            self._log_row_extraction_empty(
                "[]",
                items[0] if items else {},
                mode=mode,
            )
            return [], True
        # Missing/invalid page tags are resolved from each row below. Until
        # then equal primary keys may refer to different sources.
        deduped = self.dedup_rows(rows, schema) if len(pages) == 1 else rows
        # One row anchors to ONE original page: page_id / span / excerpt all
        # derive from the bundled (text, url), so stamping every row with the
        # concatenated batch text + comma-joined URLs produces page_ids that
        # resolve to no stored page and excerpts anchored to whichever page
        # mentions the value first.
        bundles = []
        for row in deduped:
            page = self._resolve_row_page(row, pages)
            text = page["content"]
            source = page["source_url"]
            metadata = page.get("local_source_metadata")
            original = next(
                page["observation_text"]
                for page in pages
                if page["content"] == text and page["source_url"] == source
            )
            bundles.append((row, text, source, metadata, mode, original,
                            page.get("page_id", ""), page.get("source_urls", [])))
        return bundles, True

    @staticmethod
    def _resolve_row_page(
        row: dict[str, Any],
        pages: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Resolve one evidence row to exactly one source page.

        Trusts the judge's ``_source_page`` (1-based "### Page N" index) when
        valid; otherwise scores each page — excerpt anchoring dominates, row
        text containment breaks ties — and takes the best (earliest on tie)."""
        if len(pages) == 1:
            return pages[0]
        try:
            idx = int(str(row.get("_source_page", "")).strip())
        except (TypeError, ValueError):
            idx = 0
        if 1 <= idx <= len(pages):
            return pages[idx - 1]
        from searchos.util.span_match import find_span

        excerpt = str(row.get("_source_excerpt", "") or "").strip()
        cell_texts = [
            t
            for k, v in row.items()
            if not str(k).startswith("_")
            and v is not None
            and len(t := str(v).strip()) >= 2
            and t.lower() not in _NULL_VALUES
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
        return pages[best_i]

    def _log_row_extraction_empty(
        self,
        raw: str,
        item: dict[str, Any],
        *,
        mode: str = "",
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
            self._trajectory_logger._append_raw(
                {
                    "type": "harness",
                    "kind": "row_extraction_empty",
                    "mode": mode,
                    "reason": reason,
                    "source": source_url[:200],
                    "page_chars": page_chars,
                    "raw_head": raw_head,
                }
            )
        return reason

    async def invoke(self, prompt: str) -> str:
        """最多三次同协议调用；保留 findings、支持核验或表格抽取的完整输入。

        输出解析和证据校验仍由各自调用方负责。有效空结果不触发额外调用；
        失败时不改用其他字段或截断原文，避免生成下游无法接收的候选。
        """
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                async with self._call_semaphore:
                    response = await self._judge.ainvoke(prompt)
                return response.content if hasattr(response, "content") else str(response)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                exhausted = attempt == max_attempts - 1
                if self._trajectory_logger:
                    self._trajectory_logger._append_raw(
                        {
                            "type": "harness",
                            "kind": "judge_failed" if exhausted else "judge_retry",
                            "attempt": attempt,
                            "error": str(exc)[:200],
                            "error_type": type(exc).__name__,
                        }
                    )
                if exhausted:
                    logger.warning(
                        "judge_invoke_with_retry: all attempts failed: %s(%s)",
                        type(exc).__name__,
                        str(exc).strip(),
                    )
                    return ""
                logger.debug("judge attempt %d failed: %s", attempt, exc)
                await asyncio.sleep(0.5)
        return ""

    @staticmethod
    def dedup_rows(rows: list[dict[str, Any]], schema: Any) -> list[dict[str, Any]]:
        """仅删除同一摘录支持的重复或被完整包含的行，保留互补与冲突事实。

        不拼接行：每个候选继续携带自己的来源摘录和条件。
        此方法仅用于一次调用内的 page 编号，跨调用由提交层按真实来源去重。
        """
        groups: dict[tuple, list[dict[str, Any]]] = {}
        rank = {"full": 2, "partial": 1, "loose": 0}

        def facts(row):
            return {
                (key, str(row.get(key, "")).strip())
                for key in schema.attributes
                if str(row.get(key, "")).strip().lower() not in _NULL_VALUES
            }

        def quality(row):
            return rank.get(str(row.get("_alignment", "full")).lower(), 0)

        for row in rows:
            pk = tuple(str(row.get(key, "")).strip() for key in schema.primary_key)
            if not all(pk):
                continue
            # Other grounding metadata may encode distinct conditions, units or
            # authority. Only equivalent provenance permits subsumption.
            provenance = tuple(
                sorted(
                    (key, json.dumps(value, sort_keys=True, ensure_ascii=False, default=str))
                    for key, value in row.items()
                    if str(key).startswith("_") and key not in {"_alignment", "_confidence"}
                )
            )
            key = (pk, provenance)
            kept = groups.setdefault(key, [])
            current = facts(row)
            if any(current <= facts(old) and quality(old) >= quality(row) for old in kept):
                continue
            kept[:] = [
                old for old in kept if not (facts(old) <= current and quality(row) >= quality(old))
            ]
            kept.append(row)
        return [row for rows in groups.values() for row in rows]

    @staticmethod
    def _parse_findings(raw: str) -> list[dict] | None:
        """有效空结果返回 []，格式错误返回 None，不把解析失败当作没有证据。"""
        from searchos.util.json_extract import extract_json_object

        raw = raw.strip()
        if raw == "{}":
            return []
        if raw.startswith("["):
            try:
                arr = json.loads(raw)
                if isinstance(arr, list):
                    return arr if all(isinstance(row, dict) for row in arr) else None
            except json.JSONDecodeError:
                pass
        import re

        match = re.search(r"\[.*\]", raw, re.DOTALL)
        if match:
            try:
                arr = json.loads(match.group())
                if isinstance(arr, list):
                    return arr if all(isinstance(row, dict) for row in arr) else None
            except json.JSONDecodeError:
                return None
        obj = extract_json_object(raw)
        if obj and isinstance(obj, dict) and ("finding" in obj or "entity_hint" in obj):
            return [obj]
        return None

    @staticmethod
    def strip_row_metadata(row: dict[str, Any]) -> dict[str, Any]:
        return {str(key): value for key, value in row.items() if not str(key).startswith("_")}
