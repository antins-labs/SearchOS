"""Keep batch output within context limits and extraction aligned with visible windows."""

from types import SimpleNamespace

import pytest

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from searchos.harness.middleware.context.tool_results_middleware import ToolResultLimitMiddleware
from searchos.harness.middleware.utils.tools import tool_costs
from searchos.tools.simple_browser import batch
from searchos.tools.simple_browser.render import PageContents
from searchos.tools.simple_browser.search.base import SearchResult
from searchos.util.tool_output_budget import text_token_bound, tool_output_budget


def test_many_queries_are_fully_charged():
    assert tool_costs("explore_web", {"queries": [str(i) for i in range(20)],
                                      "open_top_k": 2}) == {"search": 20, "open": 40}


def test_combined_multilingual_pages_fit_and_artifacts_match_visible_content():
    pages = [PageContents(url=f"https://example.org/{i}", title=f"页面 {i}", urls={},
                          text="关键正文及完整来源，包含中文信息。\n" * 3000) for i in range(3)]
    rows = [(f"query-{i}", [SearchResult(url=p.url, title=p.title, snippet="摘要" * 5000)], "")
            for i, p in enumerate(pages)]
    token = tool_output_budget.set(9000)
    try:
        text, artifact = batch._render_wave(rows, pages, "Wave totals: 3 pages.")
    finally:
        tool_output_budget.reset(token)
    assert text_token_bound(text) <= 9000
    assert "Context budget" in text
    assert len(artifact["pages"]) == 3
    assert all(p["content"] in text for p in artifact["pages"])
    assert all(p["page_source"]["viewport"]["end_line_exclusive"] < 3000
               for p in artifact["pages"])


def test_tiny_budget_does_not_extract_hidden_pages():
    page = PageContents(url="https://example.org/long", title="标题" * 500,
                        urls={}, text="原文" * 5000)
    token = tool_output_budget.set(200)
    try:
        text, artifact = batch._render_wave([], [page], "One page.")
    finally:
        tool_output_budget.reset(token)
    assert text_token_bound(text) <= 200
    assert "omitted" in text
    assert not artifact["pages"]


@pytest.mark.asyncio
async def test_runtime_budget_reserves_model_context_and_divides_parallel_calls():
    mw = ToolResultLimitMiddleware({"explore_web": 48000})
    request = SimpleNamespace(
        model=SimpleNamespace(profile={"max_input_tokens": 10000}, max_tokens=2000),
        messages=[HumanMessage("任务" * 300)], system_message=SystemMessage("Rules."), tools=[],
    )

    async def model_handler(req):
        return None

    await mw.awrap_model_call(request, model_handler)
    calls = [{"name": "explore_web", "id": str(i), "args": {"queries": [str(i)]}}
             for i in range(2)]
    state = {"messages": [*request.messages, AIMessage("", tool_calls=calls)]}
    budgets = []

    async def tool_handler(_):
        budgets.append(tool_output_budget.get())
        return "bounded result"

    for call in calls:
        await mw.awrap_tool_call(SimpleNamespace(tool_call=call, state=state), tool_handler)
    assert len(budgets) == 2 and budgets[0] == budgets[1]
    assert 0 < sum(budgets) < 10000 - 2000 - text_token_bound(request.messages[0].content)
    assert tool_output_budget.get() == 100000


@pytest.mark.asyncio
async def test_large_valid_batch_is_not_recropped_by_old_character_limit():
    from langchain_core.messages import ToolMessage

    mw = ToolResultLimitMiddleware({"explore_web": 48000})
    content = "a" * 60000
    result = ToolMessage(content=content, tool_call_id="batch", artifact={"pages": [
        {"content": content, "source_url": "https://example.org/long"}]})

    async def handler(_):
        return result

    actual = await mw.awrap_tool_call(SimpleNamespace(
        tool_call={"name": "explore_web"}, state={}), handler)
    assert actual.content == content
    assert actual.artifact["pages"][0]["content"] in actual.content


def test_explore_extraction_preserves_all_displayed_page_text():
    from langchain_core.messages import ToolMessage

    from searchos.agents.orchestrator.lifecycle import _extract_explore_open_pages

    text = "[Now viewing] Long page\nURL: https://example.org/long\n\n" + "Body. " * 6000
    text += "The final required fact is at the end."
    msg = ToolMessage(content=f"<<<EXPLORE_PAGE>>>\n{text}\n<<<END_EXPLORE_PAGE>>>",
                      name="explore_web", tool_call_id="batch")
    assert _extract_explore_open_pages([msg])[0]["content"] == text


@pytest.mark.asyncio
async def test_extraction_feedback_cannot_break_batch_budget():
    from langchain_core.messages import ToolMessage

    mw = ToolResultLimitMiddleware({})

    async def handler(_):
        limit = tool_output_budget.get()
        page = "a" * (limit - 100)
        return ToolMessage(content=page + "\n" + "Feedback " * 100,
                           tool_call_id="batch", artifact={"pages": [{"content": page}]})

    result = await mw.awrap_tool_call(SimpleNamespace(
        tool_call={"name": "explore_web"}, state={}), handler)
    assert text_token_bound(result.content) <= 100000
    assert result.artifact["pages"][0]["content"] in result.content


@pytest.mark.asyncio
async def test_outer_budget_feedback_obeys_the_same_output_limit():
    from langchain_core.messages import ToolMessage

    from searchos.harness.middleware.utils.messages import append_feedback

    mw = ToolResultLimitMiddleware({})

    async def handler(_):
        return ToolMessage(content="a" * tool_output_budget.get(), tool_call_id="batch")

    result = await mw.awrap_tool_call(SimpleNamespace(
        tool_call={"name": "explore_web"}, state={}), handler)
    result = append_feedback(result, "Search budget exhausted. " * 20)
    assert text_token_bound(result.content) <= 100000
