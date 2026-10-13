"""以追加式 JSONL 记录搜索轨迹与任务摘要。"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from searchos.harness.telemetry.trajectory import StateDelta, TaskSummary, TrajectoryStep

logger = logging.getLogger(__name__)


class TrajectoryLogger:
    """追加轨迹记录，并通知进程内监听者。"""

    def __init__(self, path: str | Path | None = None) -> None:
        self._path: Path | None = Path(path) if path else None
        self._step_count = 0
        self._tool_counts: dict[str, int] = {}
        self._listeners: list = []

    def set_path(self, path: str | Path) -> None:
        """(Re)set the output path. Useful when workspace is created lazily."""
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def add_listener(self, cb) -> None:
        """监听共享 logger 的所有 Agent 事件，供 TUI 实时展示。"""
        self._listeners.append(cb)

    def log_step(self, step: TrajectoryStep) -> None:
        """Append a single search step to the trajectory file."""
        if self._path is None:
            return
        step.step_index = self._step_count
        if not step.timestamp:
            step.timestamp = _now_iso()
        step.step_value = self._compute_step_value(step.state_delta)
        self._append({"type": "step", **step.model_dump()})
        self._step_count += 1

    def log_task_summary(self, summary: TaskSummary) -> None:
        """Append an end-of-task summary."""
        if self._path is None:
            return
        if not summary.timestamp_end:
            summary.timestamp_end = _now_iso()
        self._append({"type": "task_summary", **summary.model_dump()})
        logger.info(
            "Task %s logged: %d steps, coverage=%.2f",
            summary.task_id,
            summary.total_steps,
            summary.final_coverage,
        )

    def _append(self, record: dict) -> None:
        assert self._path is not None
        if record.get("type") == "step":
            action = record.get("action")
            if isinstance(action, dict):
                action_name = str(action.get("name") or "")
            else:
                action_name = str(action or "")
            if action_name:
                self._tool_counts[action_name] = self._tool_counts.get(action_name, 0) + 1
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        for cb in self._listeners:
            try:
                cb(record)
            except Exception:
                pass

    def _append_raw(self, record: dict) -> None:
        """Append a raw event (non-step) to trajectory — e.g. skill_injection."""
        if self._path is None:
            return
        if "timestamp" not in record:
            record["timestamp"] = _now_iso()
        self._append(record)

    @property
    def step_count(self) -> int:
        return self._step_count

    @property
    def tool_counts(self) -> dict[str, int]:
        return dict(self._tool_counts)

    @staticmethod
    def _compute_step_value(delta: StateDelta) -> float:
        """Heuristic value score for a single step."""
        value = 0.0
        value += delta.coverage_gain * 2.0
        value += delta.new_evidence_count * 0.3
        value += len(delta.frontier_resolved) * 0.5
        value += delta.conflicts_resolved * 0.4
        return round(value, 4)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
