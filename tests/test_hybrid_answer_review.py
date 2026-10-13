"""最终回答的支持检查、有限预算与发布时证据状态回归。"""

import asyncio
import json
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage

from searchos.harness.report.grounding import review_answer, review_matches_state
from searchos.harness.session import _write_findings_answer
from searchos.socm import SearchState
from searchos.socm.evidence import EvidenceNode, EvidenceStatus


ANSWER = "The API permits 90 requests/minute. [Official](evidence:rate)"
QUOTE = "Revision 2 permits 90 requests/minute."


def source_state():
    state = SearchState(
        intent="What is the API rate?",
        research_mode="findings",
        source_scope={"mode": "hybrid", "documents": []},
    )
    state.evidence_graph.add_node(
        EvidenceNode(
            id="rate",
            source="https://example.org/api",
            finding=QUOTE,
            source_excerpt=QUOTE,
        )
    )
    return state


def claim(**changes):
    return {
        "text": ANSWER,
        "kind": "fact",
        "supported": True,
        "bindings": [{"evidence_id": "rate", "quote": QUOTE}],
        **changes,
    }


class Reviewer:
    def __init__(self, result=None, *, delay=0):
        self.result = result or {"complete": True, "claims": [claim()]}
        self.calls = []
        self.delay = delay

    async def ainvoke(self, prompt):
        self.calls.append(prompt)
        await asyncio.sleep(self.delay)
        return SimpleNamespace(content=json.dumps(self.result))


@pytest.mark.asyncio
async def test_review_preserves_claim_spans_and_rechecks_current_fact():
    state = source_state()
    model = Reviewer()
    reviewed = await review_answer(ANSWER, state, model)
    assert reviewed.status == "verified"
    assert len(model.calls) == 1
    result = reviewed.to_dict()
    assert result["claims"][0]["span"] == [0, len(ANSWER)]
    assert result["claims"][0]["bindings"][0]["finding"] == QUOTE
    assert review_matches_state(result, ANSWER, state)
    assert not review_matches_state(result, ANSWER + " Changed", state)
    node = state.evidence_graph.nodes[0]
    node.finding = "Revision 2 is available."
    assert not review_matches_state(result, ANSWER, state)
    node.finding = QUOTE
    node.status = EvidenceStatus.REJECTED
    assert not review_matches_state(result, ANSWER, state)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "row",
    [
        claim(supported=False, reason="版本号不能支持速率。"),
        claim(bindings=[{"evidence_id": "rate", "quote": "900 requests/minute"}]),
        claim(bindings=[{"evidence_id": "other", "quote": QUOTE}]),
        claim(bindings=[{"evidence_id": [], "quote": QUOTE}]),
        claim(bindings=[]),
        claim(text="Not in the answer"),
        claim(kind=[]),
        [],
    ],
)
async def test_review_rejects_unsupported_or_malformed_bindings(row):
    reviewed = await review_answer(
        ANSWER, source_state(), Reviewer({"complete": True, "claims": [row]})
    )
    assert reviewed.status == "unsupported"
    assert reviewed.issues


@pytest.mark.asyncio
async def test_review_anchors_support_quote_across_browser_line_labels():
    state = source_state()
    state.evidence_graph.nodes[0].source_excerpt = "Revision 2 permits 90\nL1: requests/minute."
    reviewed = await review_answer(ANSWER, state, Reviewer())
    assert reviewed.status == "verified"
    assert (
        reviewed.claims[0]["bindings"][0]["source_excerpt"]
        == state.evidence_graph.nodes[0].source_excerpt
    )


@pytest.mark.asyncio
async def test_legacy_source_url_requires_exact_identity():
    state = source_state()
    model = Reviewer()
    for answer in [
        "A claim without citation",
        ANSWER.replace("rate)", "unknown)"),
        "A claim [link](https://example.org/api-other)",
    ]:
        assert (await review_answer(answer, state, model)).status == "unsupported"
    assert not model.calls
    answer = ANSWER.replace("evidence:rate", "https://example.org/api")
    model.result["claims"] = [claim(text=answer)]
    assert (await review_answer(answer, state, model)).status == "verified"


