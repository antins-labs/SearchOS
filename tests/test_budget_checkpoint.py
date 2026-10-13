"""真实 graph checkpoint 的预算恢复与作用域。"""

import pytest
from langchain.agents import create_agent
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver

from searchos.harness.middleware import BudgetMiddleware, BudgetState, ControlState


class Model(FakeMessagesListChatModel):
    def bind_tools(self, tools, **kwargs):
        return self


@tool
def search(query: str) -> str:
    """Search a fixture source."""
    return "42"


def graph(middleware, saver, responses, **kwargs):
    return create_agent(
        model=Model(responses=responses),
        tools=[search],
        middleware=[middleware],
        checkpointer=saver,
        **kwargs,
    )


def call(call_id="s"):
    return AIMessage(
        content="", tool_calls=[{"name": "search", "args": {"query": "x"}, "id": call_id}]
    )


@pytest.mark.asyncio
async def test_thread_budget_restores_after_graph_rebuild():
    saver = InMemorySaver()
    cfg = {"configurable": {"thread_id": "t"}}
    first = BudgetMiddleware(BudgetState(max_queries=1), ControlState(), scope="thread")
    await graph(first, saver, [call(), AIMessage(content="done")]).ainvoke(
        {"messages": [("user", "search")]}, cfg
    )
    second = BudgetMiddleware(BudgetState(max_queries=1), ControlState(), scope="thread")
    await graph(second, saver, [AIMessage(content="done")]).ainvoke(
        {"messages": [("user", "continue")]}, cfg
    )
    assert second.budget.consumed_queries == 1
    assert second.control.forced
    assert second.control.reason == "budget_exhausted"


@pytest.mark.asyncio
async def test_run_budget_resets_between_invocations():
    saver = InMemorySaver()
    cfg = {"configurable": {"thread_id": "t"}}
    budget = BudgetMiddleware(BudgetState(max_queries=1), ControlState(), scope="run")
    g = graph(
        budget, saver, [call("a"), AIMessage(content="done"), call("b"), AIMessage(content="done")]
    )
    for _ in range(2):
        await g.ainvoke({"messages": [("user", "search")]}, cfg)
        assert budget.budget.consumed_queries == 1
        assert budget.budget.current_iteration == 2


@pytest.mark.asyncio
async def test_tool_receipt_restores_restart_before_next_model_hook():
    saver = InMemorySaver()
    cfg = {"configurable": {"thread_id": "t"}}
    first = BudgetMiddleware(BudgetState(max_queries=2), ControlState(), scope="thread")
    g = graph(first, saver, [call(), AIMessage(content="done")], interrupt_after=["tools"])
    state = await g.ainvoke({"messages": [("user", "search")]}, cfg)
    assert state["budget_checkpoint"]["usage"]["consumed_queries"] == 0
    assert state["messages"][-1].additional_kwargs["sf_budget_receipt"]["costs"] == {"search": 1}
    second = BudgetMiddleware(BudgetState(max_queries=2), ControlState(), scope="thread")
    await graph(second, saver, [AIMessage(content="done")]).ainvoke(None, cfg)
    assert second.budget.consumed_queries == 1


@pytest.mark.asyncio
async def test_component_instance_rejects_different_thread():
    budget = BudgetMiddleware(BudgetState(), ControlState(), scope="thread")
    g = graph(budget, InMemorySaver(), [AIMessage(content="done")])
    await g.ainvoke({"messages": [("user", "a")]}, {"configurable": {"thread_id": "a"}})
    with pytest.raises(ValueError, match="separate BudgetMiddleware"):
        await g.ainvoke({"messages": [("user", "b")]}, {"configurable": {"thread_id": "b"}})


@pytest.mark.asyncio
async def test_restart_after_model_restores_iteration_before_tool_execution():
    saver = InMemorySaver()
    cfg = {"configurable": {"thread_id": "t"}}
    first = BudgetMiddleware(BudgetState(max_queries=2), ControlState(), scope="thread")
    await graph(first, saver, [call()], interrupt_after=["model"]).ainvoke(
        {"messages": [("user", "search")]}, cfg
    )
    second = BudgetMiddleware(BudgetState(max_queries=2), ControlState(), scope="thread")
    await graph(second, saver, [AIMessage(content="done")]).ainvoke(None, cfg)
    assert second.budget.current_iteration == 2
    assert second.budget.consumed_queries == 1
