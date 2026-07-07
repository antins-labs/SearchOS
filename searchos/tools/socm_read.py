"""SOCM read-only view tools for Writer agents.

Plan §4.2 "SOCM 只读视图工具". These are windowed projections of the
search state — the agent never touches the live objects, only a JSON
snapshot taken at tool-call time. Writes go through separate writer
tools that the Extraction Middleware mediates.

Returned payloads are plain JSON strings so any LLM tool runtime can
parse without extra plumbing. Filters are kept flat and optional so the
agent can call ``read_coverage()`` for a quick glance or
``read_coverage(status='uncertain')`` to target remediation work.
"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.tools import tool

from searchos.socm.views.trace import resolve_cell_provenance as _resolve
from searchos.tools.search_state import _ws


_MAX_CELL_LIMIT = 200
_EVIDENCE_IDS_PER_CELL = 5
_FINDING_EXCERPT_CHARS = 500
_RESOLUTION_EXCERPT_CHARS = 200


def _parse_cell_key(key: str) -> tuple[str, str, str]:
    """Split ``"{table_id}/{entity}.{attribute}"`` (table prefix optional)."""
    table_id, sep, rest = key.partition("/")
    if not sep:
        table_id, rest = "", key
    ent, _, attr = rest.partition(".")
    return table_id, ent, attr


def _cell_snapshot(cell_key: str, cell: Any) -> dict[str, Any]:
    ev_ids = list(cell.supporting_evidence_ids)
    return {
        "cell": cell_key,
        "status": cell.status.value,
        "best_alignment": cell.best_alignment,
        "evidence_ids": ev_ids[:_EVIDENCE_IDS_PER_CELL],
        "evidence_count": len(ev_ids),
        "display_hint": cell.display_hint,
        "has_conflict": cell.has_conflict,
    }


def coverage_summary(state: Any) -> dict[str, Any]:
    """Aggregate coverage statistics — shared by ``read_coverage(mode="summary")``
    and the writer spawn context block. Constant-size w.r.t. entity count."""
    cmap = state.coverage_map
    by_status: dict[str, int] = {}
    by_attr: dict[str, dict[str, int]] = {}
    missing_by_entity: dict[str, int] = {}
    conflict_cells: list[str] = []
    for key, cell in cmap.cells.items():
        st = cell.status.value
        by_status[st] = by_status.get(st, 0) + 1
        _, ent, attr = _parse_cell_key(key)
        a = by_attr.setdefault(attr, {"filled": 0, "missing": 0, "uncertain": 0, "conflicts": 0})
        if st in a:
            a[st] += 1
        if cell.has_conflict:
            a["conflicts"] += 1
            conflict_cells.append(key)
        if st == "missing":
            missing_by_entity[ent] = missing_by_entity.get(ent, 0) + 1
    worst_entities = sorted(missing_by_entity.items(), key=lambda kv: -kv[1])[:10]
    return {
        "total": len(cmap.cells),
        "by_status": by_status,
        "tables": [
            {
                "table_id": tid,
                "table_label": ts.table_label,
                "n_entities": len(ts.entities),
                "n_attributes": len(ts.attributes),
            }
            for tid, ts in cmap.tables.items()
        ],
        "by_attribute": [
            {"attribute": attr, **counts} for attr, counts in sorted(by_attr.items())
        ],
        "worst_entities": [{"entity": e, "missing": n} for e, n in worst_entities],
        "conflict_cells": conflict_cells[:20],
    }


def _node_snapshot(node: Any) -> dict[str, Any]:
    finding = node.finding or ""
    truncated = len(finding) > _FINDING_EXCERPT_CHARS
    return {
        "id": node.id,
        "entity": node.entity,
        "attribute": node.attribute,
        "finding": finding[:_FINDING_EXCERPT_CHARS],
        **({"finding_truncated": True} if truncated else {}),
        "source": node.source,
        "confidence": node.confidence,
        "alignment": node.alignment,
        "page_id": node.page_id,
        "span": (list(node.span) if node.span else None),
        "text_hash": node.text_hash,
        "source_authority": node.source_authority,
        "created_at": node.created_at,
    }


def _task_snapshot(task: Any) -> dict[str, Any]:
    return {
        "id": task.id,
        "kind": task.kind,
        "status": task.status.value,
        "text": task.question,
        "priority": task.priority,
        "target_cells": list(task.target_cells),
        "blocked_by": list(task.blocked_by),
        "attempts": task.attempts,
        "assigned_agent_id": task.assigned_agent_id,
        "created_by": task.created_by,
        "resolution_excerpt": task.resolution[:_RESOLUTION_EXCERPT_CHARS],
        "last_agent_report_excerpt": task.last_agent_report_excerpt,
    }


@tool
async def read_coverage(
    mode: str = "summary",
    status: str = "",
    entity: str = "",
    attribute: str = "",
    limit: int = 60,
    offset: int = 0,
) -> str:
    """Coverage view. ``mode="summary"`` (default) returns aggregate stats only — start here; ``mode="cells"`` returns a paginated cell list (always combine with filters on large tables).

    Args:
        mode (str): ``"summary"`` — ``{total, by_status, tables, by_attribute, worst_entities, conflict_cells}``; ``"cells"`` — ``{cells:[{cell, status, evidence_ids(top5), evidence_count, ...}], count, total_matched, next_offset}``.
        status (str): cells mode — ``"missing"`` | ``"filled"`` | ``"uncertain"`` | ``"hard_cell"`` — empty = no filter.
        entity (str): cells mode — exact entity name — empty = no filter.
        attribute (str): cells mode — exact attribute name — empty = no filter.
        limit (int): cells mode page size (max 200).
        offset (int): cells mode pagination offset.
    """
    state = _ws().load_state()
    if mode != "cells":
        return json.dumps(coverage_summary(state), ensure_ascii=False)

    matched = []
    for key, cell in state.coverage_map.cells.items():
        _, ent, attr = _parse_cell_key(key)
        if status and cell.status.value != status:
            continue
        if entity and ent != entity:
            continue
        if attribute and attr != attribute:
            continue
        matched.append((key, cell))
    limit = max(1, min(int(limit), _MAX_CELL_LIMIT))
    offset = max(0, int(offset))
    page = matched[offset : offset + limit]
    next_offset = offset + len(page) if offset + len(page) < len(matched) else None
    return json.dumps(
        {
            "cells": [_cell_snapshot(k, c) for k, c in page],
            "count": len(page),
            "total_matched": len(matched),
            "next_offset": next_offset,
        },
        ensure_ascii=False,
    )


@tool
async def read_evidence(
    cell: str = "",
    evidence_ids: str = "",
    entity: str = "",
    attribute: str = "",
    max_nodes: int = 40,
) -> str:
    """Fetch evidence records; filters are OR'd except ``entity``+``attribute`` which AND into a column slice. Empty filters = ``max_nodes`` most recent nodes. ``finding`` text is excerpted to 500 chars — use ``resolve_cell_provenance`` for verbatim full text.

    Args:
        cell (str): ``"entity.attribute"`` cell key — returns its ``supporting_evidence_ids``.
        evidence_ids (str): comma-separated ids (e.g. ``"f_abc,f_def"``).
        entity (str): exact entity name; returns all nodes touching it.
        attribute (str): exact attribute name; combine with ``entity`` for a precise slice.
        max_nodes (int): cap on returned records.
    """
    state = _ws().load_state()
    all_nodes = state.evidence_graph.nodes
    by_id = {n.id: n for n in all_nodes}

    ids: set[str] = set()
    if evidence_ids:
        ids.update(x.strip() for x in evidence_ids.split(",") if x.strip())
    if cell:
        target = state.coverage_map.cells.get(cell)
        if target:
            ids.update(target.supporting_evidence_ids)

    if ids:
        selected = [by_id[i] for i in ids if i in by_id]
    elif entity or attribute:
        selected = [
            n for n in all_nodes
            if (not entity or n.entity == entity)
            and (not attribute or n.attribute == attribute)
        ]
    else:
        selected = sorted(all_nodes, key=lambda n: n.created_at)[-max_nodes:]

    selected.sort(key=lambda n: n.created_at)
    if len(selected) > max_nodes:
        selected = selected[-max_nodes:]
    return json.dumps(
        {"nodes": [_node_snapshot(n) for n in selected], "count": len(selected)},
        ensure_ascii=False,
    )


@tool
async def resolve_cell_provenance(
    cell: str = "",
    evidence_id: str = "",
) -> str:
    """Look up verbatim page snippets for a cell or a single evidence id (provide exactly one). Returns ``{records:[{evidence_id, page_id, source_url, snippet, span, text_hash, finding, confidence}], count}``; ``span`` is ``{start_char, end_char}`` when verbatim in the cached page, else null.

    Args:
        cell (str): ``"entity.attribute"`` cell key.
        evidence_id (str): a single evidence id.
    """
    ws = _ws()
    state = ws.load_state()
    records = _resolve(
        state,
        cell=(cell or None),
        evidence_id=(evidence_id or None),
        workspace=ws,
    )
    return json.dumps({"records": records, "count": len(records)}, ensure_ascii=False)


@tool
async def list_frontier(kind: str = "", status: str = "", limit: int = 50) -> str:
    """List frontier tasks with optional kind / status filters, sorted by priority. Each task carries ``resolution_excerpt`` (the dispatched agent's closing report, first 200 chars) — call ``read_task_report`` for the full text.

    Args:
        kind (str): ``"search"`` | ``"write"`` | ``"explore"`` — empty = all kinds.
        status (str): ``"pending"`` | ``"running"`` | ``"completed"`` | ``"blocked"`` | ``"cancelled"`` — empty = all statuses.
        limit (int): cap on returned tasks (default 50).
    """
    state = _ws().load_state()
    tasks = state.frontier.questions
    if kind:
        tasks = [t for t in tasks if t.kind == kind]
    if status:
        tasks = [t for t in tasks if t.status.value == status]
    total = len(tasks)
    tasks = sorted(tasks, key=lambda t: (-t.priority, -t.updated_at))[: max(1, int(limit))]
    return json.dumps(
        {"tasks": [_task_snapshot(t) for t in tasks], "count": len(tasks), "total_matched": total},
        ensure_ascii=False,
    )


@tool
async def read_task_report(task_id: str) -> str:
    """Read the full natural-language report a dispatched agent left on a frontier task: ``resolution`` (closing briefing — findings, dead ends, recommendations) and ``last_agent_report_excerpt`` (failure summary on recycled/cancelled tasks). Use before emitting a new task on the same cells.

    Args:
        task_id (str): frontier task id (from ``list_frontier``).
    """
    state = _ws().load_state()
    task = next((t for t in state.frontier.questions if t.id == task_id), None)
    if task is None:
        return json.dumps({"error": f"task {task_id!r} not found"})
    return json.dumps(
        {
            "task_id": task.id,
            "kind": task.kind,
            "status": task.status.value,
            "question": task.question,
            "target_cells": list(task.target_cells),
            "assigned_agent_id": task.assigned_agent_id,
            "attempts": task.attempts,
            "resolution": task.resolution,
            "last_agent_report_excerpt": task.last_agent_report_excerpt,
        },
        ensure_ascii=False,
    )


def get_socm_read_tools() -> list:
    """Return SOCM read-only view tools for writer wiring."""
    return [read_coverage, read_evidence, resolve_cell_provenance, list_frontier, read_task_report]