@pytest.mark.asyncio
async def test_review_budget_timeout_and_cancellation_are_bounded():
    state = source_state()
    model = Reviewer(delay=1)
    assert (await review_answer(ANSWER, state, model, max_chars=1)).status == "budget_exceeded"
    assert (await review_answer(ANSWER, state, model, timeout_s=0)).status == "budget_exceeded"
    assert not model.calls
    assert (await review_answer(ANSWER, state, model, timeout_s=0.01)).status == "unavailable"
    task = asyncio.create_task(review_answer(ANSWER, state, model))
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_review_outcomes_do_not_gate_agent_answer():
    for response, expected in [
        ({"complete": False, "claims": [claim()]}, "unsupported"),
        ({"complete": True, "claims": []}, "unavailable"),
        ([claim()], "unavailable"),
    ]:
        reviewed = await review_answer(ANSWER, source_state(), Reviewer(response))
        assert reviewed.status == expected
        outputs = {}
        _write_findings_answer(
            SimpleNamespace(write_output=lambda name, text: outputs.update({name: text})),
            source_state(),
            "Question",
            {"messages": [AIMessage(content=ANSWER)]},
        )
        assert json.loads(outputs["result.json"])["mode"] == "hybrid_orchestrator"
        assert outputs["report.md"] == ANSWER.replace("evidence:rate", "https://example.org/api")
        assert "answer_review.json" not in outputs


@pytest.mark.asyncio
async def test_unavailable_citation_does_not_replace_agent_prose():
    state = source_state()
    reviewed = await review_answer(ANSWER, state, Reviewer())
    state.evidence_graph.nodes[0].status = EvidenceStatus.REJECTED
    outputs = {}
    _write_findings_answer(
        SimpleNamespace(write_output=lambda name, text: outputs.update({name: text})),
        state,
        "Question",
        {"messages": [AIMessage(content=ANSWER)]},
    )
    result = json.loads(outputs["result.json"])
    assert result["mode"] == "hybrid_orchestrator"
    assert result["answer"] == ANSWER.replace("evidence:rate", "invalid-evidence-reference")
    assert "answer_review.json" not in outputs


@pytest.mark.asyncio
async def test_inferences_keep_premise_bindings_and_suggestions_are_not_facts():
    answer = ANSWER + " This allows at most 180 requests in two minutes. Consider caching."
    rows = [
        claim(),
        claim(text="This allows at most 180 requests in two minutes.", kind="inference"),
        claim(text="Consider caching.", kind="nonfactual", supported=False, bindings=[]),
    ]
    reviewed = await review_answer(
        answer, source_state(), Reviewer({"complete": True, "claims": rows})
    )
    assert reviewed.status == "verified"
    assert [row["status"] for row in reviewed.claims] == [
        "supported",
        "supported",
        "not_applicable",
    ]
    assert not reviewed.claims[-1]["bindings"]


@pytest.mark.asyncio
async def test_line_review_anchors_original_text_without_heading_paraphrases():
    answer = "## Revision 2\n\n" + ANSWER
    model = Reviewer(
        {
            "complete": True,
            "claims": [
                {"line_id": 0, "kind": "nonfactual", "supported": True, "bindings": []},
                {**claim(text="Revision 2: " + ANSWER), "line_id": 1},
            ],
        }
    )
    review = await review_answer(answer, source_state(), model)
    assert review.status == "verified"
    assert review.claims[1]["text"] == ANSWER
    assert review.claims[1]["span"] == [len("## Revision 2\n\n"), len(answer)]
    assert '"answer_lines"' in model.calls[0]
    assert review_matches_state(review.to_dict(), answer, source_state())


@pytest.mark.asyncio
@pytest.mark.parametrize("ids", [[0], [0, 0], [0, 2], [0, True], [0, "1"]])
async def test_line_review_rejects_missing_duplicate_or_invalid_ids(ids):
    answer = "## Revision 2\n" + ANSWER
    rows = [{**claim(), "line_id": line_id} for line_id in ids]
    review = await review_answer(
        answer, source_state(), Reviewer({"complete": True, "claims": rows})
    )
    assert review.status == "unsupported" and review.issues


