"""Explore 宽召回批处理工具的回归测试。"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest
from langchain_core.messages import AIMessage, ToolMessage

from searchos.harness.middleware.sensor.core.models import ControlState
from searchos.tools.simple_browser.render import PageContents
from searchos.tools.simple_browser.search.base import SearchResult


async def test_explore_web_searches_and_opens_concurrently(monkeypatch):
    import searchos.tools.simple_browser.batch as batch_module
    from searchos.tools.simple_browser import reset_browser_for_sub_agent

    active_searches = 0
    max_active_searches = 0
    active_opens = 0
    max_active_opens = 0

    class FakeProvider:
        async def search(self, query: str, max_results: int = 10):
            nonlocal active_searches, max_active_searches
            active_searches += 1
            max_active_searches = max(max_active_searches, active_searches)
            await asyncio.sleep(0.01)
            active_searches -= 1
            slug = query.replace(" ", "-")
            return [
                SearchResult(
                    title=f"Hub for {query}",
                    url=f"https://example.com/{slug}",
                    snippet=f"candidate entities for {query}",
                )
            ]

    async def fake_fetch(url: str, timeout: float = 20.0, *, query: str = ""):
        nonlocal active_opens, max_active_opens
        active_opens += 1
        max_active_opens = max(max_active_opens, active_opens)
        await asyncio.sleep(0.01)
        active_opens -= 1
        return PageContents(
            url=url,
            title=f"Page {url.rsplit('/', 1)[-1]}",
            text=f"URL: {url}\n\nEntity A\nEntity B\nEntity C",
            urls={},
        )

    reset_browser_for_sub_agent()
    monkeypatch.setattr(batch_module, "get_provider", lambda: FakeProvider())
    monkeypatch.setattr(batch_module, "_fetch_page", fake_fetch)

    output = await batch_module.explore_web.ainvoke({
        "queries": ["official roster", "regional list", "alternate language"],
        "open_top_k": 1,
        "max_results_per_query": 3,
    })

    assert max_active_searches >= 2
    assert max_active_opens >= 2
    assert output.count("<<<EXPLORE_PAGE>>>") == 3
    assert "official-roster" in output
    assert "regional-list" in output
    assert "alternate-language" in output


def test_explore_agent_exposes_batch_tool_only(monkeypatch):
    from searchos.agents.explore import get_tools
    from searchos.config.settings import settings

    monkeypatch.setattr(settings, "enable_explore_batch", True)

    names = [tool.name for tool in get_tools()]

    assert names == ["explore_web"]


def test_explore_agent_toggle_restores_legacy_tools_and_budget(monkeypatch):
    from searchos.agents.explore import get_tools
    from searchos.agents.orchestrator.lifecycle import _agent_budget_override
    from searchos.config.settings import settings

    monkeypatch.setattr(settings, "enable_explore_batch", False)

    assert [tool.name for tool in get_tools()] == ["search", "open", "find"]
    assert _agent_budget_override("explore_agent") == {
        "max_searches": 8,
        "max_opens": 8,
        "max_finds": 8,
    }


def test_explore_page_replay_extracts_every_page_from_batch_output():
    from searchos.agents.orchestrator.lifecycle import _extract_explore_open_pages

    content = """
