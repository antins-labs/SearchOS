"""SOCM view renderers — pure functions from SearchStateSnapshot to text.

Each function targets one consumer (orchestrator, search agent, extraction
judge, …); all share the same ``SearchStateSnapshot`` input so the underlying
data is computed once. This is the role-specific projection φ(M) (paper §SOCM).
"""

from __future__ import annotations

from searchos.socm.views.snapshot import (
    FrontierSnapshot,
    SearchStateSnapshot,
    TableSnapshot,
    RowStatus,
)


def _has_unresolved_attributes(row: RowStatus) -> bool:
    return any(c.has_conflict or c.status != "filled" for c in row.cells)


def _render_entity_gaps(
    lines: list[str], rows: list[RowStatus], *, include_recorded: bool = False,
) -> None:
    """逐实体展示缺口；状态与候选值同行，不按属性组合分组。"""
    import json

    def quote(value: str) -> str:
        return json.dumps(value, ensure_ascii=False)

    for row in rows:
        missing = []
        recorded = []
        details = []
        for cell in row.cells:
            attr = quote(cell.attr)
            if cell.has_conflict:
                detail = f"{attr} status=conflict"
                if cell.display_hint:
                    detail += f" (current value: {quote(cell.display_hint)})"
                details.append(detail)
            elif cell.conflict_status in {"pending", "uncertain"}:
                details.append(
                    f"{attr} evidence_comparison={cell.conflict_status} "
                    "(not a confirmed conflict; retain source qualifications)"
                )
            elif cell.status == "filled":
                if include_recorded:
                    recorded.append(
                        f"{attr}={quote(cell.display_hint)}" if cell.display_hint
                        else f"{attr} (value preview unavailable)"
                    )
                continue
            elif cell.status == "hard_cell":
                details.append(f"{attr} unavailable")
            elif cell.status == "uncertain":
                detail = f"{attr} status=uncertain"
                if cell.display_hint:
                    detail += f" (candidate: {quote(cell.display_hint)})"
                details.append(detail)
            else:
                missing.append(attr)
        if recorded:
            details.append("recorded " + ", ".join(recorded))
        if missing:
            details.insert(0, "missing " + ", ".join(missing))
        if details:
            lines.append(f"- {quote(row.entity)}: " + "; ".join(details) + ".")


# ---------------------------------------------------------------------------
# Orchestrator view
# ---------------------------------------------------------------------------

def render_orchestrator_view(snap: SearchStateSnapshot) -> str:
    lines: list[str] = []
    if snap.research_mode == "findings":
        lines.extend(["[Research tasks and evidence]",
                      "Task status tracks execution; evidence counts do not measure answer completeness."])
        for task in snap.task_evidence[-50:]:
            lines.append(f"- {task['task_id']} ({task['agent_type']}, {task['result_mode']}, "
                         f"{task['status']}): {task['question']} | "
                         f"{task['evidence_count']} source-supported findings")
        lines.append("Inspect details with read_evidence(task_id=...).")
        if not snap.tables:
            return "\n".join(lines)
    lines.append("[Table fill state — KNOWN rows only]")
    unresolved_rows = sum(bool(_has_unresolved_attributes(r)) for t in snap.tables for r in t.rows)

    lines.append(
        f"- Known rows: {snap.total_rows} (seeded/discovered), "
        f"{unresolved_rows} with unresolved columns"
    )
    if snap.total_rows and not unresolved_rows:
        lines.append(
            "- All known rows are filled. Coverage describes rows already "
            "present in the schema; it does not describe undiscovered rows. "
            "Audit the row set against the query's full scope and "
            "add_entities for anything missing BEFORE final synthesis."
        )
    open_set_tids = [t.table_id for t in snap.tables if t.is_open_set and t.rows]
    if open_set_tids:
        lines.append(
            "- ⚠️ OPEN-SET table(s): "
            + ", ".join(f"`{t}`" for t in open_set_tids)
            + " — counts reflect DISCOVERED rows only."
        )
    empty_tids = [t.table_id for t in snap.tables if t.is_empty]
    if empty_tids:
        lines.append(
            "- ⚠️ EMPTY table(s) with 0 rows: "
            + ", ".join(f"`{t}`" for t in empty_tids)
            + " — dispatch search agents or add_entities to fill them."
        )

    _render_frontier(lines, snap.frontier)
    for ts in snap.tables:
        _render_orch_table(lines, ts)

    return "\n".join(lines)


