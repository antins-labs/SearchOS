"""预算预留、取消释放和装载边界。"""

import asyncio
from types import SimpleNamespace

import pytest

from searchos.harness.middleware.sensor.budget_middleware import BudgetMiddleware
from searchos.harness.middleware.sensor.core.models import BudgetState, ControlState
from searchos.harness.middleware.utils.messages import is_blocked


def request(name="search"):
    return SimpleNamespace(tool_call={"name": name, "args": {}, "id": name})


@pytest.mark.asyncio
async def test_concurrent_calls_cannot_spend_the_same_capacity():
    budget = BudgetState(max_queries=1, max_opens=1)
    middleware = BudgetMiddleware(budget, ControlState())
    entered = asyncio.Event()
    release = asyncio.Event()
    calls = []

    async def handler(req):
        calls.append(req.tool_call["name"])
        entered.set()
        await release.wait()
        return "source"

    first = asyncio.create_task(middleware.awrap_tool_call(request(), handler))
    try:
        await asyncio.wait_for(entered.wait(), 1)
        assert is_blocked(await middleware.awrap_tool_call(request(), handler))
    finally:
        release.set()
        await first
    assert calls == ["search"]
    assert budget.consumed_queries == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel", [False, True])
async def test_failed_or_cancelled_call_releases_capacity(cancel):
    budget = BudgetState(max_queries=1)
    middleware = BudgetMiddleware(budget, ControlState())
    entered = asyncio.Event()

    async def failed(_):
        entered.set()
        if cancel:
            await asyncio.Event().wait()
        raise RuntimeError("retrieval failed")

    first = asyncio.create_task(middleware.awrap_tool_call(request(), failed))
    await asyncio.wait_for(entered.wait(), 1)
    if cancel:
        first.cancel()
    with pytest.raises(asyncio.CancelledError if cancel else RuntimeError):
        await first

    async def success(_):
        return "source"

    assert not is_blocked(await middleware.awrap_tool_call(request(), success))
    assert budget.consumed_queries == 1


@pytest.mark.asyncio
async def test_exhaustion_allows_drain_and_notifies_once():
    notifications = []
    budget = BudgetState(max_queries=1)
    control = ControlState()
    middleware = BudgetMiddleware(
        budget,
        control,
        drain_tools=frozenset({"check_agents"}),
        on_exhausted=lambda: notifications.append("exhausted"),
    )
    executed = []

    async def handler(req):
        executed.append(req.tool_call["name"])
        return "done"

    await middleware.awrap_tool_call(request(), handler)
    assert control.stopped
    assert is_blocked(await middleware.awrap_tool_call(request(), handler))
    assert await middleware.awrap_tool_call(request("check_agents"), handler) == "done"
    assert notifications == ["exhausted"]
    assert executed == ["search", "check_agents"]


@pytest.mark.asyncio
async def test_budget_prompt_is_injected_only_by_loaded_budget():
    from dataclasses import dataclass

    from langchain_core.messages import AIMessage

    from searchos.agents.execution import ControlExecutor, _ExecutionHooks
    from tests.middleware_utils import model_call

    @dataclass
    class Request:
        system_message: object = None

    async def handler(req):
        return AIMessage(content=str(req.system_message.content) if req.system_message else "")

    control = ControlState()
    stop = _ExecutionHooks(ControlExecutor(control))
    budget = BudgetMiddleware(BudgetState(max_queries=15), control)
    assert (await model_call([stop], Request(), handler)).content == ""
    assert "search: 15" in (await model_call([budget, stop], Request(), handler)).content
