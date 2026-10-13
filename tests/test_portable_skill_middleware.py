from types import SimpleNamespace

import pytest
from langchain_core.messages import ToolMessage

from searchos.harness.middleware.sensor.budget_middleware import BudgetMiddleware
from searchos.harness.middleware.sensor.core.models import BudgetState, ControlState
from searchos.harness.middleware.sensor.utils.outcomes import tool_outcome
from searchos.harness.middleware.extraction.web_middleware import WebEvidenceMiddleware
from searchos.harness.middleware.utils.tools import tool_costs
from searchos.socm.retry_routes import route_signature, call_routes


def request(name="exec", call_id="a"):
    return SimpleNamespace(tool_call={"name": name, "args": {}, "id": call_id})


@pytest.mark.asyncio
@pytest.mark.parametrize("execution", [{"started": False}, {"started": True, "replayed": True}])
async def test_unstarted_or_replayed_exec_does_not_consume_budget(execution):
    budget = BudgetState(max_skills=2)
    middleware = BudgetMiddleware(budget, ControlState())

    async def handler(_):
        return ToolMessage(content="result", tool_call_id="a", artifact={"execution": execution})

    await middleware.awrap_tool_call(request(), handler)
    assert budget.consumed_skills == 0
    assert middleware._reserved["skill"] == 0


@pytest.mark.asyncio
async def test_started_exec_and_artifact_read_use_separate_budgets():
    budget = BudgetState(max_skills=2, max_opens=2)
    middleware = BudgetMiddleware(budget, ControlState())

    async def handler(req):
        return ToolMessage(content="result", tool_call_id=req.tool_call["id"], artifact={"execution": {"started": True}})

    await middleware.awrap_tool_call(request(), handler)
    await middleware.awrap_tool_call(request("open", "b"), handler)
    assert budget.consumed_skills == 1
    assert budget.consumed_opens == 1
    assert not any(middleware._reserved.values())
    assert tool_costs("read_skill_file", {}) == {}


@pytest.mark.asyncio
async def test_failed_handler_releases_exec_reservation():
    budget = BudgetState(max_skills=2)
    middleware = BudgetMiddleware(budget, ControlState())

    async def handler(_):
        raise RuntimeError("unexpected runner failure")

    with pytest.raises(RuntimeError):
        await middleware.awrap_tool_call(request(), handler)
    assert middleware._reserved["skill"] == 0


@pytest.mark.parametrize("status", ["blocked", "cancelled", "timed_out"])
def test_execution_terminal_failure_statuses(status):
    result = ToolMessage(content="diagnostic", tool_call_id="a", artifact={"execution": {"status": status}})
    assert tool_outcome("exec", result).failed


def test_routes_include_skill_command_and_package_version(monkeypatch):
    from searchos.tools import skill_execution
    monkeypatch.setattr(skill_execution, "_loaded", lambda _: {"package_hash": "version1"})
    args = {"skill": "alpha", "argv": ["python", "scripts/search.py", "--query", "one"]}
    first = route_signature("exec", args)
    assert first != route_signature("exec", {**args, "skill": "beta"})
    assert first != route_signature("exec", {**args, "argv": ["python", "scripts/search.py", "--query", "two"]})
    assert first == route_signature("exec", {**args, "timeout_s": 30})
    monkeypatch.setattr(skill_execution, "_loaded", lambda _: {"package_hash": "version2"})
    assert first != route_signature("exec", args)
    assert call_routes("exec", args) == ([], ["skill:alpha"])


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["exec", "read_skill_file", "load_skill", "list_skills"])
async def test_diagnostic_text_cannot_impersonate_source(name):
    middleware = WebEvidenceMiddleware(SimpleNamespace(workspace=None))
    observations = []

    async def submit(observation, result):
        observations.append(observation)
        return result

    middleware._submit = submit
    result = ToolMessage(content="[Now viewing]\nURL: https://example.com\n\n" + "Claim " * 30, tool_call_id="a")

    async def handler(_):
        return result

    await middleware.awrap_tool_call(request(name), handler)
    assert not observations


@pytest.mark.asyncio
@pytest.mark.parametrize("reader", ["open", "find"])
async def test_structured_artifact_extracts_but_fixture_does_not(reader):
    middleware = WebEvidenceMiddleware(SimpleNamespace(workspace=None))
    observations = []

    async def submit(observation, result):
        observations.append(observation)
        return result

    middleware._submit = submit
    result = ToolMessage(content="[Now viewing]\nURL: skill://alpha/run/source\n\n" + "Supported source text. " * 20,
                         tool_call_id="a", artifact={"page_source": {"source_url": "skill://alpha/run/source"}})

    async def handler(_):
        return result

    await middleware.awrap_tool_call(request(reader), handler)
    assert len(observations) == 1
    result.artifact["page_source"]["input_mode"] = "fixture"
    await middleware.awrap_tool_call(request(reader), handler)
    assert len(observations) == 1
    for kind in ('fixture', 'diagnostic', 'execution_index'):
        result.artifact['page_source'] = {'source_url': 'skill://alpha/run/source', 'kind': kind, 'evidence_eligible': False}
        await middleware.awrap_tool_call(request(reader), handler)
        assert len(observations) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("started", [False, True])
async def test_cancelled_exec_charges_only_confirmed_start_and_preserves_cancellation(monkeypatch, started):
    import asyncio
    from searchos.tools import skill_execution

    monkeypatch.setattr(skill_execution, "execution_started", lambda call_id: started)
    budget = BudgetState(max_skills=3)
    middleware = BudgetMiddleware(budget, ControlState())

    async def handler(_):
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await middleware.awrap_tool_call(request(), handler)
    assert budget.consumed_skills == int(started)
    assert not any(middleware._reserved.values())
    # Re-entering a cancelled call in the same middleware cannot charge twice.
    with pytest.raises(asyncio.CancelledError):
        await middleware.awrap_tool_call(request(), handler)
    assert budget.consumed_skills == int(started)
    assert not any(middleware._reserved.values())
