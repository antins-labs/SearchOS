"""Check bounded citation repair, cancellation, and delivery with offline models."""

import asyncio
import json
from dataclasses import replace
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from searchos.config.run_config import EffectiveRunConfig
from searchos.config.settings import settings
from searchos.harness.answer_stream import AnswerStreamEmitter
from searchos.harness.session import _finalize_stopped_research
from searchos.socm import EvidenceNode, SearchState, WorkspaceManager

BAD = "Unverified conclusion [source](evidence:unsourced)"
GOOD = "Supported conclusion [source](evidence:original)"
RESOLVED = "Supported conclusion [source](https://example.org/original)"
OLD_REPORT = "Previously delivered answer"
OLD_RESULT = json.dumps({"query": "Previous question", "answer": "Previous answer"})


class ScriptedModel:
    def __init__(self, *responses, is_final=True):
        self.responses = list(responses)
        self.calls = []
        self.self_checks = []
        self.is_final = is_final

    async def ainvoke(self, messages, **kwargs):
        if "[FINAL_ANSWER_CHECK]" in str(messages[0].content):
            self.self_checks.append(messages)
            return AIMessage(content=json.dumps({"is_final_answer": self.is_final}))
        self.calls.append(messages)
        if not self.responses:
            raise AssertionError("Exceeded the explicit final-generation budget")
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        if response == "wait_for_cancel":
            await asyncio.Event().wait()
        return AIMessage(content=response)


def evidence_state():
    state = SearchState(intent="Current question", source_scope={"mode": "web"})
    state.evidence_graph.add_node(
        EvidenceNode(
            id="original",
            source="https://example.org/original",
            finding="Supported conclusion",
            source_excerpt="Supported conclusion",
        )
    )
    state.evidence_graph.add_node(
        EvidenceNode(
            id="unsourced",
            source="agent://worker/final_summary",
            finding="Unverified conclusion",
            source_excerpt="Unverified conclusion",
        )
    )
    return state


def workspace_with_previous_answer(tmp_path):
    workspace = WorkspaceManager(tmp_path, "case")
    workspace.create()
    workspace.save_state(evidence_state())
    workspace.write_output("report.md", OLD_REPORT)
    workspace.write_output("result.json", OLD_RESULT)
    return workspace


def read_delivery(workspace):
    output = workspace.path / settings.output_dir
    return (output / "report.md").read_text(), json.loads((output / "result.json").read_text())


def assert_old_answer_preserved(workspace):
    output = workspace.path / settings.output_dir
    assert (output / "report.md").read_text() == OLD_REPORT
    assert (output / "result.json").read_text() == OLD_RESULT


def assert_old_answer_audited(workspace):
    output = workspace.path / settings.output_dir
    audit_text = "\n".join(
        p.read_text()
        for p in output.rglob("*")
        if p.is_file() and p not in {output / "report.md", output / "result.json"}
    )
    assert OLD_REPORT in audit_text
    assert "Previous question" in audit_text and "Previous answer" in audit_text


@pytest.mark.asyncio
@pytest.mark.parametrize("repair", [GOOD, BAD])
async def test_budget_final_uses_one_repair_then_consistent_delivery(tmp_path, repair):
    workspace = workspace_with_previous_answer(tmp_path)
    model, events, logged = ScriptedModel(BAD, repair), [], []
    answer = await _finalize_stopped_research(
        workspace=workspace,
        state=workspace.load_state(),
        query="Current question",
        orchestrator_model=model,
        stop_reason="time_budget_exhausted",
        answer_stream=AnswerStreamEmitter(events.append, stream_prefix="final"),
        conversation_logger=SimpleNamespace(log=logged.append),
    )

    assert len(model.calls) == 2
    report, result = read_delivery(workspace)
    assert answer == report == result["answer"] == logged[-1].content
    assert "".join(e.get("delta", "") for e in events) == answer
    assert result["query"] == "Current question"
    assert "Finalization crashed" not in answer and "invalid-evidence-reference" not in answer
    assert "source（原始来源未提供）" not in answer and "evidence:unsourced" not in answer
    if repair == GOOD:
        assert answer == RESOLVED
        assert result["citation_issues"] == []
    else:
        assert result["mode"] == "research_incomplete"
        assert result["citation_issues"] == ["evidence:unsourced"]
    assert_old_answer_audited(workspace)


