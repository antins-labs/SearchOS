"""SOCM view renderers — pure functions from SearchStateSnapshot to text.

Each function targets one consumer (orchestrator, search agent, extraction
judge, …); all share the same ``SearchStateSnapshot`` input so the underlying
data is computed once. This is the role-specific projection φ(M) (paper §SOCM).
"""

from __future__ import annotations

import json

from searchos.socm.coverage.models import cell_is_actionable, cell_is_complete
from searchos.socm.evidence.missing_values import is_null_marker
from searchos.socm.refs import cell_key, cell_ref, row_values
from searchos.socm.views.snapshot import (
    CellInfo,
    FrontierSnapshot,
    RowStatus,
    SearchStateSnapshot,
    TableSnapshot,
)


def _has_unresolved_attributes(row: RowStatus) -> bool:
    return not row.is_complete


def render_cell(cell: CellInfo, value: str | None, *, with_values: bool = True,
                include_tasks: bool = False, citation: dict | None = None):
    """行窗口与工具回执共用单元格状态；引用和任务归属按需附加。"""
    status = "unavailable" if cell.status == "hard_cell" else cell.status
    if cell.has_conflict or cell.conflict_status == "confirmed":
        status = "conflict"
    elif status == "missing" and cell.conflict_status == "clear":
        value = None
    meta = {}
    if cell.inferred:
        meta["inferred"] = True
    if status not in {"missing", "filled"} or (status == "filled" and value is None and with_values):
        meta["status"] = status
    if cell.conflict_status in {"pending", "uncertain"}:
        meta["comparison"] = cell.conflict_status
    if include_tasks and cell.active_task_ids:
        meta["active_task_ids"] = cell.active_task_ids
    if citation and value is not None:
        meta.update(citation)
    if with_values:
        if not meta:
            return value
        if value is None and meta == {"status": "filled"}:
            return meta
        return {"value": value, **meta}
    return {"status": status, **meta} if meta else status


def _row_values(ts: TableSnapshot, row: RowStatus) -> list:
    """每行仅展示列值，特殊状态附在对应单元格。"""
    values = ([row.key_values.get(attr, "") for attr in ts.primary_key]
              if ts.primary_key else row_values(row.entity))
    values.extend(render_cell(cell, cell.display_hint or None) for cell in row.cells)
    return values


def _render_rows(lines: list[str], ts: TableSnapshot, rows: list[RowStatus], *, header=True) -> None:
    if header:
        lines.append("Columns: " + json.dumps((ts.primary_key or ["Entity"]) + ts.data_columns,
                                              ensure_ascii=False))
        lines.append("""Rows follow column order; null = missing.""")
    lines.extend(json.dumps(_row_values(ts, row), ensure_ascii=False) for row in rows)


# ---------------------------------------------------------------------------
# Orchestrator view
# ---------------------------------------------------------------------------


def render_orchestrator_view(snap: SearchStateSnapshot) -> str:
    tasks = render_task_evidence(snap)
    lines: list[str] = [tasks] if tasks else []
    if not snap.tables:
        return "\n".join(lines)
    lines.append("""[Table fill state]""")
    unresolved_rows = sum(bool(_has_unresolved_attributes(r)) for t in snap.tables for r in t.rows)

    lines.append(
        f"""- Known rows: {snap.total_rows}, {unresolved_rows} with unresolved columns"""
    )
    for ts in snap.tables:
        _render_orch_table(lines, ts)

    return "\n".join(lines)


def _placeholder_pk_fields(ts: TableSnapshot, row: RowStatus) -> list[str]:
    if not ts.primary_key:
        return []
    return [
        attr for attr in ts.primary_key
        if is_null_marker(row.key_values.get(attr, ""))
    ]


