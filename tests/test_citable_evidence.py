"""Retain unsourced summaries for audit without issuing original-source citations."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from searchos.socm import EvidenceNode, SearchState


def state_with_unsourced_summary():
    state = SearchState(source_scope={"mode": "web", "documents": []})
    state.evidence_graph.add_node(EvidenceNode(
        id="summary", source="agent://search_agent/final_summary", source_urls=[],
        finding="tomllib does not support writing TOML.",
        source_excerpt="tomllib does not support writing TOML.",
        alignment="full", alignment_note="source_support_verified",
    ))
    state.evidence_graph.add_node(EvidenceNode(
        id="original", source="https://docs.python.org/3.11/library/tomllib.html",
        finding="The module provides load and loads.",
        source_excerpt="This module defines the following functions: load, loads.",
    ))
    return state


@pytest.mark.asyncio
async def test_read_evidence_does_not_issue_citation_for_summary_without_source(monkeypatch):
    from searchos.tools.socm_read import evidence

    state = state_with_unsourced_summary()
    monkeypatch.setattr(evidence, "_ws", lambda: SimpleNamespace(load_state=lambda: state))
    result = json.loads(await evidence.read_evidence.ainvoke({}))
    nodes = {node["id"]: node for node in result["nodes"]}
    assert nodes["summary"]["citation"] is None
    assert nodes["summary"]["citable"] is False
    assert nodes["summary"]["provenance_status"] == "original_source_missing"
    assert nodes["original"]["citation"] == "evidence:original"
    assert nodes["original"]["citable"] is True
    assert nodes["original"]["provenance_status"] == "source_linked"
    assert state.evidence_graph.get_node("summary") is not None


def test_task_report_keeps_summary_out_of_grounded_findings():
    from searchos.socm.coverage import answer_evidence
    from searchos.tools.tasks.reports import _ground_search_report

    state = state_with_unsourced_summary()
    report = {"last_message": "Agent claims", "evidence_bindings": [
        {"evidence_id": "summary"}, {"evidence_id": "original"},
    ]}
    _ground_search_report(report, answer_evidence(state))
    assert [n["id"] for n in report["grounded_findings"]] == ["original"]
    assert "evidence:summary" not in report["last_message"]
    assert report["agent_report"]["verified"] is False
    assert report["unlinked_findings"][0]["id"] == "summary"
    assert report["unlinked_findings"][0]["citation"] is None
    assert report["unlinked_findings_total"] == 1
    assert "补充原文" in report["last_message"]


@pytest.mark.asyncio
async def test_review_cannot_verify_summary_against_itself():
    from searchos.harness.report.grounding import review_answer

    model = SimpleNamespace(ainvoke=AsyncMock())
    review = await review_answer(
        "tomllib cannot write. [Source](evidence:summary)",
        state_with_unsourced_summary(), model,
    )
    assert review.status == "unsupported"
    model.ainvoke.assert_not_called()


@pytest.mark.parametrize("source,urls,expected", [
    ("https://example.org/original", [], "evidence:fact"),
    ("agent://worker/summary", ["https://example.org/original"], "evidence:fact"),
    ("skill://execution/result", ["https://example.org/original"], "evidence:fact"),
    ("agent://worker/summary", [], None),
    ("agent://worker/summary", ["skill://execution/result"], None),
    ("", [], None),
])
def test_citation_requires_original_address_without_inventing_sources(source, urls, expected):
    from searchos.socm.evidence.provenance import evidence_citation

    node = EvidenceNode(id="fact", source=source, source_urls=urls)
    before = node.model_dump()
    assert evidence_citation(node) == expected
    assert node.model_dump() == before


@pytest.mark.asyncio
async def test_inspect_preserves_values_and_coverage_but_reports_citation_gaps(monkeypatch):
    from searchos.socm.coverage import commit_evidence
    from searchos.tools import schema

    state = SearchState()
    state.coverage_map.add_table(
        "t", ["name", "value"], primary_key=["name"], entities=["Summary", "Original"]
    )
    commit_evidence(state, [
        EvidenceNode(id="summary", source="agent://worker/summary", table_id="t",
                     entity="Summary", attribute="value", value="kept for audit", alignment="full"),
        EvidenceNode(id="original", source="https://example.org/original", table_id="t",
                     entity="Original", attribute="value", value="source value", alignment="full"),
    ])
    before = state.model_dump()
    workspace = SimpleNamespace(load_state=lambda: state)
    monkeypatch.setattr(schema.assertions, "_orch_ctx", lambda: SimpleNamespace(workspace=workspace))
    result = json.loads(await schema.inspect_table.ainvoke({"table_id": "t"}))
    assert result["values"]["Summary"]["value"] == "kept for audit"
    assert result["citations"] == {"Original": {"value": "evidence:original"}}
    assert result["citation_gaps"] == {"Summary": {"value": "original_source_missing"}}
    assert state.model_dump() == before


@pytest.mark.asyncio
async def test_finalizer_keeps_unsourced_claim_as_explicit_gap():
    from langchain_core.messages import AIMessage

    from searchos.harness.report.synthesis import finalize_research
    from searchos.socm.planning.research_plan import ResearchPlan

    model = SimpleNamespace(ainvoke=AsyncMock(return_value=AIMessage(content="Sources incomplete.")))
    state = state_with_unsourced_summary()
    state.research_plan = ResearchPlan(
        strategy=["deep"], evidence_obligations=["Can tomllib write?"],
        stop_rule="Verify source support and report remaining gaps.",
    )
    state.coverage_map.add_table("t", ["name"], primary_key=["name"], entities=["tomllib"])
    assert await finalize_research(
        state=state, query="Can tomllib write?", model=model, stop_reason="time_budget",
    ) == "Sources incomplete."
    messages = model.ainvoke.call_args.args[0]
    payload = json.loads(messages[-1].content)
    rows = {node["id"]: node for node in payload["evidence"]}
    assert rows["summary"]["finding"] == state.evidence_graph.get_node("summary").finding
    assert rows["summary"]["citation"] is None
    assert rows["summary"]["citable"] is False
    assert rows["summary"]["provenance_status"] == "original_source_missing"
    assert rows["original"]["citation"] == "[原文](evidence:original)"
    assert payload["original_source_missing_count"] == 1
    assert "update set_scope" not in payload["research_plan"]
    assert "不得静默忽略" in messages[0].content


@pytest.mark.asyncio
async def test_review_stops_matching_when_derived_original_source_is_removed():
    from searchos.harness.report.grounding import review_answer, review_matches_state

    state = state_with_unsourced_summary()
    node = state.evidence_graph.get_node("summary")
    node.source_urls = ["https://example.org/original"]
    answer = "tomllib cannot write. [Source](evidence:summary)"
    model = SimpleNamespace(ainvoke=AsyncMock(return_value=SimpleNamespace(content=json.dumps({
        "complete": True,
        "claims": [{"line_id": 0, "kind": "fact", "supported": True,
                    "bindings": [{"evidence_id": "summary", "quote": node.source_excerpt}]}],
    }))))
    review = await review_answer(answer, state, model)
    assert review.status == "verified"
    assert review_matches_state(review.to_dict(), answer, state)
    node.source_urls = []
    assert not review_matches_state(review.to_dict(), answer, state)
