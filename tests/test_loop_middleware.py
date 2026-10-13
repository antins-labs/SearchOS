"""检测机制互相独立，装载决定是否产生信号。"""

from types import SimpleNamespace

import pytest
from langchain_core.messages import ToolMessage

from searchos.harness.middleware.sensor.core.models import ControlState
from searchos.harness.middleware.sensor.core.loops import (
    EmptyResultSensor,
    QueryRepetitionSensor,
    ReadingReminderSensor,
    StateStallSensor,
)
from searchos.harness.middleware import ReadingReminderMiddleware


@pytest.mark.asyncio
async def test_query_repetition_warns_then_escalates_independently():
    loops = []
    sensor = QueryRepetitionSensor(repetitions=2, on_loop=loops.append)
    assert await sensor.check("search", "", {"query": "Alpha"}) is None
    warning = await sensor.check("search", "", {"query": "ALPHA!"})
    assert warning["reason"] == "query_repetition"
    assert await sensor.check("search", "", {"query": "alpha"}) is None
    await sensor.check("search", "", {"query": "beta"})
    signal = await sensor.check("search", "", {"query": "beta"})
    assert signal["reason"] == "query_repetition_hard_loop"
    assert loops == ["beta"]


@pytest.mark.asyncio
async def test_reading_resets_search_reminder():
    sensor = ReadingReminderSensor(threshold=2)
    await sensor.check("search", "")
    await sensor.check("open", "A short valid source")
    assert await sensor.check("search", "") is None
    assert (await sensor.check("search", ""))["reason"] == "bare_search_without_progress"


@pytest.mark.asyncio
async def test_empty_result_uses_message_content_and_resets_on_substance():
    sensor = EmptyResultSensor(threshold=2)
    await sensor.check("open", "")
    assert await sensor.check("open", "source " * 30) is None
    assert await sensor.check("open", ToolMessage(content="", tool_call_id="x" * 120)) is None
    assert (await sensor.check("open", "error"))["strategy_switch"]


@pytest.mark.asyncio
async def test_pending_extraction_resets_state_stall():
    state = [0.0, 0, 0]
    stalled = []
    sensor = StateStallSensor(lambda: tuple(state), threshold=2, on_stall=stalled.append)
    await sensor.check("open", "")
    await sensor.check("open", "")
    state[2] = 1
    for _ in range(4):
        assert await sensor.check("open", "") is None
    state[2] = 0
    assert await sensor.check("open", "") is None
    assert (await sensor.check("open", ""))["reason"] == "state_delta_stall"
    assert await sensor.check("open", "") is None
    assert len(stalled) == 1


@pytest.mark.asyncio
async def test_only_loaded_sensors_emit_control_signals():
    control = ControlState()
    middleware = ReadingReminderMiddleware(control, threshold=1)
    request = SimpleNamespace(tool_call={"name": "search", "args": {}, "id": "read"})

    async def handler(_):
        return "error"

    await handler(request)
    assert control.messages == []
    await middleware.awrap_tool_call(request, handler)
    assert len(control.messages) == 1
    assert not control.strategy_switch
    assert not control.stopped


@pytest.mark.asyncio
async def test_public_query_component_records_warning_and_loop_without_callbacks():
    from searchos.harness.middleware import QueryRepetitionMiddleware, TaskContext
    from searchos.harness.middleware.extraction import InMemoryEvidenceStore

    workspace = InMemoryEvidenceStore()
    control = ControlState()
    middleware = QueryRepetitionMiddleware(
        control, workspace=workspace, task=TaskContext(agent_id="worker"), repetitions=2,
    )

    async def handler(_):
        return "a substantive source result " * 10

    for query in ["alpha", "ALPHA!", "beta", "beta"]:
        await middleware.awrap_tool_call(
            SimpleNamespace(tool_call={"name": "search", "args": {"query": query}, "id": query}),
            handler,
        )
    assert len(control.messages) == 1
    assert workspace.load_state().agent_status["worker"] == "looped"
    assert workspace.load_state().agent_dead_ends["worker"] == ["beta"]
    assert not control.forced


@pytest.mark.asyncio
async def test_public_reading_component_only_enables_reading_reminder():
    from searchos.harness.middleware import ReadingReminderMiddleware

    control = ControlState()
    middleware = ReadingReminderMiddleware(control, threshold=2)

    async def handler(_):
        return "error"

    request = SimpleNamespace(tool_call={"name": "search", "args": {"query": "same"}, "id": "x"})
    for _ in range(6):
        await middleware.awrap_tool_call(request, handler)
    assert len(control.messages) == 3
    assert not control.strategy_switch
    assert not control.forced
