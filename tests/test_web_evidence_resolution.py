"""Evidence conflict resolution API regression tests."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

_REPO = Path(__file__).resolve().parent.parent
for path in (str(_REPO), str(_REPO / "web")):
    if path not in sys.path:
        sys.path.insert(0, path)

from api.routes import search
from searchos.socm import (
    EvidenceEdge,
    EvidenceNode,
    EvidenceRelation,
    EvidenceStatus,
    SearchState,
    WorkspaceManager,
)


def _conflicted_state() -> SearchState:
    state = SearchState(intent="Compare companies")
    state.coverage_map.initialize(["Acme"], ["revenue"])
    nodes = [
        EvidenceNode(
            id="official",
            finding="Acme revenue: $12M",
            value="$12M",
            source="https://acme.example/report",
            source_excerpt="Revenue was $12M.",
            confidence=0.95,
            source_authority="official",
            entity="Acme",
            attribute="revenue",
            table_id="_default",
        ),
        EvidenceNode(
            id="corroborating",
            finding="Acme revenue: $12M",
            value="$12M",
            source="https://news.example/acme",
            confidence=0.8,
            source_authority="news",
            entity="Acme",
            attribute="revenue",
            table_id="_default",
        ),
        EvidenceNode(
            id="aggregator",
            finding="Acme revenue: $10M",
            value="$10M",
            source="https://data.example/acme",
            confidence=0.75,
            source_authority="aggregator",
            entity="Acme",
            attribute="revenue",
            table_id="_default",
        ),
    ]
    for node in nodes:
        state.evidence_graph.add_node(node)
    state.evidence_graph.add_edge(EvidenceEdge(
        from_id="official",
        to_id="aggregator",
        relation=EvidenceRelation.CONFLICT,
    ))
    state.coverage_map.fill_from_evidence(nodes)
    return state


def _request(evidence_id: str = "official") -> search.ResolveEvidenceRequest:
    return search.ResolveEvidenceRequest(
        table_id="_default",
        entity="Acme",
        attribute="revenue",
        evidence_id=evidence_id,
    )


def test_resolve_evidence_keeps_support_and_supersedes_other_values():
    state = _conflicted_state()

    updated, superseded = search._resolve_evidence_choice(state, _request())

    nodes = {node.id: node for node in updated.evidence_graph.nodes}
    cell = updated.coverage_map.cells["_default/Acme.revenue"]
    assert superseded == ["aggregator"]
    assert nodes["official"].status == EvidenceStatus.ACTIVE
    assert nodes["corroborating"].status == EvidenceStatus.ACTIVE
    assert nodes["aggregator"].status == EvidenceStatus.SUPERSEDED
    assert set(cell.supporting_evidence_ids) == {"official", "corroborating"}
    assert cell.primary_evidence_id == "official"
    assert cell.value == "$12M"
    assert cell.has_conflict is False
    assert "aggregator" in cell.conflict_evidence_ids
    assert any(
        edge.relation == EvidenceRelation.SUPPORT
        and {edge.from_id, edge.to_id} == {"official", "corroborating"}
        for edge in updated.evidence_graph.edges
    )


def test_resolve_evidence_endpoint_persists_workspace(monkeypatch, tmp_path):
    workspace = WorkspaceManager(tmp_path, "session")
    workspace.create()
    workspace.save_state(_conflicted_state())
    monkeypatch.setattr(search, "WORKSPACE_ROOT", tmp_path)
    search.sessions.clear()

    response = asyncio.run(search.resolve_evidence("session", _request()))

    stored = workspace.load_state()
    assert response.status == "resolved"
    assert response.superseded_evidence_ids == ["aggregator"]
    assert stored.coverage_map.cells["_default/Acme.revenue"].primary_evidence_id == "official"
    assert next(
        node for node in stored.evidence_graph.nodes if node.id == "aggregator"
    ).status == EvidenceStatus.SUPERSEDED


def test_resolve_evidence_rejects_wrong_cell():
    state = _conflicted_state()
    request = _request()
    request.entity = "Other"

    with pytest.raises(HTTPException) as exc:
        search._resolve_evidence_choice(state, request)

    assert exc.value.status_code == 422


def test_resolve_evidence_endpoint_rejects_running_session():
    search.sessions["busy"] = {"status": "running"}
    try:
        with pytest.raises(HTTPException) as exc:
            asyncio.run(search.resolve_evidence("busy", _request()))
        assert exc.value.status_code == 409
    finally:
        search.sessions.pop("busy", None)


def test_resolve_evidence_endpoint_rejects_path_traversal(monkeypatch, tmp_path):
    monkeypatch.setattr(search, "WORKSPACE_ROOT", tmp_path)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(search.resolve_evidence("../outside", _request()))

    assert exc.value.status_code == 400