def _discover_candidates_for_placeholder(
    ts: TableSnapshot, placeholder: RowStatus, missing_attrs: list[str],
) -> list[list[str]]:
    """Rows that match the placeholder on non-placeholder PK fields (rename hints only)."""
    if not ts.primary_key or not missing_attrs:
        return []
    fixed = {
        attr: placeholder.key_values.get(attr, "")
        for attr in ts.primary_key
        if attr not in missing_attrs
    }
    if not fixed:
        return []
    hints: list[list[str]] = []
    for row in ts.rows:
        if row.entity == placeholder.entity:
            continue
        if any(is_null_marker(row.key_values.get(attr, "")) for attr in missing_attrs):
            continue
        if any(row.key_values.get(attr, "") != value for attr, value in fixed.items()):
            continue
        hints.append([row.key_values.get(attr, "") for attr in ts.primary_key])
        if len(hints) >= 5:
            break
    return hints


def _render_placeholder_row_hints(lines: list[str], ts: TableSnapshot) -> None:
    """Flag placeholder-PK rows and list discover candidates; Orchestrator decides rename."""
    placeholders = []
    for row in ts.rows:
        missing = _placeholder_pk_fields(ts, row)
        if not missing:
            continue
        pk = [row.key_values.get(attr, "") for attr in ts.primary_key]
        candidates = _discover_candidates_for_placeholder(ts, row, missing)
        placeholders.append({
            "row": pk,
            "placeholder_fields": missing,
            "discover_candidates": candidates,
        })
    if not placeholders:
        return
    lines.append(
        "Placeholder primary-key rows (use edit_entities rename when a discover "
        "candidate is the same product; do not auto-merge distinct specs):"
    )
    lines.append(json.dumps(placeholders, ensure_ascii=False))


def _render_orch_table(
    lines: list[str], ts: TableSnapshot, *, reader: str = "inspect_table",
) -> None:
    incomplete = [r for r in ts.rows if _has_unresolved_attributes(r)]
    mode = "discovery" if ts.is_open_set else "seeded"
    lines.extend(
        [
            "",
            f"""### `{ts.table_id}` ({ts.label}) — mode={mode}""",
            f"""Rows: {len(ts.rows)}; rows with unresolved attributes: {len(incomplete)}; filled rows: {len(ts.rows) - len(incomplete)}.""",
        ]
    )
    summary = ts.summary()
    if ts.inferred_columns:
        lines.append(f"""Fill from known row facts with edit_entities: {json.dumps(ts.inferred_columns, ensure_ascii=False)}""")
    lines.append("Cell totals: " + json.dumps({k: v for k, v in summary.items()
                  if k not in {"total_rows", "filled_rows", "unresolved_rows", "by_attribute"}}))
    lines.append("Fields: " + json.dumps(summary["by_attribute"], ensure_ascii=False))
    _render_placeholder_row_hints(lines, ts)
    _render_gap_window(lines, ts, reader=reader)


def _render_gap_window(lines: list[str], ts: TableSnapshot, *, reader: str) -> list[RowStatus]:
    rows = [r for r in ts.rows if not r.is_complete]
    rows.sort(key=lambda r: (not any(cell_is_actionable(c) and not c.active_task_ids
                                    for c in r.cells), r.entity))
    lines.append(f"""Gap rows shown: {min(30, len(rows))}/{len(rows)}; details: {reader}.""")
    _render_rows(lines, ts, rows[:30])
    return rows[:30]


def _render_frontier(lines: list[str], fr: FrontierSnapshot) -> None:
    if not fr.by_status:
        return
    lines.append("")
    lines.append(
        f"""### Frontier: {', '.join((f'{k}={v}' for k, v in sorted(fr.by_status.items(), key=lambda x: -x[1])))}"""
    )
    if fr.open_by_kind:
        lines.append(
            f"""  open by kind: {', '.join((f'{k}={v}' for k, v in sorted(fr.open_by_kind.items(), key=lambda x: -x[1])))}"""
        )


# ---------------------------------------------------------------------------
# Search agent view (task-scoped)
# ---------------------------------------------------------------------------


