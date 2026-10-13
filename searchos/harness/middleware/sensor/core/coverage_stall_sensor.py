"""按完整任务波次检测停滞，兼顾阅读、事实、任务关联及表格进展。

保留 CoverageStallSensor 名称兼容已有配置；阅读进展不等于答案证据。
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

from searchos.harness.middleware.sensor.core.base import Sensor

logger = logging.getLogger(__name__)

_CHECK_TOOL = "check_agents"
_DISPATCH_TOOLS = ["enqueue_tasks"]


class CoverageStallSensor(Sensor):
    """Hard-stop new dispatches after consecutive no-growth result rounds.

    ``max_stalled_rounds <= 0`` disables the sensor.  State is per harness
    run, so both the high-water mark and counter reset between queries.
    """

    trigger_on: str = "every_step"

    def __init__(
        self,
        workspace: Any,
        max_stalled_rounds: int = 3,
        *,
        source_progress: Callable[[], set[str]] | None = None,
    ) -> None:
        self._workspace = workspace
        self._source_progress = source_progress
        self._seen_reads: set[str] = set()
        self._max_stalled_rounds = max_stalled_rounds
        self._stalled_rounds = 0
        self._stopped = False
        self._seen_rows: set[tuple[str, str]] = set()
        self._seen_filled_cells: set[str] = set()
        self._seen_findings: set[tuple[str, ...]] = self._findings_snapshot()
        self._update_high_water_mark()

    async def check(
        self,
        tool_name: str,
        tool_result: Any,
        tool_input: Any = None,
    ) -> dict[str, Any] | None:
        if tool_name != _CHECK_TOOL or self._max_stalled_rounds <= 0 or self._stopped:
            return None

        payload = self._parse_payload(tool_result)
        if payload is None:
            return None
        # A fast, empty report does not describe the yield of its whole wave.
        # Let already dispatched readers finish before judging stagnation.
        if payload.get("remaining", 0) or payload.get("running_ids"):
            return None
        reports = payload.get("reports")
        if not isinstance(reports, list) or not any(
            isinstance(report, dict) and report.get("kind") == "search" for report in reports
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

        try:
            reads = self._source_progress() if self._source_progress else set()
        except Exception:
            logger.debug("Reading progress snapshot unavailable", exc_info=True)
            return None
        new_reads = reads - self._seen_reads
        self._seen_reads.update(reads)
        findings = self._findings_snapshot()
        new_findings = findings - self._seen_findings
        self._seen_findings.update(findings)
        if new_rows or new_filled_cells or new_findings or new_reads:
            self._stalled_rounds = 0
            return None

        self._stalled_rounds += 1
        if self._stalled_rounds < self._max_stalled_rounds:
            return None

        self._stopped = True
        reason = f"coverage_stalled_x{self._stalled_rounds}"
        logger.warning(
            "CoverageStallSensor: %d consecutive search-agent result rounds "
            "added no reading, facts, task bindings or coverage — stopping new dispatches",
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

    def _findings_snapshot(self) -> set[tuple[str, ...]]:
        try:
            state = self._workspace.load_state()
            from searchos.socm.coverage import answer_evidence

            active_ids = {node.id for node in answer_evidence(state)}
            return {(eid,) for eid in active_ids} | {
                (binding.task_id, binding.evidence_id, binding.relation)
                for binding in state.evidence_graph.task_bindings
                if binding.evidence_id in active_ids
            }
        except Exception:
            return set()

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
