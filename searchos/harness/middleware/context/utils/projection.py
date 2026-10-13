"""把任务目标投影为可读的 SOCM 状态。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from searchos.socm.views.render import render_discovery_view, render_search_agent_view
from searchos.socm.views.snapshot import SearchStateSnapshot
from searchos.util.scope import match_entities_in_task


class TaskProjection:
    def __init__(
        self,
        agent_id: str,
        *,
        task_text: str = "",
        target_table: str = "",
        agent_graphs: Mapping[str, Any] | None = None,
    ) -> None:
        self.agent_id = agent_id
        self.task_text = task_text
        self.target_table = target_table
        self.agent_graphs = agent_graphs

    def __call__(self, state: Any) -> str:
        cmap = getattr(state, "coverage_map", None)
        if cmap is None or not cmap.tables:
            return ""

        snap = SearchStateSnapshot.from_state(state)

        # Sub-agent: resolve target cells to pick the right view
        in_scope_keys, in_scope_ents, task_table_id = self._resolve_agent_target_cells(state)
        if in_scope_keys:
            # 显式目标不得因表或实体未匹配而消失，也不能降级成发现任务。
            matched_keys = {
                f"{table.table_id}/{row.entity}.{cell.attr}"
                for table in snap.tables
                for row in table.rows
                for cell in row.cells
                if f"{table.table_id}/{row.entity}.{cell.attr}" in in_scope_keys
            }
            missing_keys = in_scope_keys - matched_keys
            blocks = []
            if missing_keys:
                import json

                blocks.append(
                    "Unmatched assigned targets (not evidence of completion):\n"
                    + "\n".join(
                        f"- {json.dumps(key, ensure_ascii=False)}" for key in sorted(missing_keys)
                    )
                    + (
                        "\nCheck the task's table, entity and attribute names; "
                        "these targets are not represented in the matched records."
                    )
                )
            for table in snap.tables:
                table_keys = {
                    f"{table.table_id}/{row.entity}.{cell.attr}"
                    for row in table.rows
                    for cell in row.cells
                    if f"{table.table_id}/{row.entity}.{cell.attr}" in matched_keys
                }
                if table_keys:
                    blocks.append(
                        render_search_agent_view(snap, in_scope_ents, table.table_id, table_keys)
                    )
            return "\n\n".join(blocks)
        target_tid = task_table_id
        if target_tid not in cmap.tables:
            target_tid = self.target_table
        if target_tid not in cmap.tables:
            target_tid = cmap.primary_table_id

        target_ts = cmap.tables[target_tid]
        is_column_only = (
            getattr(getattr(target_ts, "schema_mode", None), "value", "") == "column_only"
        )

        if not in_scope_ents and is_column_only:
            siblings = self._collect_sibling_agents_on_table(target_tid)
            return render_discovery_view(snap, target_tid, siblings)

        return render_search_agent_view(snap, in_scope_ents, target_tid, in_scope_keys or None)

    def _resolve_agent_target_cells(self, state: Any) -> tuple[set[str], set[str], str]:
        """返回目标单元格、实体集合及表 ID。
        优先读取任务的 target_cells，否则从任务文本匹配表内实体。
        """
        if not self.agent_id:
            return set(), set(), ""

        target_cells: list[str] = []
        task_table_id = ""
        assigned_task_text = ""
        try:
            tasks = list(getattr(state.frontier, "questions", []) or [])
        except Exception:
            tasks = []
        for t in tasks:
            if getattr(t, "assigned_agent_id", "") == self.agent_id:
                target_cells = list(getattr(t, "target_cells", []) or [])
                task_table_id = getattr(t, "table_id", "") or ""
                assigned_task_text = (
                    getattr(t, "task_prompt", "") or getattr(t, "question", "") or ""
                )
                break

        if target_cells:
            cmap = state.coverage_map
            keys: set[str] = set()
            for raw in target_cells:
                if raw in cmap.cells:
                    keys.add(raw)
                    continue
                resolved: set[str] = set()
                # 支持工具契约中的 Entity.Attribute，以及复合主键首分量的整组目标。
                for tid, table in cmap.tables.items():
                    qualified = raw.startswith(f"{tid}/")
                    if task_table_id and tid != task_table_id and not qualified:
                        continue
                    short = raw[len(tid) + 1 :] if qualified else raw
                    for attr in table.attributes:
                        suffix = f".{attr}"
                        if not short.endswith(suffix):
                            continue
                        entity = short[: -len(suffix)]
                        exact = [e for e in table.entities if e == entity]
                        selected = exact or [
                            e for e in table.entities if "|" in e and e.split("|", 1)[0] == entity
                        ]
                        resolved.update(cmap.cell_key(tid, e, attr) for e in selected)
                keys.update(resolved or {raw})
            matches = [
                (tid, ent)
                for tid, ts in state.coverage_map.tables.items()
                for ent in ts.entities
                for attr in ts.attributes
                if state.coverage_map.cell_key(tid, ent, attr) in keys
            ]
            tids = {tid for tid, _ in matches}
            if not task_table_id and len(tids) == 1:
                task_table_id = next(iter(tids))
            return keys, {ent for _, ent in matches}, task_table_id

        task_text = self.task_text or assigned_task_text
        ctx_tid = self.target_table
        if not task_text:
            return set(), set(), task_table_id

        cmap = getattr(state, "coverage_map", None)
        if cmap is None:
            return set(), set(), task_table_id
        tid = task_table_id or ctx_tid or cmap.primary_table_id
        if tid not in getattr(cmap, "tables", {}):
            return set(), set(), task_table_id
        ts = cmap.tables[tid]
        entities = list(getattr(ts, "entities", []) or [])
        if not entities:
            return set(), set(), tid

        ents = match_entities_in_task(task_text, entities, require_first_component=True)
        if not ents:
            return set(), set(), tid

        cell_keys = {
            cmap.cell_key(tid, ent, attr)
            for ent in ents
            for attr in ts.attributes
            if attr not in (ts.primary_key or [])
        }
        return cell_keys, ents, tid

    def _collect_sibling_agents_on_table(
        self,
        target_tid: str,
        max_chars: int = 80,
    ) -> list[tuple[str, str]]:
        """Return ``[(agent_id, scope_summary), ...]`` for all active
        sub-agents on the same table, excluding ourselves. ``scope_summary``
        is the first ``max_chars`` of the sibling's task text (single-
        line, with trailing whitespace collapsed). Returns ``[]`` if the
        orchestrator's agent_graphs ContextVar isn't reachable.
        """
        graphs = self.agent_graphs if self.agent_graphs is not None else {}
        if not graphs:
            return []
        out: list[tuple[str, str]] = []
        for aid, info in graphs.items():
            if aid == self.agent_id:
                continue
            atype = info.get("agent_type", "")
            if atype not in {"search_agent", "local_search_agent"}:
                continue
            their_table = info.get("target_table", "") or ""
            # Match only sibling agents bound to the same table. When
            # their_table is empty (the orchestrator didn't specify a
            # table), don't treat it as cross-table — keep the sibling.
            if their_table != target_tid and their_table != "":
                continue
            task = (info.get("task", "") or "").strip()
            if not task:
                continue
            scope = " ".join(task.split())[:max_chars]
            if len(task) > max_chars:
                scope += "…"
            out.append((aid, scope))
        return out
