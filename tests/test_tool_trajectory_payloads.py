"""Full tool payload persistence regression tests."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest


@pytest.mark.asyncio
async def test_agent_step_persists_full_tool_arguments_and_output(tmp_path):
    from searchos.harness.middleware.sensor.harness import HarnessMiddleware
    from searchos.harness.telemetry.episodic import TrajectoryLogger

    trajectory = tmp_path / "trajectory.jsonl"
    logger = TrajectoryLogger(trajectory)
    middleware = HarnessMiddleware(
        trajectory_logger=logger,
        worker_name="search_agent",
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

    await middleware.awrap_tool_call(request, handler)

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