@pytest.mark.asyncio
async def test_synthesis_fallback_spends_the_shared_extra_generation_budget(tmp_path):
    workspace = workspace_with_previous_answer(tmp_path)
    primary = ScriptedModel(RuntimeError("offline primary failure"))
    fallback = ScriptedModel(BAD)
    answer = await _finalize_stopped_research(
        workspace=workspace,
        state=workspace.load_state(),
        query="Current question",
        orchestrator_model=primary,
        fallback_model=fallback,
        stop_reason="time_budget_exhausted",
    )
    assert len(primary.calls) == len(fallback.calls) == 1
    report, result = read_delivery(workspace)
    assert answer == report == result["answer"]
    assert result["mode"] == "research_incomplete"
    assert result["citation_issues"] == ["evidence:unsourced"]
    assert "source（原始来源未提供）" not in answer and "Finalization crashed" not in answer
    assert_old_answer_audited(workspace)


@pytest.mark.asyncio
async def test_cancellation_during_citation_repair_preserves_previous_delivery(tmp_path):
    workspace = workspace_with_previous_answer(tmp_path)
    model, events, logged = ScriptedModel(BAD, asyncio.CancelledError()), [], []
    with pytest.raises(asyncio.CancelledError):
        await _finalize_stopped_research(
            workspace=workspace,
            state=workspace.load_state(),
            query="Current question",
            orchestrator_model=model,
            stop_reason="time_budget_exhausted",
            answer_stream=AnswerStreamEmitter(events.append, stream_prefix="final"),
            conversation_logger=SimpleNamespace(log=logged.append),
        )
    assert len(model.calls) == 2
    assert_old_answer_preserved(workspace)
    assert not events and not logged


@pytest.mark.asyncio
async def test_citation_repair_timeout_delivers_incomplete_without_another_model(
    tmp_path, monkeypatch
):
    workspace = workspace_with_previous_answer(tmp_path)
    model = ScriptedModel(BAD, "wait_for_cancel")
    monkeypatch.setattr(settings, "research_finalize_timeout_s", 0.02)
    answer = await asyncio.wait_for(
        _finalize_stopped_research(
            workspace=workspace,
            state=workspace.load_state(),
            query="Current question",
            orchestrator_model=model,
            stop_reason="time_budget_exhausted",
        ),
        timeout=0.5,
    )
    assert len(model.calls) == 2
    report, result = read_delivery(workspace)
    assert answer == report == result["answer"]
    assert result["mode"] == "research_incomplete"
    assert result["citation_issues"] == ["evidence:unsourced"]
    assert "Finalization crashed" not in answer


