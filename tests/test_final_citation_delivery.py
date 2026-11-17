"""Check bounded citation repair, cancellation, and delivery with offline models."""

import asyncio
import json
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool

from searchos.config import models
from searchos.config.run_config import EffectiveRunConfig
from searchos.config.settings import settings
from searchos.harness.answer_stream import AnswerStreamEmitter
from searchos.harness.middleware.pipelines import orchestrator_pipeline
from searchos.harness.session import SearchSession, _commit_final_answer
from searchos.skills.catalog.registry import SkillRegistry
from searchos.socm import EvidenceNode, SearchState, WorkspaceManager
from tests.test_simple_search import OfflineModel

BAD = "Unverified conclusion [source](evidence:unsourced)"
GOOD = "Supported conclusion [source](evidence:original)"
RESOLVED = "Supported conclusion [source](https://example.org/original)"
OLD_REPORT = "Previously delivered answer"
OLD_RESULT = json.dumps({"query": "Previous question", "answer": "Previous answer"})


class ScriptedModel:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    async def ainvoke(self, messages, **kwargs):
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
async def test_current_answer_uses_one_citation_repair_then_consistent_delivery(tmp_path, repair):
    workspace = workspace_with_previous_answer(tmp_path)
    model, events, logged = ScriptedModel(repair), [], []
    answer = await _commit_final_answer(
        workspace=workspace,
        state=workspace.load_state(),
        query="Current question",
        final_state={"messages": [AIMessage(content=BAD)]}, model=model,
        stop_reason="time_budget_exhausted",
        answer_stream=AnswerStreamEmitter(events.append, stream_prefix="final"),
        conversation_logger=SimpleNamespace(log=logged.append),
    )

    assert len(model.calls) == 1
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
async def test_cancellation_during_citation_repair_preserves_previous_delivery(tmp_path):
    workspace = workspace_with_previous_answer(tmp_path)
    model, events, logged = ScriptedModel(asyncio.CancelledError()), [], []
    with pytest.raises(asyncio.CancelledError):
        await _commit_final_answer(
            workspace=workspace,
            state=workspace.load_state(),
            query="Current question",
            final_state={"messages": [AIMessage(content=BAD)]}, model=model,
            stop_reason="time_budget_exhausted",
            answer_stream=AnswerStreamEmitter(events.append, stream_prefix="final"),
            conversation_logger=SimpleNamespace(log=logged.append),
        )
    assert len(model.calls) == 1
    assert_old_answer_preserved(workspace)
    assert not events and not logged


@pytest.mark.asyncio
async def test_citation_repair_timeout_delivers_incomplete_without_another_model(
    tmp_path, monkeypatch
):
    workspace = workspace_with_previous_answer(tmp_path)
    model = ScriptedModel("wait_for_cancel")
    monkeypatch.setattr(settings, "research_finalize_timeout_s", 0.02)
    answer = await asyncio.wait_for(
        _commit_final_answer(
            workspace=workspace,
            state=workspace.load_state(),
            query="Current question",
            final_state={"messages": [AIMessage(content=BAD)]}, model=model,
            stop_reason="time_budget_exhausted",
        ),
        timeout=0.5,
    )
    assert len(model.calls) == 1
    report, result = read_delivery(workspace)
    assert answer == report == result["answer"]
    assert result["mode"] == "research_incomplete"
    assert result["citation_issues"] == ["evidence:unsourced"]
    assert "Finalization crashed" not in answer


