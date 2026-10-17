"""Coverage 的统计与单元格只读窗口。"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.tools import tool

from searchos.tools.search_state import _ws

_MAX_CELL_LIMIT = 200
_EVIDENCE_IDS_PER_CELL = 5

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
        "conflict_status": cell.conflict_status,
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
