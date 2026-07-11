"""Explore 宽召回批处理工具的回归测试。"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from langchain_core.messages import AIMessage, ToolMessage

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
    from searchos.harness.middleware.sensor.harness import HarnessMiddleware

    args = {"queries": ["q1", "q2", "q3"], "open_top_k": 2}

    assert HarnessMiddleware._tool_budget_cost("explore_web", args, "search") == 3
    assert HarnessMiddleware._tool_budget_cost("explore_web", args, "open") == 6
    assert HarnessMiddleware._tool_budget_cost("search", {"query": "q"}, "search") == 1


async def test_harness_rejects_premature_explore_completion(monkeypatch):
    from searchos.config.settings import settings
    from searchos.harness.middleware.sensor.harness import HarnessMiddleware

    @dataclass
    class Request:
        system_message: object = None
        messages: tuple = ()

    monkeypatch.setattr(settings, "explore_min_waves", 2)
    monkeypatch.setattr(settings, "enable_explore_batch", True)
    middleware = HarnessMiddleware(worker_name="explore_agent")
    middleware._explore_wave_count = 1
    calls = 0

    async def handler(request):
        nonlocal calls
        calls += 1
        if calls == 1:
            return AIMessage(content="I am done after one hub")
        assert "Premature completion refused" in str(request.system_message.content)
        return AIMessage(
            content="",
            tool_calls=[{
                "name": "explore_web",
                "args": {"queries": ["gap query"]},
                "id": "call-gap",
                "type": "tool_call",
            }],
        )

    response = await middleware.awrap_model_call(Request(), handler)

    assert calls == 2
    assert response.tool_calls[0]["name"] == "explore_web"


async def test_legacy_toggle_allows_normal_terminal_response(monkeypatch):
    from dataclasses import dataclass

    from langchain_core.messages import AIMessage

    from searchos.config.settings import settings
    from searchos.harness.middleware.sensor.harness import HarnessMiddleware

    @dataclass
    class Request:
        system_message: object = None
        messages: tuple = ()

    monkeypatch.setattr(settings, "enable_explore_batch", False)
    middleware = HarnessMiddleware(worker_name="explore_agent")
    calls = 0

    async def handler(_request):
        nonlocal calls
        calls += 1
        return AIMessage(content="legacy briefing")

    response = await middleware.awrap_model_call(Request(), handler)

    assert calls == 1
    assert response.content == "legacy briefing"


async def test_subagent_tool_started_event_is_emitted_before_batch_finishes():
    from dataclasses import dataclass

    from searchos.harness.middleware.sensor.budget import BudgetState
    from searchos.harness.middleware.sensor.harness import HarnessMiddleware

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
    middleware = HarnessMiddleware(
        worker_name="explore_agent",
        trajectory_logger=logger,
        budget=BudgetState(max_queries=30, max_opens=36),
    )
    request = Request(tool_call={
        "name": "explore_web",
        "id": "wave-1",
        "args": {"queries": ["official list", "regional list"], "open_top_k": 1},
    })

    async def handler(_request):
        assert logger.events[-1]["type"] == "tool_call_started"
        return "Wave totals: 2 queries, 4 hits, 2 unique pages opened."

    await middleware.awrap_tool_call(request, handler)

    started = logger.events[0]
    assert started == {
        "type": "tool_call_started",
        "agent": "explore_agent",
        "tool": "explore_web",
        "tool_call_id": "wave-1",
        "args": {"queries": ["official list", "regional list"], "open_top_k": 1},
    }
