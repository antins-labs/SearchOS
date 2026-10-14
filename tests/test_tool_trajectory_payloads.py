"""Full tool payload persistence regression tests."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest


@pytest.mark.asyncio
async def test_agent_step_persists_full_tool_arguments_and_output(tmp_path):
    from searchos.harness.telemetry.episodic import TrajectoryLogger
    from searchos.harness.telemetry.recording import AgentRecorder

    trajectory = tmp_path / "trajectory.jsonl"
    logger = TrajectoryLogger(trajectory)
    middleware = AgentRecorder(
        logger=logger,
        agent_id="search_agent",
    )
    long_argument = "query-" + ("a" * 1200)
    long_output = "result-" + ("b" * 2400)
    request = SimpleNamespace(tool_call={
        "name": "custom_tool",
        "id": "call-1",
        "args": {"query": long_argument},
    })

    async def handler(_request):
        return SimpleNamespace(content=long_output)

    started = middleware.tool_started(request)
    middleware.tool_completed(request, await handler(request), started)

    record = json.loads(trajectory.read_text(encoding="utf-8").splitlines()[0])
    assert record["action"]["args"]["query"] == long_argument
    assert record["observation"] == long_output
    assert record["observation_preview"] == long_output[:500]


def test_orchestrator_tool_event_persists_full_arguments_and_result():
    from searchos.harness.session import _log_orchestrator_tool_events

    class CaptureLogger:
        def __init__(self):
            self.records = []

        def _append_raw(self, record):
            self.records.append(record)

    logger = CaptureLogger()
    pending = {}
    long_argument = "schema-" + ("x" * 1200)
    long_result = "output-" + ("y" * 2400)
    call = SimpleNamespace(tool_calls=[{
        "id": "call-2",
        "name": "create_schema",
        "args": {"tables_json": long_argument},
    }])
    result = SimpleNamespace(
        type="tool",
        tool_call_id="call-2",
        name="create_schema",
        content=long_result,
    )

    _log_orchestrator_tool_events(call, logger, pending)
    _log_orchestrator_tool_events(result, logger, pending)

    assert len(logger.records) == 1
    assert logger.records[0]["args"]["tables_json"] == long_argument
    assert logger.records[0]["result"] == long_result
    assert logger.records[0]["result_preview"] == long_result[:500]


@pytest.mark.asyncio
async def test_runtime_streams_tool_start_before_blocked_call_returns(tmp_path):
    import asyncio
    import sys
    from pathlib import Path

    from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
    from langchain_core.messages import AIMessage
    from langchain_core.tools import tool

    from searchos.agents.runtime import create_search_agent_graph
    from searchos.harness.telemetry.episodic import TrajectoryLogger

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "web"))
    from api.routes.stream import _stream_jsonl

    entered, release = asyncio.Event(), asyncio.Event()

    class Model(FakeMessagesListChatModel):
        def bind_tools(self, tools, **kwargs):
            return self

    @tool
    async def slow_lookup(query: str) -> str:
        """Read a source that takes time."""
        entered.set()
        await release.wait()
        return "source ready"

    path = tmp_path / "trajectory.jsonl"
    graph = create_search_agent_graph(
        Model(responses=[
            AIMessage(content="正在查询论文", tool_calls=[{
                "id": "lookup-1", "name": "slow_lookup", "args": {"query": "RSI"},
            }]),
            AIMessage(content="查完了"),
        ]), [slow_lookup], name="orchestrator", trajectory_logger=TrajectoryLogger(path),
    )
    run = asyncio.create_task(graph.ainvoke(
        {"messages": [("user", "研究 RSI")]},
        {"configurable": {"thread_id": "live-tool"}},
    ))
    events, positions = [], {}

    async def send_json(event):
        events.append(event["data"])

    try:
        await asyncio.wait_for(entered.wait(), 2)
        await _stream_jsonl(SimpleNamespace(send_json=send_json), path, "trajectory", positions)
        starts = [e for e in events if e["type"] == "tool_call_started"]
        assert len(starts) == 1
        assert starts[0]["tool_call_id"] == "lookup-1"
        assert starts[0]["args"] == {"query": "RSI"}
        assert starts[0]["reasoning"] == "正在查询论文"
        assert not any(e["type"] == "step" for e in events)
        release.set()
        await asyncio.wait_for(run, 2)
        await _stream_jsonl(SimpleNamespace(send_json=send_json), path, "trajectory", positions)
        steps = [e for e in events if e["type"] == "step"]
        assert len(steps) == 1 and steps[0]["tool_call_id"] == starts[0]["tool_call_id"]
        assert steps[0]["observation"] == "source ready"
    finally:
        run.cancel()
        await asyncio.gather(run, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["error", "cancelled"])
async def test_recording_closes_failed_or_cancelled_tool(outcome, tmp_path):
    import asyncio

    from searchos.agents.execution import _RecordingHooks
    from searchos.harness.telemetry.episodic import TrajectoryLogger
    from searchos.harness.telemetry.recording import AgentRecorder

    path = tmp_path / "trajectory.jsonl"
    hooks = _RecordingHooks(AgentRecorder(
        TrajectoryLogger(path), agent_id="orchestrator", emit_started=True,
    ))
    request = SimpleNamespace(tool_call={"id": "failed-1", "name": "check_agents", "args": {}})

    async def handler(_request):
        if outcome == "cancelled":
            raise asyncio.CancelledError()
        raise RuntimeError("failed lookup")

    with pytest.raises(asyncio.CancelledError if outcome == "cancelled" else RuntimeError):
        await hooks.awrap_tool_call(request, handler)
    records = [json.loads(line) for line in path.read_text().splitlines()]
    assert [record["type"] for record in records] == ["tool_call_started", "tool_call_failed"]
    assert records[1]["tool_call_id"] == records[0]["tool_call_id"]
    assert records[1]["status"] == outcome
