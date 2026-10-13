import asyncio
import json

from langchain_core.messages import ToolMessage

from searchos.harness.middleware.sensor.core.coverage_stall_sensor import (
    CoverageStallSensor,
)
from searchos.socm import SearchState


class _Workspace:
    def __init__(self) -> None:
        self.state = SearchState()
        self.state.coverage_map.initialize(
            ["row-1"], ["name", "value"], primary_key=["name"]
        )

    def load_state(self) -> SearchState:
        return self.state


def _check(sensor: CoverageStallSensor, reports: list[dict]) -> dict | None:
    result = ToolMessage(
        content=json.dumps({"reports": reports, "remaining": 0}),
        tool_call_id="check-1",
        name="check_agents",
    )
    return asyncio.run(sensor.check("check_agents", result))


def _search_report() -> list[dict]:
    return [{"kind": "search", "agent_id": "search_agent", "status": "completed"}]


def test_stops_after_consecutive_search_results_without_coverage_growth() -> None:
    workspace = _Workspace()
    sensor = CoverageStallSensor(workspace, max_stalled_rounds=2)

    assert _check(sensor, _search_report()) is None
    signal = _check(sensor, _search_report())

    assert signal == {
        "force_stop": True,
        "reason": "coverage_stalled_x2",
        "hard_block_tools": ["enqueue_tasks"],
    }


def test_new_rows_and_newly_filled_cells_reset_stall_counter() -> None:
    workspace = _Workspace()
    sensor = CoverageStallSensor(workspace, max_stalled_rounds=2)

    assert _check(sensor, _search_report()) is None
    workspace.state.coverage_map.add_entity("row-2")
    assert _check(sensor, _search_report()) is None

    assert _check(sensor, _search_report()) is None
    workspace.state.coverage_map.fill(
        "row-2",
        "value",
        finding_id="finding-1",
        alignment="full",
        display_hint="new value",
    )
    assert _check(sensor, _search_report()) is None

    assert _check(sensor, _search_report()) is None
    assert _check(sensor, _search_report())["reason"] == "coverage_stalled_x2"


def test_ignores_empty_non_search_and_malformed_agent_results() -> None:
    workspace = _Workspace()
    sensor = CoverageStallSensor(workspace, max_stalled_rounds=1)

    assert _check(sensor, []) is None
    assert _check(sensor, [{"kind": "writer", "agent_id": "writer_agent"}]) is None
    assert asyncio.run(sensor.check("check_agents", "not json")) is None

    assert _check(sensor, _search_report())["reason"] == "coverage_stalled_x1"


def test_zero_threshold_disables_coverage_stall_stop() -> None:
    workspace = _Workspace()
    sensor = CoverageStallSensor(workspace, max_stalled_rounds=0)

    for _ in range(5):
        assert _check(sensor, _search_report()) is None