def _render_orch_table(lines: list[str], ts: TableSnapshot) -> None:
    if ts.is_empty:
        lines.append("")
        lines.append(
            f"### `{ts.table_id}` ({ts.label}) — pk={ts.primary_key or '?'} "
            f"— ⚠️ EMPTY (0 rows)"
        )
        if ts.data_columns:
            lines.append(f"Data columns: {ts.data_columns}")
        return

    incomplete = [r for r in ts.rows if _has_unresolved_attributes(r)]
    lines.extend(["", f"### `{ts.table_id}` ({ts.label}) — pk={ts.primary_key}",
                  f"Rows: {len(ts.rows)}; rows with unresolved attributes: {len(incomplete)}; filled rows: {len(ts.rows) - len(incomplete)}."])
    if ts.is_open_set:
        lines.append("OPEN SET: this view contains discovered rows only; additional rows may exist.")
    _render_entity_gaps(lines, incomplete)


def _render_frontier(lines: list[str], fr: "FrontierSnapshot") -> None:
    if not fr.by_status:
        return
    lines.append("")
    lines.append(
        "### Frontier: "
        + ", ".join(f"{k}={v}" for k, v in
                    sorted(fr.by_status.items(), key=lambda x: -x[1]))
    )
    if fr.open_by_kind:
        lines.append(
            "  open by kind: "
            + ", ".join(f"{k}={v}" for k, v in
                        sorted(fr.open_by_kind.items(), key=lambda x: -x[1]))
        )
    # In-flight tasks: show WHAT each running sub-agent is on, so the
    # orchestrator does not re-dispatch work already covered. A gap that
    # matches a task below is being worked — wait for it, don't re-enqueue.
    if fr.running_tasks:
        lines.append(
            f"  in-flight tasks ({len(fr.running_tasks)}) — already being "
            "worked; do NOT re-enqueue these same targets:"
        )
        for rt in fr.running_tasks[:10]:
            tbl = f"`{rt.table_id}` " if rt.table_id else ""
            tgt = f" → cells: {', '.join(rt.targets)}" if rt.targets else ""
            lines.append(f"  - [{rt.agent_id}] {tbl}{rt.text}{tgt}")
        if len(fr.running_tasks) > 10:
            lines.append(f"  - …+{len(fr.running_tasks) - 10} more running")
        lines.append(
            "  Wait only when your next action depends on a running task's result. "
            "For independent gaps exposed by returned reports, dispatch focused work "
            "now (including Explore for identity or scope uncertainty); do not wait "
            "for unrelated tasks to finish."
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
        cells = [c for c in row.cells if target_cells is None or
                 f"{ts.table_id}/{row.entity}.{c.attr}" in target_cells]
        if cells:
            scoped_rows.append(RowStatus(row.entity, cells))
            targets.extend((f"{ts.table_id}/{row.entity}.{c.attr}", c) for c in cells)
    remaining = [(key, c) for key, c in targets if c.has_conflict or c.status not in ("filled", "hard_cell")]
    unavailable = sum(c.status == "hard_cell" and not c.has_conflict for _, c in targets)
    completed = len(targets) - len(remaining) - unavailable
    lines = ["[Coverage state — your task targets]",
             f"### Target table: `{ts.table_id}` ({ts.label}) — pk={ts.primary_key}",
             f"Assigned cells: {len(targets)}; filled: {completed}; actionable gaps: {len(remaining)}; unavailable: {unavailable}."]
    if not targets:
        lines.append("No matching assigned cells. Follow the explicit task scope; do not expand to unrelated rows or columns.")
    elif not remaining:
        lines.append("No actionable gaps are marked in the matched cells.")
    if unavailable:
        lines.append("Unavailable cells are unresolved limitations, not filled answers; do not retry them without new evidence.")
    lines.append("Target records (recorded values are previews):")
    _render_entity_gaps(lines, scoped_rows, include_recorded=True)
    described = {c.attr for row in scoped_rows for c in row.cells}
    for attr in sorted(described):
        desc = ts.column_descriptions.get(attr, "")
        if desc:
            lines.append(f"Column {attr}: {desc}")
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

    lines: list[str] = ["[Coverage state — your task targets]"]
    lines.append(
        f"### Target table: `{ts.table_id}` ({ts.label}) "
        f"— pk={ts.primary_key or '?'}"
    )
    lines.append(
        f"- {len(ts.rows)} rows discovered so far, "
        f"{len(ts.complete_rows)} with all columns filled"
    )
    if ts.data_columns:
        lines.append(f"- Data columns: {ts.data_columns}")

    _render_entity_gaps(lines, ts.rows)
    import json
    complete_entities = [r.entity for r in ts.rows if not _has_unresolved_attributes(r)]
    lines.append("Collected entities: " + json.dumps(complete_entities, ensure_ascii=False))
    lines.append("Stay within your discovery assignment; reuse known entity keys and avoid duplicating sibling scopes.")

    if sibling_agents:
        lines.append("")
        lines.append("### Other agents on this table")
        for agent_id, scope in sibling_agents:
            lines.append(f"- `{agent_id}`: {scope}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Extraction judge views (row inventory for coverage-aware extraction)
# ---------------------------------------------------------------------------

# All extraction-view caps are ROW COUNTS — no char budgets.
_SNAPSHOT_MAX_ROWS = 200      # max incomplete rows listed (with MISSING columns)
_SNAPSHOT_COMPLETE_CAP = 100  # max complete rows as dedup anchors (merged view)
_PK_LIST_MAX_ROWS = 500       # DISCOVER-mode PK inventory cap (compact lines)


def render_extraction_snapshot(snap: SearchStateSnapshot, target_table_id: str) -> str:
    ts = _find_table(snap, target_table_id)
    if ts is None:
        return "(no table)"

    if ts.is_empty:
        return (
            "(table is empty — every row you identify will be added as "
            f"new; {len(ts.data_columns)} data column(s): {ts.data_columns})"
        )

    incomplete = [(r.entity, r.missing_cols) for r in ts.rows if not r.is_complete]
    complete = [r.entity for r in ts.complete_rows]

    lines = [
        f"Existing rows: {len(ts.rows)} total — {len(complete)} complete, "
        f"{len(incomplete)} incomplete. Data columns: {ts.data_columns}"
    ]
    for entity, missing in incomplete[:_SNAPSHOT_MAX_ROWS]:
        lines.append(f'  "{entity}"  MISSING=[{", ".join(missing)}]')
    if len(incomplete) > _SNAPSHOT_MAX_ROWS:
        lines.append(f"  … and {len(incomplete) - _SNAPSHOT_MAX_ROWS} more incomplete row(s)")

    if complete:
        display = complete[-_SNAPSHOT_COMPLETE_CAP:]
        omitted = len(complete) - len(display)
        compact = ", ".join(f'"{e}"' for e in display)
        if omitted:
            header = (
                f"Complete rows (latest {len(display)}/{len(complete)}; "
                "reuse PK text, do NOT re-extract): "
            )
        else:
            header = "Complete rows (reuse PK text, do NOT re-extract): "
        lines.append(header + compact)

    return "\n".join(lines)


def render_fill_snapshot(snap: SearchStateSnapshot, target_table_id: str) -> str:
    """FILL-mode view: incomplete rows only, with their MISSING columns.
    Returns "" when there are none — callers skip the fill judge call."""
    ts = _find_table(snap, target_table_id)
    if ts is None or ts.is_empty:
        return ""
    incomplete = [(r.entity, r.missing_cols) for r in ts.rows if not r.is_complete]
    if not incomplete:
        return ""

    lines = [
        f"Rows with empty columns: {len(incomplete)} "
        f"(of {len(ts.rows)} total). Data columns: {ts.data_columns}"
    ]
    for entity, missing in incomplete[:_SNAPSHOT_MAX_ROWS]:
        lines.append(f'  "{entity}"  MISSING=[{", ".join(missing)}]')
    if len(incomplete) > _SNAPSHOT_MAX_ROWS:
        lines.append(f"  … and {len(incomplete) - _SNAPSHOT_MAX_ROWS} more incomplete row(s)")
    return "\n".join(lines)


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
    pks = [r.entity for r in ts.rows]
    header = f"Known rows: {len(pks)} — "
    if len(pks) <= max_rows:
        return header + ", ".join(f'"{e}"' for e in pks)
    return (
        header + ", ".join(f'"{e}"' for e in pks[:max_rows])
        + f" … and {len(pks) - max_rows} more existing row(s) "
        "(protected by ingest-time dedup)."
    )


# ---------------------------------------------------------------------------
# Compact summary (Layer 3 frozen prefix)
# ---------------------------------------------------------------------------

def render_compact_summary(snap: SearchStateSnapshot) -> str:
    lines = ["[SEARCH STATE SUMMARY]"]

    total_cells = sum(len(r.cells) for t in snap.tables for r in t.rows)
    filled_cells = sum(
        1 for t in snap.tables for r in t.rows
        for c in r.cells if c.status == "filled"
    )
    if total_cells:
        pct = filled_cells / total_cells
        lines.append(f"Coverage: {pct:.0%} ({filled_cells}/{total_cells})")
    for table in snap.tables:
        lines.append(f"### `{table.table_id}`")
        _render_entity_gaps(lines, table.rows)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_table(snap: SearchStateSnapshot, table_id: str) -> TableSnapshot | None:
    for t in snap.tables:
        if t.table_id == table_id:
            return t
    return snap.tables[0] if snap.tables else None