Wave search summary
<<<EXPLORE_PAGE>>>
[Now viewing] First hub
URL: https://one.example/hub
first page body with enough grounded candidate entity content to replay later
candidate A, candidate B, candidate C, candidate D, candidate E; official roster,
regional coverage, category coverage, historical aliases and eligibility rules.
This deliberately exceeds the minimum replay size used to reject empty snippets.
Additional grounded content: candidate F, candidate G, candidate H, candidate I.
<<<END_EXPLORE_PAGE>>>
<<<EXPLORE_PAGE>>>
[Now viewing] Second hub
URL: https://two.example/hub
second page body with enough grounded candidate entity content to replay later
candidate J, candidate K, candidate L, candidate M, candidate N; official roster,
regional coverage, category coverage, historical aliases and eligibility rules.
This deliberately exceeds the minimum replay size used to reject empty snippets.
Additional grounded content: candidate O, candidate P, candidate Q, candidate R.
<<<END_EXPLORE_PAGE>>>
"""
    messages = [ToolMessage(content=content, tool_call_id="call-1", name="explore_web")]

    pages = _extract_explore_open_pages(messages)

    assert {page["source_url"] for page in pages} == {
        "https://one.example/hub",
        "https://two.example/hub",
    }


def test_batch_tool_budget_cost_counts_underlying_work():
    from searchos.harness.middleware.utils.tools import tool_costs

    args = {"queries": ["q1", "q2", "q3"], "open_top_k": 2}

    assert tool_costs("explore_web", args)["search"] == 3
    assert tool_costs("explore_web", args)["open"] == 6
    assert tool_costs("search", {"query": "q"})["search"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("waves_used", [0, 1])
async def test_explore_accepts_terminal_brief_without_extra_model_calls(waves_used):
    from searchos.agents.explore.policy import ExplorePolicy

    @dataclass
    class Request:
        system_message: object = None

    policy = ExplorePolicy(max_waves=3, control=ControlState())
    policy.waves_used = waves_used
    calls = []

    async def handler(request):
        calls.append(request)
        return AIMessage(content="Identity resolved from the supplied official source.")

    response = await policy.call_model(Request(), handler)
    assert len(calls) == 1
    assert response.content.startswith("Identity resolved")
    assert not response.tool_calls


@pytest.mark.asyncio
async def test_explore_wave_cap_reserves_concurrent_calls_and_allows_final_brief():
    from types import SimpleNamespace
    from searchos.agents.explore.policy import ExplorePolicy
    from searchos.harness.middleware.utils.messages import is_blocked

    policy = ExplorePolicy(max_waves=2, control=ControlState())
    executed = []

    async def handler(request):
        executed.append(request.tool_call["id"])
        await asyncio.sleep(0)
        return "source content"

    results = await asyncio.gather(*(
        policy.call_tool(SimpleNamespace(tool_call={"name": "explore_web", "id": str(i)}), handler)
        for i in range(3)
    ))
    assert len(executed) == 2
    assert sum(is_blocked(result) for result in results) == 1
    assert policy.waves_used == 2

    @dataclass
    class Request:
        system_message: object = None

    async def finish(request):
        assert "No exploration waves remain" in request.system_message.content
        return AIMessage(content="Partial coverage; missing historical sources.")

    assert (await policy.call_model(Request(), finish)).content.startswith("Partial coverage")


@pytest.mark.asyncio
@pytest.mark.parametrize("for_eval", [False, True])
@pytest.mark.parametrize("batch", [False, True])
async def test_explore_pipeline_can_finish_after_one_wave(monkeypatch, for_eval, batch):
    from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
    from langchain_core.tools import tool
    from searchos.config.settings import settings
    from searchos.config.run_config import EffectiveRunConfig, activate_run_config
    from searchos.harness.middleware.extraction import TaskContext
    from searchos.harness.middleware.pipelines import explore_pipeline

    class Model(FakeMessagesListChatModel):
        def bind_tools(self, tools, **kwargs):
            return self

    calls = []

    @tool
    def explore_web(queries: list[str]) -> str:
        """读取测试资料。"""
        calls.extend(queries)
        return "Official roster: Alpha and Beta are the complete eligible set."

    monkeypatch.setattr(settings, "enable_explore_batch", batch)
    config = EffectiveRunConfig.from_settings(for_eval=for_eval)
    assert "explore_min_waves" not in config.snapshot()
    model = Model(responses=[
        AIMessage(content="", tool_calls=[{
            "name": "explore_web", "args": {"queries": ["official roster"]}, "id": "wave-1",
        }]),
        AIMessage(content="The official roster defines the complete scope: Alpha and Beta."),
        AIMessage(content="Unexpected extra model call"),
    ])
    with activate_run_config(config):
        graph = explore_pipeline(model=model, tools=[explore_web], workspace=None,
                                 task=TaskContext(agent_id="explore_agent"))
        result = await graph.ainvoke(
            {"messages": [("user", "Identify the official roster.")]},
            {"configurable": {"thread_id": "explore-early-stop"}},
        )
    assert calls == ["official roster"]
    assert result["messages"][-1].content.startswith("The official roster")
    assert model.i == 2


async def test_subagent_tool_started_event_is_emitted_before_batch_finishes():
    from dataclasses import dataclass

    from searchos.harness.telemetry.recording import AgentRecorder

    class Logger:
        def __init__(self):
            self.events = []

        def _append_raw(self, event):
            self.events.append(event)

        def _compute_step_value(self, _delta):
            return 0.0

        _step_count = 0

    @dataclass
    class Request:
        tool_call: dict

    logger = Logger()
    middleware = AgentRecorder(
        agent_id="explore_agent", emit_started=True,
        logger=logger,
    )
    request = Request(tool_call={
        "name": "explore_web",
        "id": "wave-1",
        "args": {"queries": ["official list", "regional list"], "open_top_k": 1},
    })

    async def handler(_request):
        assert logger.events[-1]["type"] == "tool_call_started"
        return "Wave totals: 2 queries, 4 hits, 2 unique pages opened."

    started = middleware.tool_started(request)
    middleware.tool_completed(request, await handler(request), started)

    started = logger.events[0]
    assert started == {
        "type": "tool_call_started",
        "agent": "explore_agent",
        "tool": "explore_web",
        "tool_call_id": "wave-1",
        "step_index": 0,
        "reasoning": "",
        "args": {"queries": ["official list", "regional list"], "open_top_k": 1},
    }