def render_search_agent_view(
    snap: SearchStateSnapshot,
    in_scope_entities: set[str],
    target_table_id: str,
    target_cells: set[str] | None = None,
) -> str:
    """按目标单元格展示实体、缺口及已记录值，供 Agent 核对。"""
    ts = next((t for t in snap.tables if t.table_id == target_table_id), None)
    if ts is None:
        return ""
    targets = []
    scoped_rows = []
    for row in ts.rows:
        if target_cells is None and row.entity not in in_scope_entities:
            continue
        cells = [
            c
            for c in row.cells
            if (target_cells is None and c.requires_search) or (
                target_cells is not None and cell_key(ts.table_id, row.entity, c.attr) in target_cells)
        ]
        if cells:
            scoped_rows.append(row)
            targets.extend((cell_key(ts.table_id, row.entity, c.attr), c) for c in cells)
    remaining = [(key, c) for key, c in targets if cell_is_actionable(c, explicit_target=target_cells is not None)]
    unavailable = sum(c.status == "hard_cell" for _, c in targets)
    completed = sum(cell_is_complete(c) for _, c in targets)
    pending = sum(c.conflict_status == "pending" for _, c in targets)
    lines = [
        """[Coverage state — your task targets]""",
        f"""### Target table: `{ts.table_id}` ({ts.label})""",
        f"""Assigned cells: {len(targets)}; filled: {completed}; actionable gaps: {len(remaining)}; unavailable: {unavailable}.""",
        f"""Pending evidence comparisons: {pending}.""",
    ]
    if not targets:
        lines.append("""Target match: none.""")
    lines.append("""Target records:""")
    _render_rows(lines, ts, scoped_rows)
    if target_cells is not None:
        offset = len(ts.primary_key) or 1
        selection = [[i, [offset + j for j, c in enumerate(row.cells)
                           if cell_key(ts.table_id, row.entity, c.attr) in target_cells]]
                     for i, row in enumerate(scoped_rows)]
        lines.append(f"""Assigned targets [row index, column indices] (zero-based): {json.dumps(selection)}""")
    described = {c.attr for row in scoped_rows for c in row.cells}
    definitions: dict[str, list[str]] = {}
    for attr in sorted(described):
        desc = ts.column_descriptions.get(attr, "")
        if desc:
            definitions.setdefault(desc, []).append(attr)
    if definitions:
        lines.append("""Column definitions:""")
        for desc, columns in definitions.items():
            lines.append(f"""- {json.dumps(columns, ensure_ascii=False)}: {desc}""")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Discovery view (column_only, no in-scope entities)
# ---------------------------------------------------------------------------


def render_discovery_view(
    snap: SearchStateSnapshot,
    target_table_id: str,
    sibling_agents: list[tuple[str, str]],
) -> str:
    ts = _find_table(snap, target_table_id)
    if ts is None:
        return ""

    lines: list[str] = ["""[Coverage state — your task targets]"""]
    lines.append(f"""### Target table: `{ts.table_id}` ({ts.label})""")
    if ts.inferred_columns:
        lines.append(f"""The orchestrator fills these columns: {json.dumps(ts.inferred_columns, ensure_ascii=False)}""")
    lines.append(
        f"""- {len(ts.rows)} rows discovered so far, {len(ts.complete_rows)} with all columns filled"""
    )

    lines.append(f"""Table totals: {json.dumps(ts.summary(), ensure_ascii=False)}""")
    gap_entities = {row.entity for row in
                    _render_gap_window(lines, ts, reader="""Main Agent via inspect_table""")}
    by_entity = {r.entity: r for r in ts.rows}
    recent = [by_entity[e] for e in ts.recent_entities if e not in gap_entities]
    lines.append(f"""Additional recent rows shown: {len(recent)}; latest window: {len(ts.recent_entities)}/{len(ts.rows)}.""")
    _render_rows(lines, ts, recent, header=False)

    if sibling_agents:
        lines.append("")
        lines.append("""### Other agents on this table""")
        for agent_id, scope in sibling_agents:
            lines.append(f"""- `{agent_id}`: {scope}""")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Extraction judge views (row inventory for coverage-aware extraction)
