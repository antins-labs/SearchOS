"""预算拒绝必须有界收尾，保留其他工具的有效执行机会。"""

import pytest
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import tool

from searchos.agents.runtime import create_search_agent_graph
from searchos.harness.middleware import (
    BudgetMiddleware,
    BudgetState,
    ControlState,
    SOCMContextMiddleware,
    TaskContext,
)
from searchos.harness.middleware.extraction import InMemoryEvidenceStore
from tests.test_budget_checkpoint import Model


@tool
def search(query: str) -> str:
    """Search a source."""
    return "A source was found."


@tool
def open(id_or_url: str) -> str:
    """Read a source."""
    return "A source was read."


def call(name, call_id):
    args = {"query": "citations"} if name == "search" else {"id_or_url": "https://example.org"}
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id}])


@pytest.mark.asyncio
async def test_agent19_budget_rejection_pattern_terminates_with_partial_summary():
    # search/open 已耗尽，find/skill 仍有额度；模型忽略拒绝继续交替调用。
    budget = BudgetState(max_queries=1, max_opens=1, max_finds=15, max_skills=20)
    control = ControlState()
    middleware = BudgetMiddleware(budget, control)
    socm = SOCMContextMiddleware(InMemoryEvidenceStore(), task=TaskContext(agent_id="agent19"))
    graph = create_search_agent_graph(
        model=Model(
            responses=[call("search", "s"), call("open", "o")]
            + [call("search" if i % 2 else "open", f"denied-{i}") for i in range(10)]
        ),
        tools=[search, open],
        middleware=[middleware, socm],
        image_fallback=False,
    )
    result = await graph.ainvoke(
        {"messages": [("user", "Fill DOI and citations")]},
        {"configurable": {"thread_id": "agent19"}, "recursion_limit": 50},
    )
    denied = [
        m
        for m in result["messages"]
        if isinstance(m, ToolMessage) and m.additional_kwargs.get("sf_blocked")
    ]
    assert len(denied) == 3
    assert control.reason == "budget_rejection_loop"
    assert control.forced
    assert budget.consumed_queries == budget.consumed_opens == 1
    assert not result["messages"][-1].tool_calls
    assert "partial" in result["messages"][-1].content
    assert "Search is stopped" in socm._last_text
    assert "Continue your assigned task" not in socm._last_text


@pytest.mark.asyncio
async def test_exhausted_tool_keeps_its_schema_and_other_budgeted_tools_remain():
    from langchain.agents.middleware.types import AgentMiddleware

    seen = []

    class Capture(AgentMiddleware):
        async def awrap_model_call(self, request, handler):
            seen.append([item.name for item in request.tools])
            return await handler(request)

    control = ControlState()
    graph = create_search_agent_graph(
        model=Model(responses=[call("search", "s"), call("open", "o"), AIMessage(content="done")]),
        tools=[search, open],
        middleware=[BudgetMiddleware(BudgetState(max_queries=1, max_opens=3), control), Capture()],
        image_fallback=False,
    )
    await graph.ainvoke({"messages": [("user", "Read")]}, {"configurable": {"thread_id": "filter"}})
    assert seen == [["search", "open"]] * 3
    assert not control.forced


@pytest.mark.asyncio
async def test_parallel_denials_count_once_and_an_executed_tool_resets_the_streak():
    control = ControlState()
    budget = BudgetState(max_queries=1, max_opens=10, max_finds=15)
    denied_batch = AIMessage(
        content="",
        tool_calls=[
            {"name": "search", "args": {"query": "citations"}, "id": f"batch-{i}"} for i in range(8)
        ],
    )
    recovery = AIMessage(
        content="",
        tool_calls=[
            *call("search", "mixed-denial").tool_calls,
            *call("open", "mixed-read").tool_calls,
        ],
    )
    graph = create_search_agent_graph(
        model=Model(
            responses=[
                call("search", "first"),
                denied_batch,
                call("search", "denied-2"),
                recovery,
                call("search", "denied-3"),
                call("search", "denied-4"),
                call("open", "last-read"),
                AIMessage(content="done"),
            ]
        ),
        tools=[search, open],
        middleware=[BudgetMiddleware(budget, control)],
        image_fallback=False,
    )
    result = await graph.ainvoke(
        {"messages": [("user", "Read")]},
        {"configurable": {"thread_id": "recover"}, "recursion_limit": 100},
    )
    assert not control.forced
    assert budget.consumed_opens == 2
    assert result["messages"][-1].content == "done"


@pytest.mark.asyncio
@pytest.mark.parametrize("interrupt_at", ["tools", "model"])
async def test_rejection_streak_survives_rebuild_between_checkpoint_hooks(interrupt_at):
    from langgraph.checkpoint.memory import InMemorySaver

    from tests.test_budget_checkpoint import graph

    saver = InMemorySaver()
    cfg = {"configurable": {"thread_id": f"rejection-{interrupt_at}"}}
    first = BudgetMiddleware(
        BudgetState(max_queries=1, max_finds=15), ControlState(), scope="thread"
    )
    await graph(
        first,
        saver,
        [
            call("search", "first"),
            call("search", "denied-1"),
            call("search", "denied-2"),
            AIMessage(content="partial"),
        ],
    ).ainvoke(
        {"messages": [("user", "Read")]},
        cfg,
    )
    # 新回合拒绝前（model）或拒绝后（tools）中断，随后从新实例恢复。
    await graph(first, saver, [call("search", "denied-3")], interrupt_after=[interrupt_at]).ainvoke(
        {"messages": [("user", "Continue")]},
        cfg,
    )
    second = BudgetMiddleware(
        BudgetState(max_queries=1, max_finds=15), ControlState(), scope="thread"
    )
    await graph(second, saver, [AIMessage(content="partial findings")]).ainvoke(None, cfg)
    assert second.control.forced
    assert second.control.reason == "budget_rejection_loop"
    assert second.budget.consumed_queries == 1


@pytest.mark.asyncio
async def test_new_run_resets_rejection_streak():
    from langgraph.checkpoint.memory import InMemorySaver

    from tests.test_budget_checkpoint import graph

    budget = BudgetMiddleware(BudgetState(max_queries=1, max_finds=15), ControlState())
    responses = []
    for i in range(2):
        responses.extend(
            [
                call("search", f"first-{i}"),
                call("search", f"denied-1-{i}"),
                call("search", f"denied-2-{i}"),
                AIMessage(content="done"),
            ]
        )
    g = graph(budget, InMemorySaver(), responses)
    for _ in range(2):
        result = await g.ainvoke(
            {"messages": [("user", "Read")]}, {"configurable": {"thread_id": "new-run"}}
        )
        assert not budget.control.forced
        assert result["messages"][-1].content == "done"
