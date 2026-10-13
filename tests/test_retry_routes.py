"""重试路线持久化、工具拦截与 SOCM heartbeat。"""

from dataclasses import dataclass
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from searchos.config.settings import settings
from searchos.harness.middleware.context.socm_middleware import SOCMContextMiddleware
from searchos.harness.middleware.models import TaskContext
from searchos.harness.middleware.sensor.route_middleware import RetryRouteMiddleware
from searchos.harness.middleware.extraction import InMemoryEvidenceStore
from searchos.socm import FrontierTask, FrontierTaskStatus, SearchState
from searchos.socm.retry_routes import check_and_record_route, retry_route_prompt


def store():
    state = SearchState()
    state.frontier.add(
        FrontierTask(
            id="f",
            question="revenue",
            assigned_agent_id="search_agent_1",
            status=FrontierTaskStatus.RUNNING,
            attempts=1,
        )
    )
    return InMemoryEvidenceStore(state)


def test_recycle_persists_routes_and_blocks_previous_attempt(monkeypatch):
    from searchos.agents.orchestrator import lifecycle

    ws = store()
    assert not check_and_record_route(
        ws, "search_agent_1", "search", {"query": "Acme annual revenue"}
    )
    assert not check_and_record_route(
        ws, "search_agent_1", "open", {"id_or_url": "https://www.example.com/report"}
    )
    monkeypatch.setattr(lifecycle, "_ctx", SimpleNamespace(workspace=ws, trajectory_logger=None))
    lifecycle._recycle_failed_task("f", "search_agent_1", "error", "failed")
    task = ws.state.frontier.questions[0]
    assert task.previous_queries == ["Acme annual revenue"]
    assert task.previous_source_families == ["example.com"]
    assert not task.attempt_queries
    restored = SearchState.model_validate_json(ws.state.model_dump_json())
    assert restored.frontier.questions[0].previous_queries == task.previous_queries
    task.assigned_agent_id = "search_agent_2"
    assert "Previous queries" in retry_route_prompt(task)
    assert check_and_record_route(ws, "search_agent_2", "search", {"query": "REVENUE, Acme annual"})
    assert not check_and_record_route(
        ws, "search_agent_2", "open", {"id_or_url": "https://example.com/different-page"}
    )
    assert not check_and_record_route(
        ws, "search_agent_2", "search", {"query": "Acme filing site:example.com"}
    )
    assert not check_and_record_route(
        ws, "search_agent_2", "search", {"query": "Acme securities filing"}
    )
    assert not check_and_record_route(
        ws, "search_agent_2", "open", {"id_or_url": "https://other.org/filing"}
    )


@pytest.mark.asyncio
async def test_retry_guard_stops_tool_before_execution():
    ws = store()
    ws.state.frontier.questions[0].previous_queries = ["annual revenue"]
    mw = RetryRouteMiddleware(ws, agent_id="search_agent_1")

    async def handler(request):
        pytest.fail("blocked query must not execute")

    result = await mw.awrap_tool_call(
        SimpleNamespace(
            tool_call={"name": "search", "args": {"query": "annual revenue"}, "id": "call1"}
        ),
        handler,
    )
    assert "RETRY_ROUTE_BLOCKED" in result.content


@pytest.mark.asyncio
async def test_snapshot_visible_with_or_without_legacy_heartbeat(monkeypatch):
    @dataclass
    class Request:
        messages: list
        system_message: object = None

    monkeypatch.setattr(settings, "enable_socm_projection", True)
    monkeypatch.setattr(settings, "socm_heartbeat_turns", 3)
    ws = store()
    ws.state.coverage_map.add_table("t", ["Name", "Revenue"], primary_key=["Name"], entities=["A"])
    mw = SOCMContextMiddleware(
        ws, task=TaskContext(agent_id="search_agent_1"), guidance="Continue.", heartbeat_turns=3
    )
    seen = []

    async def handler(request):
        seen.append(
            sum(m.additional_kwargs.get("sf_kind") == "socm_update" for m in request.messages)
        )
        return AIMessage(content="continue")

    for _ in range(4):
        await mw.awrap_model_call(Request([HumanMessage(content="task")]), handler)
    assert seen == [1, 1, 1, 1]
    mw.heartbeat_turns = 0
    for _ in range(4):
        await mw.awrap_model_call(Request([HumanMessage(content="task")]), handler)
    assert seen[-4:] == [1, 1, 1, 1]


def test_legacy_hostnames_do_not_block_unseen_pages_or_skill_arguments(monkeypatch):
    from searchos.tools.simple_browser import state as browser_state

    ws = store()
    ws.state.frontier.questions[0].previous_source_families = ["example.com", "skill:annual_report"]
    browser = SimpleNamespace(
        page_stack=["results"],
        pages={"results": SimpleNamespace(urls={"0": "https://www.example.com/report"})},
    )
    monkeypatch.setattr(browser_state, "_get_browser", lambda: browser)
    assert not check_and_record_route(ws, "search_agent_1", "open", {"id_or_url": 0})
    assert not check_and_record_route(ws, "search_agent_1", "skill_annual_report", {})
    assert not check_and_record_route(ws, "search_agent_1", "skill_other_source", {})


def test_route_history_is_isolated_between_agents():
    ws = store()
    ws.state.frontier.questions[0].previous_queries = ["annual revenue"]
    ws.state.frontier.add(
        FrontierTask(id="sibling", question="other", assigned_agent_id="search_agent_2")
    )
    assert not check_and_record_route(ws, "search_agent_2", "search", {"query": "annual revenue"})
    assert ws.state.frontier.questions[0].attempt_queries == []
    assert ws.state.frontier.questions[1].attempt_queries == ["annual revenue"]