# ---------------------------------------------------------------------------

# All extraction-view caps are ROW COUNTS — no char budgets.
_SNAPSHOT_MAX_ROWS = 200  # max incomplete rows listed (with MISSING columns)
_SNAPSHOT_COMPLETE_CAP = 100  # max complete rows as dedup anchors (merged view)
_PK_LIST_MAX_ROWS = 500  # DISCOVER-mode PK inventory cap (compact lines)


def render_extraction_snapshot(
    snap: SearchStateSnapshot, target_table_id: str, target_cells: set[str] | None = None,
) -> str:
    ts = _find_table(snap, target_table_id)
    if ts is None:
        return "(no table)"

    if ts.is_empty:
        columns = [c for c in ts.data_columns if c not in ts.inferred_columns]
        return f"""(table is empty — every row you identify will be added as new; {len(columns)} data column(s): {columns})"""

    incomplete = _extraction_rows(ts, target_cells)
    complete = ts.complete_rows

    lines = [
        f"""Existing rows: {len(ts.rows)} total — {len(complete)} complete, {len(incomplete)} incomplete."""
    ]
    _render_extraction_rows(lines, ts, incomplete)

    if complete:
        display = complete[-_SNAPSHOT_COMPLETE_CAP:]
        omitted = len(complete) - len(display)
        compact = json.dumps([[row.key_values.get(attr, "") for attr in ts.primary_key]
                              for row in display], ensure_ascii=False)
        if omitted:
            header = f"""Complete rows (latest {len(display)}/{len(complete)}; primary-key column order): """
        else:
            header = """Complete rows (primary-key column order): """
        lines.append(header + compact)

    return "\n".join(lines)


def render_fill_snapshot(
    snap: SearchStateSnapshot, target_table_id: str, target_cells: set[str] | None = None,
) -> str:
    """FILL-mode view: incomplete rows only, with their MISSING columns.
    Returns "" when there are none — callers skip the fill judge call."""
    ts = _find_table(snap, target_table_id)
    if ts is None or ts.is_empty:
        return ""
    incomplete = _extraction_rows(ts, target_cells)
    if not incomplete:
        return ""

    lines = [
        f"""Rows with empty columns: {len(incomplete)} (of {len(ts.rows)} total)."""
    ]
    _render_extraction_rows(lines, ts, incomplete)
    return "\n".join(lines)


def _extraction_rows(
    ts: TableSnapshot, target_cells: set[str] | None,
) -> list[tuple[RowStatus, list[str]]]:
    rows = []
    for row in ts.rows:
        attrs = [c.attr for c in row.cells if cell_is_actionable(c, explicit_target=target_cells is not None)
                 and (target_cells is None or cell_key(ts.table_id, row.entity, c.attr) in target_cells)]
        if attrs:
            rows.append((row, attrs))
    return rows


def _render_extraction_rows(
    lines: list[str], ts: TableSnapshot, rows: list[tuple[RowStatus, list[str]]],
) -> None:
    _render_rows(lines, ts, [row for row, _ in rows])
    offset = len(ts.primary_key) or 1
    targets = [[i, [offset + ts.data_columns.index(attr) for attr in attrs]]
               for i, (_, attrs) in enumerate(rows)]
    lines.append(f"""Fill targets [row index, column indices] (zero-based): {json.dumps(targets)}""")


