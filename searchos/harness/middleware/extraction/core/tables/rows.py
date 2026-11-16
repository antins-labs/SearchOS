"""规划 FILL/DISCOVER 提示词，调用模型并解析带来源的候选行。"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from searchos.harness.middleware.extraction.core.models import ExtractionConfig
from searchos.harness.middleware.extraction.core.tables.prompts import (
    build_coverage_aware_row_prompt,
    build_discover_row_prompt,
    build_fill_row_prompt,
)
from searchos.socm.evidence.missing_values import _NULL_VALUES
from searchos.socm.refs import cell_key
from searchos.utils.json_extract import parse_object_array

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

    def plan_calls(
        self, tid: str, state: Any, items: list[dict],
    ) -> list[tuple[str, set[str] | None]]:
        """双阶段按实体分窗；原文驱动模式保留一次完整写入范围。"""
        from searchos.harness.middleware.extraction.core.tables.targets import task_target_keys
        from searchos.socm.coverage.models import cell_is_actionable
        from searchos.socm.views import SearchStateSnapshot
        from searchos.socm.views.render import _SNAPSHOT_MAX_ROWS

        allowed = task_target_keys(state, items)
        snap = SearchStateSnapshot.from_state(state)
        table = next((t for t in snap.tables if t.table_id == tid), None)
        if table is None or allowed == set():
            return []
        if not self._config.dual_mode:
            return [("merged", allowed)]
        rows = []
        for row in table.rows:
            keys = {cell_key(tid, row.entity, c.attr) for c in row.cells
                    if cell_is_actionable(c, explicit_target=allowed is not None)}
            if allowed is not None:
                keys &= allowed
            if keys:
                rows.append(keys)
        calls = [("fill", set().union(*rows[i:i + _SNAPSHOT_MAX_ROWS]))
                 for i in range(0, len(rows), _SNAPSHOT_MAX_ROWS)]
        if allowed is None:
            calls.append(("discover", None))
        return calls

    @staticmethod
    def render_call(mode: str, tid: str, state: Any, targets: set[str] | None) -> str:
        from searchos.socm.views import (
            SearchStateSnapshot,
            render_fill_snapshot,
            render_known_pk_list,
        )
        if mode == "merged":
            return ""
        snap = SearchStateSnapshot.from_state(state)
        if mode == "discover":
            return render_known_pk_list(snap, tid)
        if mode == "fill":
            return render_fill_snapshot(snap, tid, targets)
        return ""

    async def extract_rows(
        self,
        items: list[dict[str, Any]],
        schema: Any,
        view: str,
        state: Any,
        *,
        mode: str,
        target_cells: set[str] | None = None,
    ) -> tuple[list[tuple[dict[str, Any], str, str, Any, str]], bool]:
        """One judge call over all pages in the flush. Returns
        ``ok=False`` 保留合法候选，并报告解析或来源归属失败。
        合法空数组完成结算。此方法不写状态。
        """
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
                "referring_page": it.get("referring_page"),
                "linked_records": it.get("linked_records", []),
                "page_id": it.get("page_id", "") or "",
                "content": it.get("content", "") or "",
                "local_source_metadata": it.get("local_source_metadata"),
                "observation_text": it.get("observation_text", it.get("content", "") or ""),
            }
            for it in items
        ]
        targeted_attrs = {state.coverage_map.parse_cell_key(key)[2] for key in target_cells or ()}
        common = dict(
            sub_agent_task=sub_agent_task,
            primary_key=schema.primary_key,
            data_columns=[col for col in schema.data_columns
                          if schema.requires_search(col) or col in targeted_attrs],
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
        scoped_targets = [item.get("task_target_cells") for item in items
                          if item.get("task_target_cells")]
        if scoped_targets:
            scoped_targets = sorted(target_cells) if target_cells is not None else scoped_targets
            prompt += f"""

## Explicit task write scope
Only return values for these target cells: {json.dumps(scoped_targets, ensure_ascii=False)}.
Do not reinterpret requirement IDs or fill other rows/columns. These explicit targets constrain
every extraction mode. A page about another requirement cannot fill these cells;
return [] when unsupported."""
        item = items[0] if items else {}
        ok = True
        for attempt in range(3):
            retry_prompt = prompt
            if attempt:
                retry_prompt += f"""

