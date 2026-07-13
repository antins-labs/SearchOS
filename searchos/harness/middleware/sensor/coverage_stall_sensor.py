"""Stop orchestration after repeated search-agent returns add no coverage.

The orchestrator may keep dispatching rescue waves even when every completed
search agent leaves the coverage map unchanged.  This sensor observes only
non-empty ``check_agents`` returns containing search reports and maintains a
monotonic high-water mark of rows and filled cells.  New rows or newly filled
cells reset the stall counter; otherwise the counter advances.

Writer and Explore reports are deliberately ignored because those agents are
not expected to fill the coverage map.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from searchos.harness.middleware.sensor.base import Sensor

logger = logging.getLogger(__name__)

_CHECK_TOOL = "check_agents"
_DISPATCH_TOOLS = ["enqueue_tasks"]


class CoverageStallSensor(Sensor):
    """Hard-stop new dispatches after consecutive no-growth result rounds.

    ``max_stalled_rounds <= 0`` disables the sensor.  State is per harness
    run, so both the high-water mark and counter reset between queries.
    """

    trigger_on: str = "every_step"

    def __init__(self, workspace: Any, max_stalled_rounds: int = 3) -> None:
        self._workspace = workspace
        self._max_stalled_rounds = max_stalled_rounds
        self._stalled_rounds = 0
        self._stopped = False
        self._seen_rows: set[tuple[str, str]] = set()
        self._seen_filled_cells: set[str] = set()
        self._update_high_water_mark()

    async def check(
        self, tool_name: str, tool_result: Any, tool_input: Any = None,
    ) -> dict[str, Any] | None:
        if (
            tool_name != _CHECK_TOOL
            or self._max_stalled_rounds <= 0
            or self._stopped
        ):
            return None

        payload = self._parse_payload(tool_result)
        if payload is None:
            return None
        reports = payload.get("reports")
        if not isinstance(reports, list) or not any(
            isinstance(report, dict) and report.get("kind") == "search"
            for report in reports
        ):
            return None

        snapshot = self._coverage_snapshot()
        if snapshot is None:
            # Persistence/read failures must not terminate a productive run.
            return None
        rows, filled_cells = snapshot
        new_rows = rows - self._seen_rows
        new_filled_cells = filled_cells - self._seen_filled_cells
        self._seen_rows.update(rows)
        self._seen_filled_cells.update(filled_cells)

        if new_rows or new_filled_cells:
            self._stalled_rounds = 0
            return None

        self._stalled_rounds += 1
        if self._stalled_rounds < self._max_stalled_rounds:
            return None

        self._stopped = True
        reason = f"coverage_stalled_x{self._stalled_rounds}"
        logger.warning(
            "CoverageStallSensor: %d consecutive search-agent result rounds "
            "added no rows or filled cells — stopping new dispatches",
            self._stalled_rounds,
        )
        return {
            "force_stop": True,
            "reason": reason,
            "hard_block_tools": _DISPATCH_TOOLS,
        }

    def _update_high_water_mark(self) -> None:
        snapshot = self._coverage_snapshot()
        if snapshot is None:
            return
        rows, filled_cells = snapshot
        self._seen_rows.update(rows)
        self._seen_filled_cells.update(filled_cells)

    def _coverage_snapshot(
        self,
    ) -> tuple[set[tuple[str, str]], set[str]] | None:
        try:
            state = self._workspace.load_state()
            coverage = state.coverage_map
            rows = {
                (table_id, entity)
                for table_id, table in coverage.tables.items()
                for entity in table.entities
            }
            filled_cells = {
                key
                for key, cell in coverage.cells.items()
                if getattr(cell.status, "value", cell.status) == "filled"
            }
            return rows, filled_cells
        except Exception:  # noqa: BLE001 - sensors must fail open
            logger.debug("CoverageStallSensor could not read coverage", exc_info=True)
            return None

    @staticmethod
    def _parse_payload(tool_result: Any) -> dict[str, Any] | None:
        content = getattr(tool_result, "content", tool_result)
        if isinstance(content, dict):
            return content
        if not isinstance(content, str):
            return None
        try:
            payload = json.loads(content)
        except (json.JSONDecodeError, TypeError):
            return None
        return payload if isinstance(payload, dict) else None
