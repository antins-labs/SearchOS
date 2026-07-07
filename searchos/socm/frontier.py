"""SOCM · Frontier Memory — the task-scheduling queue (paper §Frontier).

Search / write / explore tasks share one pool; DAG dependencies via
``blocked_by``; the scheduler dispatches the highest-priority unblocked task.
"""

from __future__ import annotations

import time
from enum import Enum
from typing import Literal

from pydantic import Field

from searchos.util.base_model import CamelModel


class FrontierTaskStatus(str, Enum):
    PENDING = "pending"      # queued, not yet dispatched
    RUNNING = "running"      # dispatched to a sub-agent
    COMPLETED = "completed"
    BLOCKED = "blocked"      # waiting on `blocked_by` tasks
    CANCELLED = "cancelled"  # max attempts, cycle, or explicit drop


class FrontierTask(CamelModel):
    """Unified Frontier task — search / write / explore."""

    id: str
    question: str
    kind: Literal["search", "write", "explore"] = "search"

    status: FrontierTaskStatus = FrontierTaskStatus.PENDING
    priority: float = 0.5  # 0-1, higher = more important

    parent_id: str = ""
    depth: int = 0
    blocked_by: list[str] = Field(default_factory=list)

    target_cells: list[str] = Field(default_factory=list)
    table_id: str = ""

    # Dispatch hints set at enqueue; Scheduler consumes them when spawning.
    # Empty agent_type → Scheduler infers from `kind`.
    agent_type: str = ""
    skills: list[str] = Field(default_factory=list)
    # Per-task search budget; None → agent-type override / settings default.
    max_searches: int | None = None
    # Full sub-agent prompt; falls back to ``question`` when empty (keeps
    # ``question`` short for list_frontier display).
    task_prompt: str = ""

    assigned_agent_id: str = ""
    attempts: int = 0
    # Earliest wall-clock time this task may be (re-)dispatched — set by the
    # 429-recycle path so the next tick doesn't refill straight into the limit.
    not_before: float = 0.0
    created_by: str = ""  # explore | orchestrator | search | writer | sensor | scheduler | user
    last_agent_report_excerpt: str = ""

    created_at: float = 0.0
    updated_at: float = 0.0

    resolution: str = ""


MAX_FRONTIER_DEPTH = 5
MAX_FRONTIER_CAP = 200
MAX_TASK_ATTEMPTS = 3


def _normalize_task_text(text: str) -> str:
    """Lowercase + collapse whitespace — dedup signature."""
    return " ".join((text or "").strip().lower().split())