[JSON format correction] Return one JSON array of objects. Each row requires every primary-key
field: {json.dumps(schema.primary_key, ensure_ascii=False)}. Quote strings, including values
containing units or symbols. Preserve all supported rows, source values and excerpts.
Return [] only when the sources support no rows."""
            try:
                raw = await self.invoke(retry_prompt)
            except Exception:  # noqa: BLE001
                logger.warning("row extraction (%s) raised", mode, exc_info=True)
                return [], False
            self.call_count += 1
            if not raw:
                self._log_response(
                    "judge_format_failure", "judge_returned_empty", "", item, mode, attempt
                )
                return [], False  # invoke already bounds transport retries
            rows = self._parse_findings(raw)
            reason = "invalid_json_array"
            if rows is not None:
                if not rows:
                    self._log_response(
                        "row_extraction_empty", "judge_returned_no_rows", raw, item, mode, attempt
                    )
                    return [], True
                valid = [
                    row for row in rows if all(
                        isinstance(row.get(key), (str, int, float))
                        and str(row[key]).strip().lower() not in _NULL_VALUES
                        for key in schema.primary_key
                    )
                ]
                if len(valid) == len(rows):
                    break
                reason = "missing_primary_key"
                if valid:
                    # 提交有效行，同时保留未完成的观察供重放。
                    self._log_response("judge_format_failure", reason, raw, item, mode, attempt)
                    rows, ok = valid, False
                    break
            if attempt == 2:
                self._log_response("judge_format_failure", reason, raw, item, mode, attempt)
                return [], False
            self._log_response("judge_format_retry", reason, raw, item, mode, attempt)
        # 多页候选在页身份验证后由提交层去重，同键可来自不同来源。
        deduped = self.dedup_rows(rows, schema) if len(pages) == 1 else rows
        bundles = []
        for row in deduped:
            page = self._resolve_row_page(row, pages)
            if page is None:
                ok = False
                self._log_response(
                    "row_source_failure", "invalid_page_or_excerpt", raw, item, mode, attempt
                )
                continue
            text = page["content"]
            source = page["source_url"]
            metadata = page.get("local_source_metadata")
            original = page["observation_text"]
            bundles.append((row, text, source, metadata, mode, original,
                            page.get("page_id", ""), page.get("source_urls", []),
                            page.get("referring_page")))
        return bundles, ok

    @staticmethod
    def _resolve_row_page(
        row: dict[str, Any],
        pages: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        """校验声明页及其摘录；多页缺失或含糊引用交由拆包重放。"""
        if not pages:
            return None
        if len(pages) == 1:
            # 来源唯一时沿用提交层逐字段定位，保留可恢复的原文支持。
            return pages[0]
        tag = row.get("_source_page")
        if isinstance(tag, bool) or not isinstance(tag, (int, str)):
            return None
        if not str(tag).strip().isdecimal():
            return None
        idx = int(str(tag).strip())
        if not 1 <= idx <= len(pages):
            return None
        page = pages[idx - 1]
        from searchos.socm.evidence.provenance import find_span

        excerpt = str(row.get("_source_excerpt", "") or "").strip()
        if not excerpt:
            return None
        fragments = [part for part in re.split(r"\s*(?:…+|\.{3,})\s*", excerpt) if part]
        texts = (page["content"], page.get("observation_text", page["content"]))
        if not fragments or not all(
            find_span(text, fragment, browser_lines=True)[0] is not None
            for text in texts for fragment in fragments
        ):
            return None
        return page

    def _log_response(
        self, kind: str, reason: str, raw: str, item: dict, mode: str, attempt: int
    ) -> None:
        if self._trajectory_logger:
            self._trajectory_logger._append_raw(
                {
                    "type": "harness",
                    "kind": kind,
                    "mode": mode,
                    "reason": reason,
                    "attempt": attempt + 1,
                    "source": (item.get("source_url") or "")[:200],
                    "page_chars": len(item.get("content") or ""),
                    "raw_head": raw[:200],
                }
            )

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

        def quality(row, column):
            alignment = row.get("_alignment", "full")
            if isinstance(alignment, dict):
                alignment = alignment.get(column, "partial")
            return rank.get(str(alignment).lower(), 0)

        def covers(left, right):
            return facts(right) <= facts(left) and all(
                quality(left, column) >= quality(right, column) for column, _ in facts(right)
            )

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
            if any(covers(old, row) for old in kept):
                continue
            kept[:] = [
                old for old in kept if not covers(row, old)
            ]
            kept.append(row)
        return [row for rows in groups.values() for row in rows]

    @staticmethod
    def _parse_findings(raw: str) -> list[dict] | None:
        try:
            return parse_object_array(raw)
        except ValueError:
            return None

    @staticmethod
    def strip_row_metadata(row: dict[str, Any]) -> dict[str, Any]:
        return {str(key): value for key, value in row.items() if not str(key).startswith("_")}
