"""Evidence 查询与单元格来源追踪。"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.tools import tool

from searchos.socm.coverage import (
    answer_evidence,
    evidence_matches_cell,
    evidence_scope,
    project_cell_evidence,
)
from searchos.socm.evidence.graph import EvidenceStatus
from searchos.socm.evidence.provenance import resolve_cell_provenance as _resolve
from searchos.socm.refs import CellRef, RowRef, cell_ref, row_ref
from searchos.tools.search_state import _ws

_FINDING_EXCERPT_CHARS = 500
_READABLE_SOURCE_FIELDS = (
    "file_name", "ref_id", "tool_ref_id", "location", "source_locator", "locators",
    "text_range", "coverage", "warnings", "extraction_method",
    "representation_id", "representation_selector",
)

def _node_snapshot(node: Any, state: Any = None, *, include_inactive: bool = False) -> dict[str, Any]:
    from searchos.socm.evidence.provenance import evidence_citation, evidence_source_urls

    finding = node.finding or ""
    truncated = len(finding) > _FINDING_EXCERPT_CHARS
    citation = evidence_citation(node)
    urls = evidence_source_urls(node)
    metadata = node.local_source_metadata or {}
    source_details = {key: metadata[key] for key in _READABLE_SOURCE_FIELDS if key in metadata}
    return {
        "id": node.id,
        "status": node.status.value,
        "table_id": node.table_id,
        **(evidence_scope(state, node) if state is not None else {}),
        "row": row_ref(node.table_id or state.coverage_map.primary_table_id, node.entity) if node.entity and state is not None else None,
        "attribute": node.attribute,
        "value": node.value,
        "cell_bindings": ([
            {"cell": cell_ref(key), **binding.model_dump(exclude={"evidence_id"})}
            for key, records in state.coverage_map.evidence_bindings.items()
            for binding in records
            if binding.evidence_id == node.id
            and (include_inactive or (
                key in state.coverage_map.cells and binding.status.value == "active"
            ))
        ] if state is not None else []),
        "finding": finding[:_FINDING_EXCERPT_CHARS],
        **({"finding_truncated": True} if truncated else {}),
        "source": node.source,
        "source_urls": urls,
        "citation": citation,
        "citable": citation is not None,
        "provenance_status": "source_linked" if urls else "original_source_missing",
        "source_excerpt": node.source_excerpt,
        **({"local_source_metadata": source_details} if source_details else {}),
        "confidence": node.confidence,
        "alignment": node.alignment,
        "observation_id": node.observation_id,
        "span_basis": "observation" if node.observation_id else "page",
        "span": (list(node.span) if node.span else None),
        "source_authority": node.source_authority,
    }


@tool(parse_docstring=True)
async def read_evidence(
    cell: CellRef | None = None,
    evidence_ids: str = "",
    row: RowRef | None = None,
    attribute: str = "",
    max_nodes: int = 40,
    include_inactive: bool = False,
    task_id: str = "",
) -> str:
    """Read evidence records in the current answer scope. Returns nodes, task bindings, and
    available comparisons for the requested cell.

    Explicit IDs and a cell select their combined records and take priority over row and attribute.
    With no selection filters, the tool returns recent nodes. Findings are excerpted to 500
    characters. Use resolve_cell_provenance for the full finding and original snippet where
    available. A source_linked record has a traceable source. Verify that its text supports the
    claim. Records missing an original source have citable=false.

    Args:
        cell: Exact CellRef {table_id,key,attribute}, with key values in primary_key order.
        evidence_ids: Comma-separated fact IDs, e.g. "f_abc,f_def".
        row: Exact RowRef to select evidence for one row.
        attribute: Exact column name. Combine with row for one row and column.
        max_nodes: Maximum number of recent records to return, default 40.
        include_inactive: True includes candidates, excluded, rejected and superseded evidence in
            the source scope for audit.
        task_id: Restrict the selection to facts associated with this task.
    """
    state = _ws().load_state()
    cell = (state.coverage_map.resolve_cell_reference(cell) or cell.cell_key()) if cell else ""
    entity = (state.coverage_map.resolve_row(row.row_key(), table_id=row.table_id)[0] or row.row_key()) if row else ""
    from searchos.socm.coverage import evidence_source_allowed
    all_nodes = ([node for node in state.evidence_graph.nodes if evidence_source_allowed(state, node)]
                 if include_inactive else answer_evidence(state))
    by_id = {n.id: n for n in all_nodes}

    ids: set[str] = set()
    if evidence_ids:
        ids.update(x.strip() for x in evidence_ids.split(",") if x.strip())
    if cell:
        if include_inactive:
            ids.update(n.id for n in all_nodes if n.status == EvidenceStatus.CANDIDATE
                       and n.entity and n.attribute
                       and state.coverage_map.cell_key(n.table_id, n.entity, n.attribute) == cell)
        target = state.coverage_map.cells.get(cell)
        if target is None and include_inactive:
            target = state.coverage_map.removed_cells.get(cell)
        if target:
            binding = state.coverage_map.cell_binding(cell)
            ids.update(
                eid for eid in target.supporting_evidence_ids
                if eid in by_id and (
                    include_inactive
                    or (binding is not None and evidence_matches_cell(state.coverage_map, by_id[eid], *binding))
                )
            )

    if ids or cell or evidence_ids:
        selected = [by_id[i] for i in ids if i in by_id]
    elif entity or attribute:
        bound_ids = set()
        for key, records in state.coverage_map.evidence_bindings.items():
            target = state.coverage_map.cell_binding(key)
            if target and (include_inactive or key in state.coverage_map.cells):
                if (not row or (target[0] == row.table_id and target[1] == entity)) and (not attribute or target[2] == attribute):
                    bound_ids.update(b.evidence_id for b in records if include_inactive or b.status.value == "active")
        selected = [
            n for n in all_nodes
            if n.id in bound_ids or ((not row or (n.entity == entity and (n.table_id or state.coverage_map.primary_table_id) == row.table_id))
            and (not attribute or n.attribute == attribute))
        ]
    else:
        selected = all_nodes

    if task_id:
        task_ids = {b.evidence_id for b in state.evidence_graph.task_bindings if b.task_id == task_id}
        selected = [node for node in selected if node.id in task_ids]

    target = state.coverage_map.cell_binding(cell) if cell else None
    if target and not include_inactive:
        selected = [project_cell_evidence(state.coverage_map, node, *target) or node for node in selected]

    selected.sort(key=lambda n: n.created_at)
    if len(selected) > max_nodes:
        selected = selected[-max_nodes:]
    comparisons = []
    if cell:
        from searchos.socm.coverage.conflicts import cell_pairs

        cached = state.coverage_map.evidence_comparisons.get(cell, {})
        comparisons = [
            result.model_dump(exclude={"retry_after"}) for pair in cell_pairs(state, cell)
            if (result := cached.get(pair.fingerprint)) is not None
        ]
    return json.dumps(
        {"nodes": [_node_snapshot(n, state, include_inactive=include_inactive) for n in selected], "count": len(selected),
         "comparisons": comparisons[:12], "comparison_count": len(comparisons),
         "task_bindings": [b.model_dump() for b in state.evidence_graph.task_bindings
                           if b.evidence_id in {n.id for n in selected}
                           and (not task_id or b.task_id == task_id)]},
        ensure_ascii=False,
    )


@tool(parse_docstring=True)
async def resolve_cell_provenance(
    cell: CellRef | None = None,
    evidence_id: str = "",
) -> str:
    """Trace a cell or one evidence record to its original source. Supply exactly one selector.
    Returns records and count.

    Each record includes its evidence_id, source_url/source_urls, snippet, finding, confidence and
    observation_id. A located span gives {start_char,end_char} relative to span_basis (observation
    or page). A null span means the text location is unknown.

    Args:
        cell: CellRef {table_id,key,attribute}, with key values in primary_key order. Omit when
            selecting an evidence ID.
        evidence_id: One evidence ID. Omit when selecting a cell.
    """
    ws = _ws()
    state = ws.load_state()
    records = _resolve(
        state,
        cell=((state.coverage_map.resolve_cell_reference(cell) or cell.cell_key()) if cell else None),
        evidence_id=(evidence_id or None),
        workspace=ws,
    )
    fields = (
        "evidence_id", "source_url", "source_urls", "snippet", "finding", "confidence",
        "observation_id", "span", "span_basis", "cell", "cell_value",
    )
    visible = [{key: record[key] for key in fields if key in record} for record in records]
    return json.dumps({"records": visible, "count": len(visible)}, ensure_ascii=False)


for _tool in (read_evidence, resolve_cell_provenance):
    _tool.args_schema.model_config["extra"] = "forbid"
    _tool.args_schema.model_rebuild(force=True)