class FrontierMemory(CamelModel):
    """Task pool for search / write / explore work."""

    questions: list[FrontierTask] = Field(default_factory=list)

    @property
    def open_questions(self) -> list[FrontierTask]:
        return [q for q in self.questions if q.status == FrontierTaskStatus.PENDING]

    @property
    def resolved_count(self) -> int:
        return sum(1 for q in self.questions if q.status == FrontierTaskStatus.COMPLETED)

    @staticmethod
    def _dedup_key(task: FrontierTask) -> tuple:
        # Keys on the FULL task text (task_prompt|question): ``question`` is
        # truncated at enqueue, so backfill tasks sharing a long template
        # prefix would all collide and get silently swallowed.
        return (task.kind, _normalize_task_text(task.task_prompt or task.question))

    def _find_duplicate(self, task: FrontierTask) -> FrontierTask | None:
        active = (FrontierTaskStatus.PENDING,
                  FrontierTaskStatus.RUNNING,
                  FrontierTaskStatus.BLOCKED)

        # Only entity.attr cells join subset-dedup; char-split / free-text
        # cells fall back to text-dedup, else char-set subsets false-merge.
        def _cellish(cells: list[str]) -> bool:
            return all("." in c for c in cells)

        if task.kind == "search" and task.target_cells and _cellish(task.target_cells):
            new_cells = frozenset(task.target_cells)
            for q in self.questions:
                if q.kind != "search" or q.status not in active:
                    continue
                if not q.target_cells or not _cellish(q.target_cells):
                    continue
                if new_cells.issubset(frozenset(q.target_cells)):
                    return q
            return None

        if task.kind == "write":
            for q in self.questions:
                if q.kind == "write" and q.status in active:
                    return q
            return None

        key = self._dedup_key(task)
        for q in self.questions:
            if q.status not in active:
                continue
            if self._dedup_key(q) == key:
                return q
        return None

    # ---- Add / state flips ----
    def add(self, question: FrontierTask) -> FrontierTask | None:
        """Insert a task. depth > MAX → reject; dedup hit → bump priority and
        return existing; over cap → evict lowest-priority PENDING first."""
        if question.depth > MAX_FRONTIER_DEPTH:
            return None
        dup = self._find_duplicate(question)
        if dup is not None:
            if question.priority > dup.priority:
                dup.priority = question.priority
                dup.updated_at = time.time()
            return dup
        now = time.time()
        if question.created_at == 0.0:
            question.created_at = now
        question.updated_at = now
        # A PENDING task with unfinished deps starts BLOCKED; the scheduler
        # flips it back to PENDING once they finish (serial-parallel waves).
        if question.status == FrontierTaskStatus.PENDING and question.blocked_by:
            terminal = {
                q.id for q in self.questions
                if q.status in (FrontierTaskStatus.COMPLETED,
                                FrontierTaskStatus.CANCELLED)
            }
            if not all(d in terminal for d in question.blocked_by):
                question.status = FrontierTaskStatus.BLOCKED
        self._evict_if_over_cap()
        self.questions.append(question)
        return question

    def _evict_if_over_cap(self) -> None:
        """Drop lowest-priority PENDING items when the ACTIVE pool would
        exceed the cap. Terminal tasks are kept for audit (cap governs
        in-flight work, not history)."""
        active = [
            q for q in self.questions
            if q.status in (FrontierTaskStatus.PENDING,
                            FrontierTaskStatus.RUNNING,
                            FrontierTaskStatus.BLOCKED)
        ]
        if len(active) < MAX_FRONTIER_CAP:
            return
        open_items = [q for q in active if q.status == FrontierTaskStatus.PENDING]
        open_items.sort(key=lambda q: (q.priority, q.created_at))  # lowest, oldest first
        needed = len(active) - MAX_FRONTIER_CAP + 1
        now = time.time()
        for q in open_items[:needed]:
            q.status = FrontierTaskStatus.CANCELLED
            q.last_agent_report_excerpt = "[dropped] frontier cap evict"
            q.updated_at = now

    def resolve(self, question_id: str, resolution: str) -> None:
        for q in self.questions:
            if q.id == question_id:
                q.status = FrontierTaskStatus.COMPLETED
                q.resolution = resolution
                q.updated_at = time.time()
                return

    def set_running(self, question_id: str, worker: str = "") -> None:
        for q in self.questions:
            if q.id == question_id:
                q.status = FrontierTaskStatus.RUNNING
                q.assigned_agent_id = worker
                q.attempts += 1
                q.updated_at = time.time()
                return

    def next(self, kind_filter: str | None = None) -> FrontierTask | None:
        """Atomic take-and-mark: pick the highest-priority READY PENDING task
        (no pending deps, attempts < MAX), flip to RUNNING, return it.

        Callers inside ``atomic_update_state`` get take-and-mark in one
        critical section — the recommended pattern.
        """
        done_ids = {
            q.id for q in self.questions
            if q.status in (FrontierTaskStatus.COMPLETED,
                            FrontierTaskStatus.CANCELLED)
        }
        candidates = []
        for q in self.questions:
            if q.status != FrontierTaskStatus.PENDING:
                continue
            if q.attempts >= MAX_TASK_ATTEMPTS:
                continue
            if kind_filter and q.kind != kind_filter:
                continue
            if q.blocked_by and not all(b in done_ids for b in q.blocked_by):
                continue
            candidates.append(q)
        if not candidates:
            return None
        candidates.sort(key=lambda q: (-q.priority, q.depth, q.created_at))
        pick = candidates[0]
        pick.status = FrontierTaskStatus.RUNNING
        pick.attempts += 1
        pick.updated_at = time.time()
        return pick

    # ---- Read views ----
    def by_kind(self, kind: str) -> list[FrontierTask]:
        return [q for q in self.questions if q.kind == kind]

    def pending_count(self) -> int:
        return sum(
            1 for q in self.questions
            if q.status in (FrontierTaskStatus.PENDING,
                            FrontierTaskStatus.RUNNING,
                            FrontierTaskStatus.BLOCKED)
        )
