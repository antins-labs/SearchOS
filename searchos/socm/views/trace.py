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


def _trace_node(node: EvidenceNode, ws: WorkspaceManager | None, state: SearchState) -> dict[str, Any]:
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
    observation = next((item for item in state.evidence_graph.observations
                        if item.id == node.observation_id and item.source == node.source), None)
    if node.observation_id:
        # Never interpret a window-relative span as a cached full-page offset.
        span_obj = None
        if observation is not None and node.span is not None:
            start, end = node.span
            if 0 <= start <= end <= len(observation.text) and observation.text[start:end] == raw_snippet:
                span_obj = {"start_char": start, "end_char": end}
    return {
        "evidence_id": node.id,
        "page_id": node.page_id,
        "source_url": node.source,
        "snippet": raw_snippet,
        "span": span_obj,
        "span_basis": "observation" if node.observation_id else "page",
        "observation_id": node.observation_id,
        "observation_text_hash": observation.text_hash if observation else "",
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

    from searchos.socm.coverage import evidence_source_allowed, project_cell_evidence
    nodes_by_id = {n.id: n for n in state.evidence_graph.nodes if evidence_source_allowed(state, n)}

    if evidence_id is not None:
        node = nodes_by_id.get(evidence_id)
        return [_trace_node(node, workspace, state)] if node else []

    ids = state.coverage_map.cells.get(cell, None)
    if ids is None:
        return []
    target = state.coverage_map.cell_binding(cell)
    if target is None:
        return []
    return [
        {**_trace_node(view, workspace, state), "cell": cell, "cell_value": view.value}
        for eid in ids.supporting_evidence_ids
        if eid in nodes_by_id
        and (view := project_cell_evidence(state.coverage_map, nodes_by_id[eid], *target)) is not None
    ]
