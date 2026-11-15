"""Exercise execution routing, evidence handoff, and conversation planning."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from searchos.config.run_config import EffectiveRunConfig
from searchos.config.settings import settings
from searchos.harness.routing import SearchRoute, select_route
from searchos.socm import EvidenceNode, SearchState


def route(path="simple"):
    return SearchRoute(
        path=path, reason="A narrow factual lookup", evidence_obligations=["Verify release date"],
        strategy=["simple"] if path == "simple" else ["deep"],
    )


@pytest.mark.asyncio
async def test_router_selects_simple_without_guessed_answers():
    model = SimpleNamespace(ainvoke=AsyncMock(
        return_value=AIMessage(content=route().model_dump_json()),
    ))
    chosen = await select_route(model=model, query="When was X released?", state=SearchState())
    assert chosen.path == "simple" and chosen.table_policy == "none"
    assert chosen.plan().evidence_obligations == ["Verify release date"]
    assert model.ainvoke.await_count == 1


@pytest.mark.parametrize("count", [4, 13])
@pytest.mark.asyncio
async def test_factual_check_count_does_not_force_research(count):
    obligations = [f"Verify published metric {index} in the same official bulletin"
                   for index in range(count)]
    response = dict(path="simple", reason="One official bulletin contains all requested metrics",
                    evidence_obligations=obligations, strategy=["simple"], table_policy="none")
    model = SimpleNamespace(ainvoke=AsyncMock(return_value=AIMessage(content=json.dumps(response))))
    chosen = await select_route(model=model, query="Read the requested metrics from this bulletin",
                                state=SearchState())
    assert chosen.path == "simple", chosen.reason
    assert chosen.plan().evidence_obligations == obligations


@pytest.mark.asyncio
async def test_router_receives_trusted_runtime_date():
    from datetime import date

    query = "截至2025年10月19日，当年布克奖得主公布了吗？"
    model = SimpleNamespace(ainvoke=AsyncMock(
        return_value=AIMessage(content=route().model_dump_json()),
    ))
    await select_route(model=model, query=query, state=SearchState())
    messages = model.ainvoke.call_args.args[0]
    assert f"Runtime as-of date: {date.today().isoformat()}" in messages[0].content
    assert "user" in messages[0].content and "cutoff" in messages[0].content
    assert json.loads(messages[1].content)["question"] == query


@pytest.mark.parametrize("kwargs", [
    {"execution_path": "unified"}, {"fixed_schema": True}, {"targeted_repair": True},
    {"follow_up": True}, {"table_export": True}, {"remaining_time_s": 0},
])
@pytest.mark.asyncio
async def test_structural_routes_skip_classifier(kwargs):
    model = SimpleNamespace(ainvoke=AsyncMock())
    chosen = await select_route(model=model, query="Question", state=SearchState(), **kwargs)
    assert chosen.path == "research"
    model.ainvoke.assert_not_called()


@pytest.mark.asyncio
async def test_required_schema_columns_route_to_research_before_classification():
    model = SimpleNamespace(ainvoke=AsyncMock(return_value=AIMessage(content=route().model_dump_json())))
    state = SearchState(required_attributes=["地区", "学校", "复试总分"])
    chosen = await select_route(model=model, query="查出各校分数", state=state)
    assert chosen.path == "research" and chosen.table_policy == "as_needed"
    model.ainvoke.assert_not_called()


@pytest.mark.asyncio
async def test_hybrid_keeps_source_workflow_and_malformed_router_falls_back():
    model = SimpleNamespace(ainvoke=AsyncMock(return_value=AIMessage(content="invalid")))
    state = SearchState(source_scope={"mode": "hybrid", "documents": []})
    assert (await select_route(model=model, query="Q", state=state)).path == "research"
    model.ainvoke.assert_not_called()
    chosen = await select_route(model=model, query="Q", state=SearchState())
    assert chosen.path == "research" and chosen.reason.startswith("router_fallback:")


@pytest.mark.asyncio
async def test_router_cancellation_propagates():
    model = SimpleNamespace(ainvoke=AsyncMock(side_effect=asyncio.CancelledError))
    with pytest.raises(asyncio.CancelledError):
        await select_route(model=model, query="Q", state=SearchState())


@pytest.mark.asyncio
async def test_existing_research_bypasses_router_even_without_follow_up_flag():
    from searchos.socm import FrontierTask

    state = SearchState()
    state.frontier.add(FrontierTask(id="pending", question="Existing research"))
    model = SimpleNamespace(ainvoke=AsyncMock())
    chosen = await select_route(model=model, query="Q", state=state)
    assert chosen.path == "research" and chosen.reason == "continue_existing_research"
    model.ainvoke.assert_not_called()


def test_no_plan_tool_prompt_preserves_completeness_and_source_rules():
    from searchos.agents.orchestrator.prompt import build_orchestrator_prompt
    from searchos.harness.middleware.context.socm_middleware import SOCMContextMiddleware
    from searchos.harness.middleware.models import TaskContext

    prompt = build_orchestrator_prompt("agents", "skills")
    assert "set_research_plan" not in prompt
    assert "source-backed inventory" in prompt and "evidence:FACT_ID" in prompt
    state = SearchState()
    middleware = SOCMContextMiddleware(
        workspace=SimpleNamespace(load_state=lambda: state), view="overview",
        task=TaskContext(agent_id="orchestrator"),
    )
    assert "set_research_plan" not in middleware.render()


@pytest.mark.asyncio
async def test_simple_session_publishes_evidence_without_building_orchestrator(monkeypatch, tmp_path):
    from searchos.config import models
    from searchos.harness import routing, session, simple_search
    from searchos.harness.simple_search import SimpleSearchOutcome
    from searchos.skills.catalog.registry import SkillRegistry

    model = SimpleNamespace(ainvoke=AsyncMock(return_value=AIMessage(
        content='{"is_final_answer": true}',
    )))
    monkeypatch.setattr(models, "get_model_for", lambda role: model)
    monkeypatch.setattr(settings, "enable_skills", False)
    monkeypatch.setattr(settings, "enable_access_skill_generation", False)
    monkeypatch.setattr(session, "_premature_end_reason", lambda *_: None)
    monkeypatch.setattr(routing, "select_route", AsyncMock(return_value=route()))

    async def simple(**kwargs):
        ws = kwargs["workspace"]
        state = ws.load_state()
        state.evidence_graph.add_node(EvidenceNode(
            id="original", source="https://example.org/release", finding="Released on 2022-10-24",
            source_excerpt="Released on 2022-10-24",
        ))
        ws.save_state(state)
        assert kwargs["remaining_time_s"] == 120
        kwargs["on_steer_delivery"](HumanMessage(
            content="Use UTC dates", id="steer-original-id",
            additional_kwargs={"sf_steer_id": "original-id", "sf_steer_mode": "immediate",
                               "sf_steer_text": "Use UTC dates"},
        ))
        return SimpleSearchOutcome(
            answer="2022-10-24. [Source](evidence:original)", delivered=["Use UTC dates"],
        )

    def build(self, **kwargs):
        raise AssertionError("Simple search must not build an Orchestrator")

    monkeypatch.setattr(simple_search, "run_simple_search", simple)
    monkeypatch.setattr(session.SearchSession, "_build_research_graph", build)
    harness = session.SearchSession(
        workspace_root=str(tmp_path), skill_registry=SkillRegistry(), max_time_s=240,
        run_config=EffectiveRunConfig.from_settings(), skip_synthesis=False,
    )
    result = await harness.run("Release date?", session_id="route")
    assert not result.execution_error
    model.ainvoke.assert_not_called()
    assert result.evidence_count == 1
    output = tmp_path / "route" / "output"
    assert "https://example.org/release" in (output / "report.md").read_text()
    record = json.loads((output / "routing.json").read_text())
    assert "escalated" not in record
    assert record["final_path"] == "simple"
    from searchos.harness.telemetry.conversation import conversation_turns, read_conversation

    turns = conversation_turns(result.workspace_path)
    assert len(turns) == 1 and turns[0]["query"] == "Release date?"
    assert turns[0]["steers"] == ["Use UTC dates"]
    assert turns[0]["answer"] == (output / "report.md").read_text()
    messages = read_conversation(
        tmp_path / "route/conversations/snapshots/orchestrator.json",
    )["messages"]
    assert sum(m["content"] == "Release date?" for m in messages) == 1
    assert any(m["metadata"].get("steer_id") == "original-id" for m in messages)