@pytest.mark.asyncio
@pytest.mark.parametrize("answer", [GOOD, "The available sources leave this question unresolved."])
async def test_normal_session_commits_its_answer_without_another_model_call(
    tmp_path, monkeypatch, answer
):
    from unittest.mock import AsyncMock

    from searchos.config import models
    from searchos.harness import session
    from searchos.harness.middleware.context.steering_middleware import SteeringMiddleware
    from searchos.harness.steering import SteeringQueue
    from searchos.harness.telemetry.conversation import conversation_turns
    from searchos.skills.catalog.registry import SkillRegistry

    model = ScriptedModel()
    model.ainvoke = AsyncMock(wraps=model.ainvoke)
    monkeypatch.setattr(models, "get_model_for", lambda role: model)
    monkeypatch.setattr(settings, "enable_skills", False)
    monkeypatch.setattr(settings, "enable_access_skill_generation", False)
    monkeypatch.setattr(session, "_premature_end_reason", lambda *_: None)

    def build(self, **kwargs):
        async def stream(payload, **stream_kwargs):
            first = payload["messages"][0]
            yield "values", {"messages": [HumanMessage(content=first["content"]), AIMessage(answer)]}

        return SimpleNamespace(middleware=[], astream=stream), SteeringMiddleware(SteeringQueue())

    monkeypatch.setattr(session.SearchSession, "_build_research_graph", build)
    harness = session.SearchSession(
        workspace_root=str(tmp_path), skill_registry=SkillRegistry(), max_time_s=30,
        run_config=replace(EffectiveRunConfig.from_settings(), execution_path="unified"),
    )
    events = []
    result = await harness.run(
        "Current question", session_id="direct", initial_state=evidence_state(), on_event=events.append,
    )

    model.ainvoke.assert_not_awaited()
    assert not result.execution_error
    output = tmp_path / "direct" / settings.output_dir
    committed = json.loads((output / "result.json").read_text())
    expected = RESOLVED if answer == GOOD else answer
    assert committed["answer"] == (output / "report.md").read_text() == expected
    assert conversation_turns(result.workspace_path)[-1]["answer"] == expected
    assert result.final_messages[-1]["content"] == expected
    assert "".join(event.get("delta", "") for event in events if event.get("phase") == "final_answer") == expected
    assert committed["finalization"]["extra_generation_used"] == 0
    assert committed["finalization"]["generation_events"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("repair", [GOOD, BAD, "cancel", "audit_failure", "precommit_failure"])
async def test_normal_session_final_does_not_bypass_repair_and_history(
    tmp_path, monkeypatch, repair
):
    from searchos.config import models
    from searchos.harness import session
    from searchos.harness.telemetry.conversation import conversation_turns
    from searchos.skills.catalog.registry import SkillRegistry

    model = ScriptedModel(
        asyncio.CancelledError() if repair == "cancel" else
        GOOD if repair in {"audit_failure", "precommit_failure"} else repair,
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
                        AIMessage(content=BAD),
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
    assert len(model.calls) == 1
    report = (output / "report.md").read_text()
    committed = json.loads((output / "result.json").read_text())
    assert report == committed["answer"] == conversation_turns(result.workspace_path)[-1]["answer"]
    assert report == result.final_messages[-1]["content"]
    assert "".join(e.get("delta", "") for e in events if e.get("phase") == "final_answer") == report
    assert "source（原始来源未提供）" not in report and "Finalization crashed" not in report
    if repair in {GOOD, "audit_failure"}:
        assert report == RESOLVED
    else:
        assert committed["mode"] == "research_incomplete"
        assert committed["citation_issues"] == ["evidence:unsourced"]


def summary_messages(messages):
    return [m for m in messages if m.additional_kwargs.get("sf_kind") == "budget_summary"]


@pytest.fixture
def offline_settings(monkeypatch):
    for name in ("enable_skills", "enable_failure_memory", "enable_writer_agent",
                 "enable_access_skill_generation"):
        monkeypatch.setattr(settings, name, False)
    monkeypatch.setattr(settings, "middleware_pipelines", {"orchestrator": []})


def session_at(tmp_path):
    return SearchSession(
        workspace_root=str(tmp_path), skill_registry=SkillRegistry(),
        skill_library_path=str(tmp_path / "skills"), max_time_s=60,
        run_config=replace(EffectiveRunConfig.from_settings(), execution_path="unified"),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("stop", ["sensor", "resume"])
async def test_stopped_session_saves_existing_answer_without_regeneration(
    tmp_path, monkeypatch, offline_settings, stop,
):
    answer = "Team Orion published Paper Alpha. [Publication list](https://example.org/papers)."
    model = SimpleNamespace(ainvoke=AsyncMock(return_value=AIMessage(content="Replacement without the papers")))
    monkeypatch.setattr(models, "get_model_for", lambda _: model)
    monkeypatch.setattr(settings, "orch_premature_end_max_resumes", 2)
    state = SearchState(intent="Review Team Orion's publications", source_scope={"mode": "web"})
    if stop == "resume":
        state.coverage_map.add_table("paper_details", ["Title", "Venue"], primary_key=["Title"])
    streams = []

    def build(self, **kwargs):
        async def stream(payload, **stream_kwargs):
            streams.append(payload)
            if stop == "sensor":
                kwargs["orch_control"].stop("state_delta_stall")
            yield "values", {"messages": [HumanMessage(content=state.intent), AIMessage(content=answer)]}

        return SimpleNamespace(middleware=[], astream=stream), None

    monkeypatch.setattr(SearchSession, "_build_research_graph", build)
    result = await session_at(tmp_path).run(state.intent, session_id="saved", initial_state=state)
    delivery = json.loads((tmp_path / "saved/output/result.json").read_text())

    model.ainvoke.assert_not_awaited()
    assert len(streams) == (3 if stop == "resume" else 1)
    assert delivery["answer"] == (tmp_path / "saved/output/report.md").read_text() == answer
    assert result.final_messages[-1]["content"] == answer
    assert delivery["stop_reason"] == (
        "premature_end_resumes_exhausted" if stop == "resume" else "state_delta_stall"
    )


@pytest.mark.asyncio
async def test_sensor_stop_summarizes_after_full_tool_batch_in_original_context(
    tmp_path, monkeypatch, offline_settings,
):
    entered = [asyncio.Event(), asyncio.Event()]
    release = asyncio.Event()
    stopped = asyncio.Event()
    finished = []
    answer = "Paper Alpha and Paper Beta were retrieved; their complete venue counts remain unverified."

    async def respond(count, messages):
        if count == 1:
            return AIMessage(content="", tool_calls=[
                {"name": "read_paper", "args": {"index": i}, "id": f"paper-{i}"}
                for i in range(2)
            ])
        assert count == 2
        assert sorted(finished) == [0, 1]
        assert [m.content for m in messages if m.type == "tool"] == ["Paper Alpha", "Paper Beta"]
        assert "Earlier report: Orion's research scope" in str(messages)
        assert len(summary_messages(messages)) == 1
        assert messages[-1].type == "human"
        assert "state_delta_stall" in messages[-1].content
        return AIMessage(content=answer)

    model = OfflineModel(handler=respond)
    monkeypatch.setattr(models, "get_model_for", lambda _: model)

    def build(self, **kwargs):
        control = kwargs["orch_control"]

        @tool
        async def read_paper(index: int) -> str:
            """Read one saved paper."""
            entered[index].set()
            if index == 0:
                await entered[1].wait()
                control.stop("state_delta_stall")
                stopped.set()
            else:
                await release.wait()
            finished.append(index)
            return ["Paper Alpha", "Paper Beta"][index]

        from searchos.agents.runtime import _ctx

        return orchestrator_pipeline(
            model, [read_paper], workspace=kwargs["workspace"],
            budget=kwargs["orch_budget"], control=control,
            agent_graphs=_ctx.agent_graphs, task_pool=_ctx.task_pool,
            trajectory_logger=kwargs["traj_logger"], conversation_logger=kwargs["conv_logger"],
        ), None

    monkeypatch.setattr(SearchSession, "_build_research_graph", build)
    task = asyncio.create_task(session_at(tmp_path).run(
        "Review the papers", session_id="summary",
        conversation_history=[{"role": "assistant", "content": "Earlier report: Orion's research scope"}],
    ))
    try:
        await asyncio.wait_for(stopped.wait(), 5)
        assert len(model.calls) == 1 and not task.done()
        release.set()
        result = await asyncio.wait_for(task, 5)
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    assert not result.execution_error
    assert len(model.calls) == 2
    assert (tmp_path / "summary/output/report.md").read_text() == answer
    delivery = json.loads((tmp_path / "summary/output/result.json").read_text())
    assert delivery["stop_reason"] == "state_delta_stall"
    assert delivery["finalization"]["generation_events"] == []
