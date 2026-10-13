import asyncio
from types import SimpleNamespace

from langchain_core.messages import ToolMessage

from searchos.harness.middleware.sensor.core.models import ControlState
from searchos.harness.middleware.sensor.progress_middleware import ToolProgressMiddleware
from searchos.agents.execution import ControlExecutor
from searchos.socm import FrontierTask, FrontierTaskStatus, SearchState
from searchos.tools.tasks import _agent_creation_slots_used_for_frontier_kind


def test_no_progress_stop_blocks_dynamic_skill_tools() -> None:
    control = ControlState()
    progress = ToolProgressMiddleware(control, limit=3)
    stop = ControlExecutor(control)
    delta = SimpleNamespace(coverage_gain=0.0, new_evidence_count=0)
    for name in ("search", "open", "skill_r_jina_ai"):
        progress.observe(name, delta, "obs")
    assert control.stopped

    async def handler(_request):
        raise AssertionError("blocked skill should not execute")

    req = SimpleNamespace(tool_call={"name": "skill_r_jina_ai", "args": {}, "id": "tool-1"})
    blocked = asyncio.run(stop.call_tool(req, handler))
    assert isinstance(blocked, ToolMessage)
    assert "hard-blocked" in blocked.content


def test_agent_creation_limit_counts_non_cancelled_frontier_task_slots() -> None:
    state = SearchState()
    state.frontier.add(FrontierTask(id="s1", question="search one", kind="search"))
    state.frontier.add(
        FrontierTask(
            id="s2",
            question="cancelled search",
            kind="search",
            status=FrontierTaskStatus.CANCELLED,
        )
    )
    state.frontier.add(FrontierTask(id="e1", question="explore", kind="explore"))

    assert _agent_creation_slots_used_for_frontier_kind(state, "search") == 1
    assert _agent_creation_slots_used_for_frontier_kind(state, "explore") == 1
