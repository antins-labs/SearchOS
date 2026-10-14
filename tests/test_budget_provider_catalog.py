"""预算边界经过真实 OpenAI 序列化；本地传输模拟严格校验工具名的网关。"""

import json

import httpx
import pytest
from langchain_core.messages import ToolMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

from searchos.agents.runtime import create_search_agent_graph
from searchos.harness.middleware import BudgetMiddleware, BudgetState, ControlState


@pytest.mark.asyncio
@pytest.mark.parametrize("exhausted", ["search", "open"])
async def test_exhausted_tool_reaches_budget_guard_instead_of_provider_400(exhausted):
    executed = []

    @tool
    def search(query: str) -> str:
        """Search sources."""
        executed.append("search")
        return "source found"

    @tool
    def open(id_or_url: str) -> str:
        """Read a source."""
        executed.append("open")
        return "source read"

    remaining = "open" if exhausted == "search" else "search"
    sequence = [exhausted, exhausted, remaining, exhausted, exhausted, exhausted, exhausted]
    payloads = []

    def respond(request):
        payload = json.loads(request.content)
        index = len(payloads)
        payloads.append(payload)
        name = sequence[index]
        names = {t["function"]["name"] for t in payload.get("tools", [])}
        if name not in names:
            return httpx.Response(400, json={"error": {
                "message": f'LLM is trying to invoke a non-exist tool: "{name}"',
                "type": "BadRequestError", "code": "400",
            }})
        args = {"query": "papers"} if name == "search" else {"id_or_url": "https://example.org"}
        return httpx.Response(200, json={
            "id": f"reply-{index}", "object": "chat.completion", "created": 0,
            "model": "fixture", "choices": [{"index": 0, "finish_reason": "tool_calls",
                "message": {"role": "assistant", "content": "", "tool_calls": [{
                    "id": f"call-{index}", "type": "function",
                    "function": {"name": name, "arguments": json.dumps(args)},
                }]}}],
        })

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        model = ChatOpenAI(model="fixture", api_key="fixture", base_url="https://model.invalid/v1",
                           http_async_client=client, max_retries=0)
        budget = BudgetState(max_queries=1 if exhausted == "search" else 3,
                             max_opens=1 if exhausted == "open" else 3, max_finds=15)
        control = ControlState()
        graph = create_search_agent_graph(
            model=model, tools=[search, open], middleware=[BudgetMiddleware(budget, control)],
            image_fallback=False,
        )
        result = await graph.ainvoke(
            {"messages": [("user", "Research papers")]},
            {"configurable": {"thread_id": exhausted}},
        )

    assert executed == [exhausted, remaining]
    assert control.reason == "budget_rejection_loop"
    assert len(payloads) == len(sequence)
    assert any(isinstance(m, ToolMessage) and m.additional_kwargs.get("sf_blocked")
               for m in result["messages"])
    assert not result["messages"][-1].tool_calls
    assert "partial" in result["messages"][-1].content