def render_known_pk_list(
    snap: SearchStateSnapshot,
    target_table_id: str,
    *,
    max_rows: int = _PK_LIST_MAX_ROWS,
) -> str:
    """DISCOVER-mode view: compact inventory of every existing PK, no per-row
    fill status — so there's no "form" tempting the judge to fill anything.
    "" for an empty/unknown table (every emitted row is then new)."""
    ts = _find_table(snap, target_table_id)
    if ts is None or ts.is_empty:
        return ""
    pks = [[r.key_values.get(attr, "") for attr in ts.primary_key]
           if ts.primary_key else row_values(r.entity) for r in ts.rows]
    header = f"""Known rows: {len(pks)}; keys in schema primary-key column order: """
    if len(pks) <= max_rows:
        return header + json.dumps(pks, ensure_ascii=False)
    return f"""{header}{json.dumps(pks[:max_rows], ensure_ascii=False)} … and {len(pks) - max_rows} more existing row(s) (protected by ingest-time dedup)."""


# ---------------------------------------------------------------------------
# Compact summary (Layer 3 frozen prefix)
# ---------------------------------------------------------------------------


def render_compact_summary(snap: SearchStateSnapshot) -> str:
    tasks = render_task_evidence(snap)
    if not snap.tables:
        return tasks
    lines = ["""[SEARCH STATE SUMMARY]"""]
    if tasks:
        lines.append(tasks)

    total_cells = sum(len(r.cells) for t in snap.tables for r in t.rows)
    filled_cells = sum(
        1 for t in snap.tables for r in t.rows for c in r.cells if cell_is_complete(c)
    )
    if total_cells:
        pct = filled_cells / total_cells
        lines.append(f"""Coverage: {pct:.0%} ({filled_cells}/{total_cells})""")
    for table in snap.tables:
        _render_orch_table(lines, table, reader="""read_coverage / read_evidence""")

    return "\n".join(lines)


def render_task_evidence(snap: SearchStateSnapshot, task_ids: set[str] | None = None) -> str:
    """展示任务及可用的无表证据；task_ids 用于子任务隔离。"""
    import json

    tasks = [t for t in snap.task_evidence if task_ids is None or t["task_id"] in task_ids]
    findings = [
        f for f in snap.findings if task_ids is None or task_ids.intersection(f["task_ids"])
    ]
    if not tasks and not findings:
        return ""
    lines = ["""[Research tasks and evidence]"""]
    if task_ids is None:
        _render_frontier(lines, snap.frontier)
        running = [t for t in tasks if t["status"] == "running"]
        queued = sorted((t for t in tasks if t["status"] in {"pending", "blocked"}),
                        key=lambda t: (-t["priority"], t["task_id"]))[:20]
        ended = sorted((t for t in tasks if t["status"] in {"completed", "cancelled"}),
                       key=lambda t: (-t["updated_at"], t["task_id"]))[:5]
        shown = running + queued + ended
        lines.append(f"""Tasks shown: {len(shown)}/{len(tasks)}; details: list_frontier.""")
        tasks = shown
    for task in tasks:
        details = [f"""{task['task_id']} ({task['status']})""", f"evidence={task['evidence_count']}"]
        if task_ids is None:
            details.append(task["agent_type"])
            if task["agent_id"]:
                details.append(f"agent={task['agent_id']}")
            if task["table_id"]:
                details.append(f"table={task['table_id']}")
            question = task["question"].strip()
            if question:
                goal = question.splitlines()[0]
                details.append(goal[:120] + ("…" if len(goal) > 120 else ""))
            targets = task["target_cells"]
            if targets:
                details.append("targets=" + json.dumps([cell_ref(key) for key in targets[:4]], ensure_ascii=False)
                               + (f""" (+{len(targets) - 4})""" if len(targets) > 4 else ""))
        lines.append("- " + " | ".join(details))
    for finding in findings:
        lines.append(json.dumps(finding, ensure_ascii=False, sort_keys=True))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _find_table(snap: SearchStateSnapshot, table_id: str) -> TableSnapshot | None:
    for t in snap.tables:
        if t.table_id == table_id:
            return t
    return snap.tables[0] if snap.tables else None
