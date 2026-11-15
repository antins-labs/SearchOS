"""Frontier 任务与持久化执行报告的只读窗口。"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.tools import tool

from searchos.tools.search_state import _ws
from searchos.socm.refs import cell_ref

_RESOLUTION_EXCERPT_CHARS = 200

def _task_snapshot(task: Any) -> dict[str, Any]:
    return {
        "id": task.id,
        "kind": task.kind,
        "agent_type": task.agent_type,
        "target_table": task.table_id,
        "status": task.status.value,
        "text": task.question,
        "priority": task.priority,
        "target_cells": [cell_ref(key) for key in task.target_cells],
        "blocked_by": list(task.blocked_by),
        "attempts": task.attempts,
        "assigned_agent_id": task.assigned_agent_id,
        "requested_agent_id": task.requested_agent_id,
        "created_by": task.created_by,
        "resolution_excerpt": task.resolution[:_RESOLUTION_EXCERPT_CHARS],
        "last_agent_report_excerpt": task.last_agent_report_excerpt,
    }


@tool(parse_docstring=True)
async def list_frontier(kind: str = "", status: str = "", limit: int = 50) -> str:
    """Inspect queued, running or completed tasks in priority order. Returns tasks, count and
    total_matched. Each resolution_excerpt contains up to 200 characters of the closing report. Use
    read_task_report for its full text when available.

    Args:
        kind: Filter by search, write or explore. Omit for all kinds.
        status: Filter by pending, running, completed, blocked or cancelled. Omit for all statuses.
        limit: Maximum tasks to return, default 50.
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


@tool(parse_docstring=True)
async def read_task_report(task_id: str) -> str:
    """Read a Frontier task's recorded outcome before assigning more work on the same cells.
    Returns task identity, targets, status, attempts, full resolution and
    last_agent_report_excerpt.

    The resolution is the worker's closing brief, including findings, dead ends and
    recommendations. The excerpt can include a failure summary for a recycled or cancelled task.

    Args:
        task_id: Task ID returned by list_frontier.
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
            "target_table": task.table_id,
            "status": task.status.value,
            "question": task.question,
            "target_cells": [cell_ref(key) for key in task.target_cells],
            "assigned_agent_id": task.assigned_agent_id,
            "attempts": task.attempts,
            "resolution": task.resolution,
            "last_agent_report_excerpt": task.last_agent_report_excerpt,
        },
        ensure_ascii=False,
    )
