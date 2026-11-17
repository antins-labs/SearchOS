"""轨迹数据模型、调用统计与追加式 JSONL 记录。"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import Field

from searchos.utils.base_model import CamelModel

logger = logging.getLogger(__name__)


class StateDelta(CamelModel):
    """The change a single step made to the search state."""

    coverage_before: float = 0.0
    coverage_after: float = 0.0
    new_evidence_count: int = 0
    frontier_resolved: list[str] = Field(default_factory=list)
    frontier_added: list[str] = Field(default_factory=list)
    conflicts_detected: int = 0
    conflicts_resolved: int = 0

    @property
    def coverage_gain(self) -> float:
        return self.coverage_after - self.coverage_before

    @property
    def is_valuable(self) -> bool:
        """Whether this step produced meaningful progress."""
        return (
            self.coverage_gain >= 0.05
            or self.new_evidence_count >= 1
            or len(self.frontier_resolved) >= 1
            or self.conflicts_resolved >= 1
        )


class TrajectoryStep(CamelModel):
    """One step in a search trajectory. Append-only to JSONL."""

    timestamp: str
    step_index: int = 0
    action: str  # tool name or description
    action_input_summary: str = ""  # truncated input
    observation_summary: str = ""  # truncated output
    state_delta: StateDelta = Field(default_factory=StateDelta)
    step_value: float = 0.0  # computed from state_delta


class TaskSummary(CamelModel):
    """End-of-task summary appended after all steps."""

    task_id: str
    task_type: str = ""
    query: str
    timestamp_start: str
    timestamp_end: str
    total_steps: int = 0
    total_queries: int = 0
    final_coverage: float = 0.0
    effective_strategies: list[str] = Field(default_factory=list)
    failed_strategies: list[str] = Field(default_factory=list)
    bottlenecks_encountered: list[str] = Field(default_factory=list)
    skills_used: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TrajectoryLogger:
    """追加轨迹记录，并通知进程内监听者。"""

    def __init__(self, path: str | Path | None = None) -> None:
        self._path: Path | None = Path(path) if path else None
        self._step_count = 0
        self._tool_counts: dict[str, int] = {}
        self._counted_calls: set[tuple] = set()
        self._skill_executions: set[str] = set()
        self._listeners: list = []

    def set_path(self, path: str | Path) -> None:
        """(Re)set the output path. Useful when workspace is created lazily."""
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def add_listener(self, cb) -> None:
        """监听共享 logger 的所有 Agent 事件，供 TUI 实时展示。"""
        self._listeners.append(cb)

    def log_phase(self, phase: str, status: str = "running", *, agent: str = "orchestrator") -> None:
        """记录当前执行阶段，沿用实时与历史轨迹通道。"""
        self._append_raw({"type": "harness", "kind": "run_phase", "phase": phase,
                          "status": status, "agent": agent})

    def log_step(self, step: TrajectoryStep) -> None:
        """Append a single search step to the trajectory file."""
        if self._path is None:
            return
        step.step_index = self._step_count
        if not step.timestamp:
            step.timestamp = _now_iso()
        step.step_value = self._compute_step_value(step.state_delta)
        self._append({"type": "step", **step.model_dump()})

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
        if record.get("type") == "skill_execution":
            self._skill_executions.add(record["execution_id"])
        if record.get("type") in {"step", "tool_call_started", "tool_call_failed"}:
            action = record.get("action")
            if isinstance(action, dict):
                action_name = str(action.get("name") or "")
            else:
                action_name = str(action or record.get("tool") or "")
            identifier = (record.get("agent"), record.get("tool_call_id"))
            if not identifier[1]:
                identifier = (record.get("agent"), record.get("step_index"), action_name)
            if action_name and identifier not in self._counted_calls:
                self._counted_calls.add(identifier)
                self._step_count += 1
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

    @property
    def skill_execution_count(self) -> int:
        return len(self._skill_executions)

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
