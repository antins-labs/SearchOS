"""Reject untraceable citations before publication and preserve previous output."""

import json
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage

from searchos.harness.session import _write_findings_answer
from searchos.socm import EvidenceNode, SearchState


@pytest.mark.parametrize("kind", ["unknown", "rejected", "unsourced"])
@pytest.mark.parametrize("has_previous_answer", [False, True])
def test_direct_orchestrator_final_rejects_bad_citation_before_publication(
    kind, has_previous_answer
):
    state = SearchState()
    if kind != "unknown":
        state.evidence_graph.add_node(
            EvidenceNode(
                id="fact",
                finding="A supported claim",
                source_excerpt="A supported claim",
                source="agent://worker/final_summary"
                if kind == "unsourced"
                else "https://example.org/original",
                status="rejected" if kind == "rejected" else "active",
            )
        )
    before_state = state.model_dump()
    outputs = (
        {
            "report.md": "Previously delivered answer",
            "result.json": json.dumps({"query": "Previous question", "answer": "Previous answer"}),
        }
        if has_previous_answer
        else {}
    )
    before_outputs = dict(outputs)
    workspace = SimpleNamespace(write_output=lambda name, value: outputs.update({name: value}))

    # 此处直接进入正常 Orchestrator final 使用的写出边界，未调用可选 review_answer。
    with pytest.raises(ValueError, match=r"(?i)citation|引用|来源"):
        _write_findings_answer(
            workspace,
            state,
            "Current question",
            {"messages": [AIMessage(content="A supported claim [source](evidence:fact)")]},
        )

    assert outputs == before_outputs
    assert state.model_dump() == before_state


@pytest.mark.parametrize("derived", [False, True])
def test_direct_orchestrator_final_publishes_traceable_citation(derived):
    state = SearchState()
    state.evidence_graph.add_node(
        EvidenceNode(
            id="fact",
            finding="A supported claim",
            source_excerpt="A supported claim",
            source="agent://worker/final_summary" if derived else "https://example.org/original",
            source_urls=["https://example.org/original"] if derived else [],
        )
    )
    outputs = {}
    answer = _write_findings_answer(
        SimpleNamespace(write_output=lambda name, value: outputs.update({name: value})),
        state,
        "Current question",
        {"messages": [AIMessage(content="A supported claim [source](evidence:fact)")]},
    )
    result = json.loads(outputs["result.json"])
    assert answer == "A supported claim [source](https://example.org/original)"
    assert result["answer"] == outputs["report.md"] == answer
    assert result["citation_issues"] == []
