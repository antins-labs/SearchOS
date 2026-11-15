"""Coverage 的统计与单元格只读窗口。"""

from __future__ import annotations

import json
from collections import Counter
from typing import Any

from langchain_core.tools import tool

from searchos.tools.search_state import _ws
from searchos.socm.refs import RowRef, cell_ref, cell_key, row_ref

_MAX_CELL_LIMIT = 200
_EVIDENCE_IDS_PER_CELL = 5

def _cell_snapshot(cell_key: str, cell: Any) -> dict[str, Any]:
    ev_ids = list(cell.supporting_evidence_ids)
    return {
        "cell": cell_ref(cell_key),
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
    from searchos.socm.views.snapshot import SearchStateSnapshot
    snap = SearchStateSnapshot.from_state(state)
    tables = [{"table_id": t.table_id, "table_label": t.label, **t.summary()} for t in snap.tables]
    by_status = Counter()
    for table in tables:
        by_status.update(table["by_status"])
    gaps = [(t.table_id, r.entity, len(r.missing_cols)) for t in snap.tables for r in t.rows
            if r.missing_cols]
    return {
        "total": sum(by_status.values()), "by_status": dict(by_status), "tables": tables,
        "completed_cells": sum(t["completed_cells"] for t in tables),
        "by_attribute": [{"table_id": t["table_id"], "attribute": attr, **counts}
                         for t in tables for attr, counts in t["by_attribute"].items()],
        "worst_entities": [{"row": row_ref(tid, e), "missing": n}
                           for tid, e, n in sorted(gaps, key=lambda item: -item[2])[:10]],
        "conflict_cells": [cell_ref(cell_key(t.table_id, r.entity, c.attr)) for t in snap.tables
                           for r in t.rows for c in r.cells
                           if c.has_conflict or c.conflict_status == "confirmed"][:20],
    }


@tool(parse_docstring=True)
async def read_coverage(
    mode: str = "summary",
    status: str = "",
    row: RowRef | None = None,
    attribute: str = "",
    limit: int = 60,
    offset: int = 0,
) -> str:
    """Read coverage across result tables. Start with the summary and use filtered cell pages to
    investigate gaps or conflicts.

    Args:
        mode: "summary" returns total, completed_cells, by_status, tables, by_attribute,
            worst_entities and conflict_cells. "cells" returns cells, count, total_matched and
            next_offset. Each cell includes its reference, status, up to five evidence_ids and the
            full evidence_count.
        status: In cells mode filter by missing, filled, uncertain or hard_cell. Omit to include
            all statuses.
        row: Optional exact RowRef {table_id,key} for cells mode. Supply key values in primary_key
            order.
        attribute: Exact column name for cells mode. Omit to include all data columns.
        limit: Maximum cells per page, default 60, capped at 200.
        offset: Starting index in cells mode. Use next_offset to continue.
    """
    state = _ws().load_state()
    if mode != "cells":
        return json.dumps(coverage_summary(state), ensure_ascii=False)

    matched = []
    cmap = state.coverage_map
    for tid, table in cmap.tables.items():
        for ent in sorted(table.entities):
            if row and (tid != row.table_id or ent != cmap.resolve_entity(row.row_key(), table_id=tid)):
                continue
            for attr in table.data_columns:
                if attribute and attr != attribute:
                    continue
                key = cmap.cell_key(tid, ent, attr)
                cell = cmap.cells.get(key)
                if cell is not None and (not status or cell.status.value == status):
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


read_coverage.args_schema.model_config["extra"] = "forbid"
read_coverage.args_schema.model_rebuild(force=True)
