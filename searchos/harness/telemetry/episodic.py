"""Episodic Memory: trajectory logging for skill mining.

Phase 1: TrajectoryLogger — append-only JSONL, write-only.
Phase 3 will extend with retrieval and mining support.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from searchos.harness.telemetry.trajectory import StateDelta, TaskSummary, TrajectoryStep

logger = logging.getLogger(__name__)


class TrajectoryLogger:
    """Append-only trajectory recorder.

    Every search step and task summary is written to a JSONL file inside the
    workspace.  Phase 1 only writes; Phase 3 will add retrieval and export
    for Skill Mining.

    Usage::

        tl = TrajectoryLogger(workspace / "trajectory.jsonl")
        tl.log_step(TrajectoryStep(...))
        tl.log_task_summary(TaskSummary(...))
    """

    def __init__(self, path: str | Path | None = None) -> None:
        self._path: Path | None = Path(path) if path else None
        self._step_count = 0
        self._listeners: list = []

    def set_path(self, path: str | Path) -> None:
        """(Re)set the output path. Useful when workspace is created lazily."""
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def add_listener(self, cb) -> None:
        """Register an in-process callback fired on every appended event.

        Lets the live TUI observe trajectory events without tailing the file.
        All agents share one logger instance (via the orchestrator ContextVar),
        so a single listener sees orchestrator + sub-agent events.
        """
        self._listeners.append(cb)

    # ----- Write (Phase 1) -----

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

    # ----- Helpers -----

    def _append(self, record: dict) -> None:
        assert self._path is not None
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

    @staticmethod
    def _compute_step_value(delta: StateDelta) -> float:
        """Heuristic value score for a single step."""
        value = 0.0
        value += delta.coverage_gain * 2.0
        value += delta.new_evidence_count * 0.3
        value += len(delta.frontier_resolved) * 0.5
        value += delta.conflicts_resolved * 0.4
        return round(value, 4)

    # ----- Read (Phase 3 stub) -----

    def export_valuable_steps(self, min_value: float = 0.1) -> list[TrajectoryStep]:
        """Export high-value steps for Skill Mining."""
        if self._path is None or not self._path.exists():
            return []
        steps: list[TrajectoryStep] = []
        with open(self._path, encoding="utf-8") as f:
            for line in f:
                record = json.loads(line)
                if record.get("type") != "step":
                    continue
                step = TrajectoryStep.model_validate(record)
                if step.step_value >= min_value:
                    steps.append(step)
        return steps

    def load_task_summaries(self) -> list[TaskSummary]:
        """Load all task summaries."""
        if self._path is None or not self._path.exists():
            return []
        summaries: list[TaskSummary] = []
        with open(self._path, encoding="utf-8") as f:
            for line in f:
                record = json.loads(line)
                if record.get("type") != "task_summary":
                    continue
                summaries.append(TaskSummary.model_validate(record))
        return summaries

    # ----- Phase 3: Retrieval + Experience Reuse -----

    def retrieve_similar_tasks(
        self,
        task_type: str,
        query_keywords: list[str] | None = None,
        top_k: int = 3,
    ) -> list[TaskSummary]:
        """Retrieve historical tasks similar to the current one.

        Similarity heuristic:
        1. Same task_type (mandatory)
        2. Keyword overlap in query (optional, for ranking)
        3. Most recent first
        """
        summaries = self.load_task_summaries()
        # Filter by task_type
        candidates = [s for s in summaries if s.task_type == task_type]

        if query_keywords:
            # Score by keyword overlap
            def keyword_score(s: TaskSummary) -> int:
                q_lower = s.query.lower()
                return sum(1 for kw in query_keywords if kw.lower() in q_lower)

            candidates.sort(key=keyword_score, reverse=True)
        else:
            # Most recent first
            candidates.sort(key=lambda s: s.timestamp_end, reverse=True)

        return candidates[:top_k]

    def get_effective_strategies_for(self, bottleneck_type: str) -> list[str]:
        """Query which strategies historically worked for a bottleneck type.

        Scans task summaries for effective_strategies where the bottleneck
        was encountered.
        """
        summaries = self.load_task_summaries()
        strategies: list[str] = []
        for s in summaries:
            if bottleneck_type in s.bottlenecks_encountered:
                strategies.extend(s.effective_strategies)
        # Deduplicate while preserving order
        seen: set[str] = set()
        unique: list[str] = []
        for st in strategies:
            if st not in seen:
                seen.add(st)
                unique.append(st)
        return unique

    def get_skills_used_successfully(self) -> dict[str, int]:
        """Count how many times each skill was used in successful tasks.

        A task is "successful" if final_coverage >= 0.8.
        """
        summaries = self.load_task_summaries()
        counts: dict[str, int] = {}
        for s in summaries:
            if s.final_coverage >= 0.8:
                for skill_name in s.skills_used:
                    counts[skill_name] = counts.get(skill_name, 0) + 1
        return counts

    def export_for_mining(
        self,
        min_step_value: float = 0.1,
        task_type: str | None = None,
    ) -> list[TrajectoryStep]:
        """Export high-value steps for Skill Mining, optionally filtered by task type.

        If task_type is specified, only returns steps from tasks of that type.
        """
        if task_type is None:
            return self.export_valuable_steps(min_step_value)

        # Need to correlate steps with task summaries
        # For now, return all valuable steps (task-level filtering requires
        # step→task mapping which we don't have yet in Phase 3)
        return self.export_valuable_steps(min_step_value)

    @property
    def step_count(self) -> int:
        return self._step_count


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
