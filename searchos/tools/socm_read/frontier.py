"""Frontier 任务与持久化执行报告的只读窗口。"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.tools import tool

from searchos.tools.search_state import _ws

_RESOLUTION_EXCERPT_CHARS = 200

def _task_snapshot(task: Any) -> dict[str, Any]:
    return {
        "id": task.id,
        "kind": task.kind,
        "agent_type": task.agent_type,
        "result_mode": task.result_mode,
        "status": task.status.value,
        "text": task.question,
        "priority": task.priority,
        "target_cells": list(task.target_cells),
        "blocked_by": list(task.blocked_by),
        "attempts": task.attempts,
        "assigned_agent_id": task.assigned_agent_id,
        "requested_agent_id": task.requested_agent_id,
        "created_by": task.created_by,
        "resolution_excerpt": task.resolution[:_RESOLUTION_EXCERPT_CHARS],
        "last_agent_report_excerpt": task.last_agent_report_excerpt,
    }


@tool
async def list_frontier(kind: str = "", status: str = "", limit: int = 50) -> str:
    """List frontier tasks with optional kind / status filters, sorted by priority. Each task carries ``resolution_excerpt`` (the dispatched agent's closing report, first 200 chars) — call ``read_task_report`` for the full text.

    Args:
        kind (str): ``"search"`` | ``"write"`` | ``"explore"`` — empty = all kinds.
        status (str): ``"pending"`` | ``"running"`` | ``"completed"`` | ``"blocked"`` | ``"cancelled"`` — empty = all statuses.
        limit (int): cap on returned tasks (default 50).
    """
    state = _ws().load_state()
    tasks = state.frontier.questions
    if kind:
        tasks = [t for t in tasks if t.kind == kind]
    if status:
        tasks = [t for t in tasks if t.status.value == status]
    total = len(tasks)
    tasks = sorted(tasks, key=lambda t: (-t.priority, -t.updated_at))[: max(1, int(limit))]
    return json.dumps(
        {"tasks": [_task_snapshot(t) for t in tasks], "count": len(tasks), "total_matched": total},
        ensure_ascii=False,
    )


@tool
async def read_task_report(task_id: str) -> str:
    """Read the full natural-language report a dispatched agent left on a frontier task: ``resolution`` (closing briefing — findings, dead ends, recommendations) and ``last_agent_report_excerpt`` (failure summary on recycled/cancelled tasks). Use before emitting a new task on the same cells.

    Args:
        task_id (str): frontier task id (from ``list_frontier``).
    """
    state = _ws().load_state()
    task = next((t for t in state.frontier.questions if t.id == task_id), None)
    if task is None:
        return json.dumps({"error": f"task {task_id!r} not found"})
    return json.dumps(
        {
            "task_id": task.id,
            "kind": task.kind,
        "agent_type": task.agent_type,
        "result_mode": task.result_mode,
            "status": task.status.value,
            "question": task.question,
            "target_cells": list(task.target_cells),
            "assigned_agent_id": task.assigned_agent_id,
            "attempts": task.attempts,
            "resolution": task.resolution,
            "last_agent_report_excerpt": task.last_agent_report_excerpt,
        },
        ensure_ascii=False,
    )
