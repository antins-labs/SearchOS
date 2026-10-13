"""显式可选子 agent 继承调用方工具及自定义状态。"""

import pytest
from langchain.agents.middleware.types import AgentState
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool

from searchos.agents.runtime import create_search_agent_graph
from tests.test_middleware_runtime import Model


@pytest.mark.asyncio
async def test_raw_subagent_inherits_tools_and_custom_state():
    from langchain.agents.middleware.types import AgentMiddleware

    class State(AgentState):
        task_marker: str

    seen = []

    class Capture(AgentMiddleware):
        async def awrap_model_call(self, request, handler):
            seen.append((request.state.get("task_marker"), [t.name for t in request.tools]))
            return await handler(request)

    @tool
    def lookup(query: str) -> str:
        """Read the requested information."""
        return query

    parent = Model(
        responses=[
            AIMessage(
                "",
                tool_calls=[
                    {
                        "id": "delegate",
                        "name": "task",
                        "args": {"description": "Inspect data", "subagent_type": "reader"},
                    }
                ],
            ),
            AIMessage("Finished"),
        ]
    )
    child = Model(responses=[AIMessage("Found data")])
    graph = create_search_agent_graph(
        parent,
        [lookup],
        state_schema=State,
        subagents=[
            {
                "name": "reader",
                "description": "Inspect data",
                "system_prompt": "Inspect data",
                "model": child,
                "middleware": [Capture()],
            }
        ],
    )
    result = await graph.ainvoke(
        {"messages": [HumanMessage("Research")], "task_marker": "original-task"},
        {"configurable": {"thread_id": "optional-state"}},
    )
    assert result["messages"][-1].content == "Finished"
    assert seen == [("original-task", ["lookup"])]


@pytest.mark.asyncio
async def test_compaction_checks_actual_system_budget_before_model():
    from types import SimpleNamespace

    from langchain_core.messages import SystemMessage

    from searchos.harness.middleware import CompactionContextMiddleware

    middleware = CompactionContextMiddleware(
        Model(responses=[AIMessage("summary")]),
        context_window=1000,
    )
    request = SimpleNamespace(
        messages=[HumanMessage("task")],
        system_message=SystemMessage("rules " * 1000),
        tools=[],
    )

    async def forbidden(request):
        pytest.fail("Over-budget request reached model")

    with pytest.raises(ValueError, match="Actual model request exceeds compaction budget"):
        await middleware.awrap_model_call(request, forbidden)
