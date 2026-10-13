import asyncio
from types import SimpleNamespace

from searchos.harness.middleware.sensor.budget_middleware import BudgetMiddleware
from searchos.harness.middleware.sensor.core.models import BudgetState, ControlState


def _request(name: str, call_id: str) -> SimpleNamespace:
    return SimpleNamespace(
        tool_call={"name": name, "args": {}, "id": call_id},
    )


def test_skill_calls_use_an_independent_budget_dimension() -> None:
    budget = BudgetState(max_queries=1, max_skills=1)
    middleware = BudgetMiddleware(
        budget=budget,
        control=ControlState(),
    )
    executed: list[str] = []

    async def handler(request):
        executed.append(request.tool_call["name"])
        return "result"

    first = asyncio.run(
        middleware.awrap_tool_call(
            _request("skill_data_worldbank_org", "skill-1"), handler,
        )
    )

    assert budget.consumed_skills == 1
    assert budget.consumed_queries == 0
    assert budget.skills_exhausted
    assert not budget.queries_exhausted
    assert not budget.fully_exhausted
    assert "skill budget is now exhausted" in first

    blocked = asyncio.run(
        middleware.awrap_tool_call(
            _request("skill_data_worldbank_org", "skill-2"), handler,
        )
    )
    assert "skill budget cannot fit this call" in blocked.content
    assert executed == ["skill_data_worldbank_org"]

    asyncio.run(middleware.awrap_tool_call(_request("search", "search-1"), handler))
    assert budget.consumed_queries == 1
    assert budget.fully_exhausted
    assert budget.exhaustion_detail() == "search 1/1, skill 1/1"
    assert executed == ["skill_data_worldbank_org", "search"]
