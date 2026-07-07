"""Provenance trace — cell/evidence → raw page snippet lookup.

Closes the loop from a CoverageCell back to the page text that supports it,
without re-fetching. Read-only and workspace-local (no network).

    CoverageCell.supporting_evidence_ids → EvidenceNode → page_id / excerpt
        → pages/<page_id>.md (cached)

Returns plain dicts so callers can serialize them directly into tool results.
"""

from __future__ import annotations

from typing import Any

from searchos.socm.evidence import EvidenceNode
from searchos.socm.state import SearchState
from searchos.socm.workspace import WorkspaceManager


def _trace_node(node: EvidenceNode, ws: WorkspaceManager | None) -> dict[str, Any]:
    raw_snippet = node.source_excerpt or ""
    # Prefer the span stored at extraction; re-compute only as a fallback for
    # older evidence records without span populated.
    span_obj: dict[str, int] | None = None
    if node.span is not None:
        span_obj = {"start_char": node.span[0], "end_char": node.span[1]}
    elif raw_snippet and ws and node.page_id:
        page_text = ws.read_page(node.page_id)
        idx = page_text.find(raw_snippet) if page_text else -1
        if idx >= 0:
            span_obj = {"start_char": idx, "end_char": idx + len(raw_snippet)}
    return {
        "evidence_id": node.id,
        "page_id": node.page_id,
        "source_url": node.source,
        "snippet": raw_snippet,
        "span": span_obj,
        "text_hash": node.text_hash,
        "finding": node.finding,
        "confidence": node.confidence,
    }


def resolve_cell_provenance(
    state: SearchState,
    *,
    cell: str | None = None,
    evidence_id: str | None = None,
    workspace: WorkspaceManager | None = None,
) -> list[dict[str, Any]]:
    """Provenance records for a cell or a single evidence id.

    ``cell`` is a key in ``CoverageMap.cells``. Exactly one of ``cell`` /
    ``evidence_id`` must be given. Missing pages yield ``span=None`` rather
    than raising — the writer can still cite the snippet.
    """
    if (cell is None) == (evidence_id is None):
        raise ValueError("exactly one of `cell` or `evidence_id` is required")

    nodes_by_id = {n.id: n for n in state.evidence_graph.nodes}

    if evidence_id is not None:
        node = nodes_by_id.get(evidence_id)
        return [_trace_node(node, workspace)] if node else []

    ids = state.coverage_map.cells.get(cell, None)
    if ids is None:
        return []
    return [
        _trace_node(nodes_by_id[eid], workspace)
        for eid in ids.supporting_evidence_ids
        if eid in nodes_by_id
    ]