@pytest.mark.asyncio
async def test_valid_line_id_does_not_bypass_source_support():
    review = await review_answer(
        ANSWER,
        source_state(),
        Reviewer(
            {
                "complete": True,
                "claims": [
                    {
                        **claim(bindings=[{"evidence_id": "rate", "quote": "900 requests/minute"}]),
                        "line_id": 0,
                    },
                ],
            }
        ),
    )
    assert review.status == "unsupported"


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["gap", "failure", "timeout", "cancel", "unsupported"])
async def test_forced_finalization_calls_llm_with_no_facts_and_keeps_failures_explicit(monkeypatch, outcome):
    from searchos.config.settings import settings
    from searchos.harness.session import _finalize_stopped_research
    from searchos.harness.answer_stream import AnswerStreamEmitter
    from searchos.socm.frontier import FrontierTask

    state = SearchState(intent="List the bibliography", research_mode="findings")
    state.frontier.add(FrontierTask(id="references", question="Read References"))
    outputs, events, calls = {}, [], []
    workspace = SimpleNamespace(load_state=lambda: state,
                                write_output=lambda name, text: outputs.update({name: text}))
    draft = "尚未取得文献依据，参考文献读取任务未完成。"

    class Model:
        async def ainvoke(self, messages):
            payload = json.loads(messages[-1].content)
            calls.append(payload)
            assert payload["evidence"] == []
            assert payload["tasks"][0]["status"] == "pending"
            if outcome == "failure":
                raise RuntimeError("synthetic")
            if outcome == "timeout":
                await asyncio.sleep(1)
            if outcome == "cancel":
                raise asyncio.CancelledError()
            return AIMessage(content=draft)

    monkeypatch.setattr(settings, "research_finalize_timeout_s", 0.01)
    stream = AnswerStreamEmitter(events.append, stream_prefix="final")
    invocation = _finalize_stopped_research(
        workspace=workspace, state=state, query=state.intent,
        orchestrator_model=Model(), stop_reason="research_budget_exhausted",
        answer_stream=stream,
    )
    if outcome == "cancel":
        with pytest.raises(asyncio.CancelledError):
            await invocation
        assert not outputs and not events
    else:
        answer = await invocation
        result = json.loads(outputs["result.json"])
        assert result["answer"] == answer == outputs["report.md"]
        assert result["stop_reason"] == "research_budget_exhausted"
        if outcome in {"gap", "unsupported"}:
            assert answer == draft and result["mode"] == "research_finalized"
        else:
            assert result["mode"] == "hybrid_partial"
            assert answer == "研究执行中断，尚未生成回答。"
        assert events[0]["type"] == "answer_stream_start"
        assert "".join(event.get("delta", "") for event in events) == answer
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_forced_finalization_uses_synthesis_only_after_orchestrator_failure():
    from searchos.harness.session import _finalize_stopped_research

    state = source_state()
    outputs = {}
    logged = []
    workspace = SimpleNamespace(
        load_state=lambda: state,
        write_output=lambda name, text: outputs.update({name: text}),
    )

    class FailingOrchestrator:
        async def ainvoke(self, messages):
            raise RuntimeError("orchestrator unavailable")

    class SynthesisFallback:
        async def ainvoke(self, messages):
            return AIMessage(content=ANSWER)

    answer = await _finalize_stopped_research(
        workspace=workspace,
        state=state,
        query=state.intent,
        orchestrator_model=FailingOrchestrator(),
        fallback_model=SynthesisFallback(),
        stop_reason="time_budget_exhausted",
        conversation_logger=SimpleNamespace(log=logged.append),
    )

    result = json.loads(outputs["result.json"])
    assert result["mode"] == "research_finalized"
    assert result["execution_error"] == ""
    assert answer == ANSWER.replace("evidence:rate", "https://example.org/api")
    assert logged[0].content == answer
    assert logged[0].metadata["finalizer"] == "synthesis"


@pytest.mark.asyncio
async def test_finalization_limits_input_without_cutting_evidence():
    from searchos.harness.report.synthesis import finalize_research

    state = source_state()
    state.evidence_graph.add_node(EvidenceNode(
        id="oversized", source="https://example.org/long", finding="x" * 5000,
        source_excerpt="x" * 5000,
    ))
    captured = []

    class Model:
        async def ainvoke(self, messages):
            captured.append(messages[-1].content)
            return AIMessage(content=ANSWER)

    assert await finalize_research(state=state, query=state.intent, model=Model(),
                                   stop_reason="stop", max_chars=1000) == ANSWER
    payload = json.loads(captured[0])
    assert len(captured[0]) <= 1000 and payload["omitted_evidence"] == 1
    assert [node["id"] for node in payload["evidence"]] == ["rate"]


def test_final_agent_text_survives_trailing_tool_and_empty_messages():
    from langchain_core.messages import ToolMessage
    from searchos.harness.report.grounding import final_answer_text

    state = {"messages": [
        AIMessage(content="较早的回答"),
        AIMessage(content=[{"type": "text", "text": "## 最终回答\n\n保留原始段落。"}]),
        AIMessage(content="工具调用说明", tool_calls=[{"name": "search", "args": {}, "id": "call"}]),
        ToolMessage(content="工具返回内容", tool_call_id="call"),
        AIMessage(content=""),
    ]}
    assert final_answer_text(state) == "## 最终回答\n\n保留原始段落。"


def test_legacy_review_nudge_does_not_create_an_extra_history_turn(tmp_path):
    from searchos.harness.telemetry.conversation_context import conversation_turns

    folder = tmp_path / "conversations" / "snapshots"
    folder.mkdir(parents=True)
    (folder / "orchestrator.json").write_text(json.dumps({"messages": [
        {"role": "user", "content": "调研论文"},
        {"role": "assistant", "content": "初步回答"},
        {"role": "user", "content": "[回答来源检查]\n核查引用"},
        {"role": "assistant", "content": "最终回答"},
    ]}), encoding="utf-8")
    assert conversation_turns(tmp_path) == [{"query": "调研论文", "answer": "最终回答", "steers": []}]
