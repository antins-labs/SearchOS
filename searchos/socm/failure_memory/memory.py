"""Failure Memory 的唯一写入入口与任务范围解析。"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from searchos.socm.failure_memory.models import FailureMemory, FailureScope

logger = logging.getLogger(__name__)


def source_scope_key(scope: Any) -> str:
    value = json.dumps(scope, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(value.encode()).hexdigest()


def assigned_task(state: Any, task_id: str = "", agent_id: str = "") -> Any:
    tasks = state.frontier.questions
    if task_id:
        return next((task for task in tasks if task.id == task_id), None)
    return next(
        (task for task in tasks if task.assigned_agent_id == agent_id and task.status == "running"),
        None,
    )


def scope_for_task(
    state: Any, task_id: str = "", agent_id: str = "", *, shared: bool = False
) -> FailureScope:
    task = assigned_task(state, task_id, agent_id)
    scope = FailureScope(source_scope_key=source_scope_key(state.source_scope))
    if shared:
        return scope
    if task is None:
        scope.task_id = task_id or (f"agent:{agent_id}" if agent_id else "")
        return scope
    scope.table_id = task.table_id
    scope.target_cells = [
        state.coverage_map.resolve_cell_reference(cell, table_id=task.table_id) or cell
        for cell in task.target_cells
    ]
    if not scope.target_cells:
        scope.task_id = task.id
    return scope


def record_failure(
    workspace: Any, memory: FailureMemory, *, shared: bool = False
) -> FailureMemory | None:
    """原子记录搜索经验；记忆写入失败不覆盖原执行异常。"""
    from searchos.config.settings import settings

    if workspace is None or not settings.enable_failure_memory:
        return None
    stored = None

    def update(state):
        nonlocal stored
        item = memory.model_copy(deep=True)
        task = assigned_task(state, item.task_id, item.agent_id)
        if task is not None:
            item.task_id = item.task_id or task.id
        if item.scope == FailureScope():
            item.scope = scope_for_task(state, item.task_id, item.agent_id, shared=shared)
        elif not item.scope.source_scope_key:
            item.scope.source_scope_key = source_scope_key(state.source_scope)
        stored = state.failure_memory.record(item)
        return state

    try:
        workspace.atomic_update_state(update)
    except Exception:
        logger.warning("Failed to persist search failure memory", exc_info=True)
        return None
    return stored