@pytest.mark.asyncio
@pytest.mark.parametrize("repair", [GOOD, BAD, "cancel", "audit_failure", "precommit_failure", "self_audit"])
async def test_normal_session_final_does_not_bypass_repair_and_history(
    tmp_path, monkeypatch, repair
):
    from searchos.config import models
    from searchos.harness import session
    from searchos.harness.telemetry.conversation_context import conversation_turns
    from searchos.skills.catalog.registry import SkillRegistry

    model = ScriptedModel(
        asyncio.CancelledError() if repair == "cancel" else
        GOOD if repair in {"audit_failure", "precommit_failure", "self_audit"} else repair,
        is_final=repair != "self_audit",
    )
    if repair in {"audit_failure", "precommit_failure"}:
        original_audit = session._finalization_audit

        def fail_after_commit(workspace, audit):
            if audit["status"] == "repaired" or repair == "precommit_failure":
                raise OSError("offline audit storage failure")
            return original_audit(workspace, audit)

        monkeypatch.setattr(session, "_finalization_audit", fail_after_commit)
    monkeypatch.setattr(models, "get_model_for", lambda role: model)
    monkeypatch.setattr(settings, "enable_skills", False)
    monkeypatch.setattr(settings, "enable_access_skill_generation", False)
    monkeypatch.setattr(session, "_premature_end_reason", lambda *_: None)

    def build(self, **kwargs):
        async def stream(payload, **stream_kwargs):
            first = payload["messages"][0]
            yield (
                "values",
                {
                    "messages": [
                        HumanMessage(content=first["content"], id=first.get("id")),
                        AIMessage(content="Let me write the comprehensive answer." if repair == "self_audit" else BAD),
                    ]
                },
            )

        return SimpleNamespace(middleware=[], astream=stream), None

    monkeypatch.setattr(session.SearchSession, "_build_research_graph", build)
    harness = session.SearchSession(
        workspace_root=str(tmp_path),
        skill_registry=SkillRegistry(),
        max_time_s=30,
        run_config=replace(EffectiveRunConfig.from_settings(), execution_path="unified"),
    )
    events = []
    invocation = harness.run(
        "Current question",
        session_id="normal",
        initial_state=evidence_state(),
        on_event=events.append,
    )
    output = tmp_path / "normal" / settings.output_dir
    if repair == "precommit_failure":
        output.mkdir(parents=True)
        (output / "report.md").write_text(OLD_REPORT)
        (output / "result.json").write_text(OLD_RESULT)
        result = await invocation
        assert result.execution_error == "OSError"
        assert len(model.calls) == 0
        assert (output / "report.md").read_text() == OLD_REPORT
        assert (output / "result.json").read_text() == OLD_RESULT
        error = json.loads((output / "finalization_error.json").read_text())
        assert error["error_type"] == "OSError"
        assert not any(e.get("phase") == "final_answer" for e in events)
        return
    if repair == "cancel":
        with pytest.raises(asyncio.CancelledError):
            await invocation
        assert len(model.calls) == 1
        assert not (output / "report.md").exists()
        assert not (output / "result.json").exists()
        assert not any(e.get("phase") == "final_answer" for e in events)
        return
    result = await invocation
    assert len(model.self_checks) == 1
    assert len(model.calls) == 1
    report = (output / "report.md").read_text()
    committed = json.loads((output / "result.json").read_text())
    assert report == committed["answer"] == conversation_turns(result.workspace_path)[-1]["answer"]
    assert report == result.final_messages[-1]["content"]
    assert "".join(e.get("delta", "") for e in events if e.get("phase") == "final_answer") == report
    assert "source（原始来源未提供）" not in report and "Finalization crashed" not in report
    if repair in {GOOD, "audit_failure", "self_audit"}:
        assert report == RESOLVED
    else:
        assert committed["mode"] == "research_incomplete"
        assert committed["citation_issues"] == ["evidence:unsourced"]


@pytest.mark.asyncio
@pytest.mark.parametrize("is_final", [True, False])
async def test_answer_self_check_preserves_final_or_completes_once(is_final):
    from langchain_core.messages import ToolMessage
    from searchos.harness.session import _check_or_complete_answer

    audit = "All work is complete. Let me write the comprehensive answer."
    messages = [
        HumanMessage(content="比较甲乙"),
        AIMessage(content="", tool_calls=[{"name": "read_evidence", "id": "read", "args": {}}]),
        ToolMessage(content="甲两项合作，乙三项。", tool_call_id="read"),
        AIMessage(content=GOOD if is_final else audit),
    ]
    calls = []

    async def invoke(history):
        calls.append(history)
        if len(calls) == 1:
            payload = json.loads(history[-1].content)
            assert payload["candidate"] == messages[-1].content
            assert payload["follow_ups"] == ["补充收入比较"]
            return AIMessage(content=json.dumps({"is_final_answer": is_final}))
        assert len(calls) == 2
        assert messages == history[1:-1]
        assert "补充收入比较" in history[-1].content
        assert "此前已要求比较商业价值" in history[-1].content
        return AIMessage(content=GOOD)

    state = {"messages": messages}
    result, regenerated = await _check_or_complete_answer(
        final_state=state, query="比较甲乙", model=SimpleNamespace(ainvoke=invoke),
        follow_ups=["补充收入比较"], context_preamble="此前已要求比较商业价值",
    )
    assert len(calls) == (1 if is_final else 2)
    assert regenerated is (not is_final)
    assert result["messages"][-1].content == GOOD
    if is_final:
        assert result is state


@pytest.mark.asyncio
async def test_answer_self_check_skips_tool_calls():
    from unittest.mock import AsyncMock
    from searchos.harness.session import _check_or_complete_answer

    model = SimpleNamespace(ainvoke=AsyncMock())
    state = {"messages": [AIMessage(content="继续检索", tool_calls=[
        {"name": "read_evidence", "id": "read", "args": {}}
    ])]}
    result, regenerated = await _check_or_complete_answer(final_state=state, query="比较", model=model)
    assert result is state and not regenerated
    model.ainvoke.assert_not_called()
