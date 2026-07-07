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
)


# ---------------------------------------------------------------------------
# Orchestrator view
# ---------------------------------------------------------------------------

def render_orchestrator_view(snap: SearchStateSnapshot) -> str:
    lines: list[str] = ["[Table fill state — KNOWN rows only]"]

    lines.append(
        f"- Known rows: {snap.total_rows} (seeded/discovered), "
        f"{snap.rows_with_gaps} with missing/uncertain columns"
    )
    if snap.total_rows and not snap.rows_with_gaps:
        lines.append(
            "- ⚠️ All KNOWN rows are filled — NOT proof the task is "
            "complete: this view only counts rows already in the schema. "
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

    for ts in snap.tables:
        _render_orch_table(lines, ts)

    _render_frontier(lines, snap.frontier)

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

    complete = ts.complete_rows
    partial = ts.partial_rows
    empty = ts.empty_rows

    lines.append("")
    if ts.is_open_set:
        lines.append(
            f"### `{ts.table_id}` ({ts.label}) — pk={ts.primary_key or '?'} "
            f"— OPEN SET: {len(ts.rows)} rows discovered, "
            f"{len(partial) + len(empty)} with gaps"
        )
    else:
        lines.append(
            f"### `{ts.table_id}` ({ts.label}) — pk={ts.primary_key or '?'} "
            f"— {len(ts.rows)} rows, "
            f"{len(partial) + len(empty)} with gaps"
        )
    if ts.data_columns:
        lines.append(f"Data columns: {ts.data_columns}")

    # Group partial rows by gap signature
    from collections import OrderedDict
    partial_groups: OrderedDict[tuple[str, ...], list[str]] = OrderedDict()
    for r in partial:
        sig = tuple(r.missing_cols)
        partial_groups.setdefault(sig, []).append(r.entity)

    for missing_sig, ents in sorted(partial_groups.items(), key=lambda kv: -len(kv[1])):
        n_data = len(ts.data_columns)
        n_filled = n_data - len(missing_sig)
        lines.append(
            f"- ⚠️ {len(ents)} rows ({n_filled}/{n_data} columns filled) "
            f"— still missing: [{', '.join(missing_sig)}]"
        )
        lines.append("    " + ", ".join(ents))

    if empty:
        lines.append(f"- ❌ {len(empty)} rows with NO data yet")
        lines.append("    " + ", ".join(r.entity for r in empty))

    if complete:
        if ts.is_open_set:
            lines.append(
                f"- {len(complete)} discovered rows have all data columns filled "
                "(open set — row completeness vs task scope NOT verified)"
            )
        else:
            lines.append(f"- {len(complete)} rows have all data columns filled")


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
            "worked; do NOT re-enqueue the same target, wait for results:"
        )
        for rt in fr.running_tasks[:10]:
            tbl = f"`{rt.table_id}` " if rt.table_id else ""
            tgt = f" → cells: {', '.join(rt.targets)}" if rt.targets else ""
            lines.append(f"  - [{rt.agent_id}] {tbl}{rt.text}{tgt}")
        if len(fr.running_tasks) > 10:
            lines.append(f"  - …+{len(fr.running_tasks) - 10} more running")


# ---------------------------------------------------------------------------
# Search agent view (task-scoped)
# ---------------------------------------------------------------------------

def render_search_agent_view(
    snap: SearchStateSnapshot,
    in_scope_entities: set[str],
    target_table_id: str,
) -> str:
    ts = _find_table(snap, target_table_id)
    if ts is None:
        return ""

    lines: list[str] = ["[Coverage state — your task targets]"]
    lines.append(
        f"### Target table: `{ts.table_id}` ({ts.label}) "
        f"— pk={ts.primary_key or '?'}"
    )

    in_scope = [r for r in ts.rows if r.entity in in_scope_entities]
    if not in_scope:
        lines.append("- (no matching rows found for your task yet)")
        return "\n".join(lines)

    lines.append("")
    lines.append("### Your rows")

    empty_ents: list[str] = []
    for r in in_scope:
        if r.is_complete:
            vals = ", ".join(
                f'{c.attr}="{c.display_hint}"'
                for c in r.cells if c.display_hint
            )
            lines.append(f"- {r.entity}: filled ✓" + (f" ({vals})" if vals else ""))
            continue
        if r.is_empty:
            empty_ents.append(r.entity)
            continue
        # Partial: show filled values + missing columns
        filled_parts: list[str] = []
        missing_parts: list[str] = []
        for c in r.cells:
            if c.status == "filled" and c.display_hint:
                filled_parts.append(f'{c.attr}="{c.display_hint}"')
            elif c.status == "hard_cell":
                continue
            elif c.status == "uncertain" and c.display_hint:
                missing_parts.append(f"{c.attr} = 待确认 \"{c.display_hint}\"")
            else:
                missing_parts.append(f"{c.attr} = MISSING")
        identity = "; ".join(filled_parts) if filled_parts else "no data yet"
        lines.append(f"- {r.entity} ({identity}):")
        for mp in missing_parts:
            lines.append(f"    {mp}")

    if empty_ents:
        lines.append(
            f"- [{len(empty_ents)} rows with all columns MISSING] "
            + ", ".join(empty_ents)
        )

    # Other tables summary
    other = [t for t in snap.tables if t.table_id != target_table_id]
    if other:
        lines.append("")
        lines.append("### Other tables")
        for ot in other:
            filled_count = len(ot.complete_rows)
            lines.append(
                f"- `{ot.table_id}` ({ot.label}): "
                f"{filled_count}/{len(ot.rows)} rows filled"
            )

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
        gaps = [
            f"{t.table_id}/{r.entity}.{c.attr}"
            for t in snap.tables for r in t.rows
            for c in r.cells if c.status == "missing"
        ][:10]
        if gaps:
            lines.append(f"Gaps: {', '.join(gaps)}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_table(snap: SearchStateSnapshot, table_id: str) -> TableSnapshot | None:
    for t in snap.tables:
        if t.table_id == table_id:
            return t
    return snap.tables[0] if snap.tables else None
