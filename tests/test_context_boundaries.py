"""从真实模型请求验证装载契约与最后一层上下文预算。"""

from dataclasses import dataclass

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from searchos.agents.runtime import create_search_agent_graph
from searchos.harness.middleware import DynamicTrimMiddleware
from tests.test_middleware_runtime import Model


@pytest.mark.asyncio
async def test_empty_list_never_enters_automatic_deepagents_summary(monkeypatch):
    from deepagents.middleware.summarization import SummarizationMiddleware

    async def unexpected(*args, **kwargs):
        pytest.fail("Unloaded automatic summarization ran")

    monkeypatch.setattr(SummarizationMiddleware, "awrap_model_call", unexpected)
    graph = create_search_agent_graph(
        Model(responses=[AIMessage("done")]),
        [],
        middleware=[],
    )
    result = await graph.ainvoke(
        {"messages": [HumanMessage("A long task " * 1000)]},
        {"configurable": {"thread_id": "explicit"}},
    )
    assert result["messages"][-1].content == "done"


@dataclass
class Request:
    messages: list
    system_message: object = None
    tools: object = None
    model: object = None


@pytest.mark.asyncio
async def test_trim_counts_large_arguments_and_pins_latest_context():
    mw = DynamicTrimMiddleware(max_tokens=600)
    snapshot = HumanMessage(
        "Current task state", additional_kwargs={"sf_kind": "socm_update", "sf_synthetic": True}
    )
    handoff = HumanMessage(
        "Previous verified result",
        additional_kwargs={"sf_kind": "context_compaction", "sf_synthetic": True},
    )
    request = Request(
        [
            HumanMessage("Task"),
            handoff,
            AIMessage("", tool_calls=[{"id": "a", "name": "read", "args": {"text": "x" * 4000}}]),
            ToolMessage("short", tool_call_id="a"),
            snapshot,
        ],
        SystemMessage("Rules"),
    )
    seen = []

    async def handler(req):
        seen.extend(req.messages)

    await mw.awrap_model_call(request, handler)
    assert snapshot in seen and handoff in seen
    assert not any(getattr(m, "tool_calls", None) for m in seen)


@pytest.mark.asyncio
async def test_system_and_tool_schema_alone_over_budget_fail_before_model():
    request = Request([HumanMessage("task")], SystemMessage("x" * 2000), [])

    async def handler(req):
        pytest.fail("Oversized request reached model")

    with pytest.raises(ValueError, match="budget"):
        await DynamicTrimMiddleware(max_tokens=400).awrap_model_call(request, handler)


def test_budget_must_checkpoint_before_compaction_deletes_receipts():
    from searchos.harness.middleware import (
        BudgetMiddleware,
        BudgetState,
        CompactionContextMiddleware,
        ControlState,
    )

    model = Model(responses=[AIMessage("done")])
    with pytest.raises(ValueError, match="BudgetMiddleware before CompactionContextMiddleware"):
        create_search_agent_graph(
            model,
            [],
            middleware=[
                CompactionContextMiddleware(model, context_window=4000),
                BudgetMiddleware(BudgetState(), ControlState(), scope="thread"),
            ],
        )
