"""按任务、来源权限和角色投影搜索失败记忆。"""

from __future__ import annotations

import json
import time
from typing import Any, Literal

from searchos.socm.failure_memory.memory import scope_for_task, source_scope_key
from searchos.socm.failure_memory.models import FailureKind, FailureMemory, FailureScope


def _cells(state: Any, scope: FailureScope) -> set[str]:
    keys = set()
    for raw in scope.target_cells:
        resolved = state.coverage_map.resolve_cell_reference(raw, table_id=scope.table_id)
        if resolved:
            keys.add(resolved)
        elif scope.table_id and not raw.startswith(f"{scope.table_id}/"):
            # 未建立的目标仍保留表边界，不把同名短引用跨表匹配。
            keys.add(f"{scope.table_id}/{raw}")
        else:
            keys.add(raw)
    return keys


def _tables(state: Any, scope: FailureScope) -> set[str]:
    tables = {scope.table_id} if scope.table_id else set()
    tables.update(key.split("/", 1)[0] for key in _cells(state, scope) if "/" in key)
    return tables


def _matches(state: Any, memory: FailureMemory, current: FailureScope) -> bool:
    scope = memory.scope
    if scope.task_id and scope.task_id != current.task_id:
        return False
    if scope.table_id and scope.table_id not in _tables(state, current):
        return False
    if scope.target_cells and not (_cells(state, scope) & _cells(state, current)):
        return False
    if scope.entities:
        entities = set(current.entities)
        for key in _cells(state, current):
            binding = state.coverage_map.cell_binding(key)
            if binding is not None:
                entities.add(binding[1])
        if not (set(scope.entities) & entities):
            return False
    if scope.task_id or scope.table_id or scope.target_cells or scope.entities:
        return True
    # 只有显式共享的来源和技能限制可以跨任务投影。
    return memory.kind in {FailureKind.SOURCE, FailureKind.SKILL}


def _task_scopes(state: Any, task_id: str, agent_id: str, target_table: str) -> list[FailureScope]:
    tasks = state.frontier.questions
    if task_id:
        task = next((task for task in tasks if task.id == task_id), None)
        if task is not None and agent_id and task.assigned_agent_id != agent_id:
            return []
        scopes = [scope_for_task(state, task_id, agent_id)]
    elif agent_id:
        scopes = [
            scope_for_task(state, task.id, agent_id)
            for task in tasks
            if task.assigned_agent_id == agent_id and task.status == "running"
        ] or [scope_for_task(state, agent_id=agent_id)]
    else:
        scopes = []
    for scope in scopes:
        scope.table_id = scope.table_id or target_table
    return scopes


def _scope_label(scope: FailureScope) -> str:
    if scope.target_cells:
        label = "cells=" + json.dumps(scope.target_cells[:5], ensure_ascii=False)
        return label + (f" (+{len(scope.target_cells) - 5})" if len(scope.target_cells) > 5 else "")
    if scope.entities:
        label = "entities=" + json.dumps(scope.entities[:5], ensure_ascii=False)
        return label + (f" (+{len(scope.entities) - 5})" if len(scope.entities) > 5 else "")
    if scope.task_id:
        return "task=" + json.dumps(scope.task_id, ensure_ascii=False)
    if scope.table_id:
        return "table=" + json.dumps(scope.table_id, ensure_ascii=False)
    return "shared under current source permissions"


def _writing_source_operation(operation: str) -> str:
    """写作保留访问方法与窗口条件，不携带复盘的查询和阅读轨迹。"""
    try:
        calls = json.loads(operation)
    except (TypeError, ValueError):
        return ""
    if not isinstance(calls, list):
        return ""
    if len(calls) == 2 and isinstance(calls[0], str) and isinstance(calls[1], dict):
        calls = [{"tool": calls[0], "arguments": calls[1]}]
    methods = []
    for call in calls:
        if not isinstance(call, dict):
            continue
        tool, args = call.get("tool"), call.get("arguments", {})
        if tool not in {"open", "find", "read_visual", "local_open", "local_find"}:
            continue
        if not isinstance(args, dict):
            continue
        conditions = {
            key: args[key]
            for key in ("loc", "view_tokens", "page", "view", "max_chars", "representation_id")
            if key in args
        }
        methods.append([tool, conditions])
    return json.dumps(methods, ensure_ascii=False) if methods else ""


def render_failure_memory(
    state: Any,
    *,
    task_id: str = "",
    agent_id: str = "",
    target_table: str = "",
    view: Literal["task", "overview", "writing"] = "task",
) -> str:
    """查询和路径按明确任务目标匹配；写作视图只保留交付限制。"""
    from searchos.config.settings import settings

    if not settings.enable_failure_memory or settings.failure_memory_max_inject <= 0:
        return ""
    store = getattr(state, "failure_memory", None)
    if store is None:
        return ""
    now = time.time()
    permission_key = source_scope_key(state.source_scope)
    scopes = _task_scopes(state, task_id, agent_id, target_table) if view == "task" else []
    records = []
    for memory in store.records:
        if memory.superseded or memory.scope.source_scope_key != permission_key:
            continue
        if now - (memory.last_seen or memory.created_at) >= settings.failure_memory_decay_seconds:
            continue
        if view == "task" and not any(_matches(state, memory, scope) for scope in scopes):
            # 没有分派信息时也可读取明确共享的来源和技能限制。
            if scopes or not _matches(state, memory, FailureScope()):
                continue
        if view == "writing":
            if memory.kind == FailureKind.QUERY:
                continue
            tables = _tables(state, memory.scope)
            if target_table and tables and target_table not in tables:
                continue
        records.append(memory)
    records.sort(key=lambda memory: memory.last_seen or memory.created_at, reverse=True)
    if not records:
        return ""
    lines = ["Search failure memory (scope and conditions apply):"]
    for memory in records[:settings.failure_memory_max_inject]:
        scope = _scope_label(memory.scope)
        target = json.dumps(memory.target[:200], ensure_ascii=False)
        operation = memory.operation
        if view == "writing":
            operation = (
                _writing_source_operation(operation) if memory.kind == FailureKind.SOURCE else ""
            )
        detail = f"; operation={operation[:300]}" if operation else ""
        if memory.skill_version:
            detail += f"; skill_version={memory.skill_version}"
        origin = {
            "observation": "tool observation",
            "post_mortem": "post_mortem inference",
            "historical": "historical record",
        }.get(memory.source, memory.source)
        lines.append(
            f"- [{memory.kind.value}; {origin}; confidence={memory.confidence}] "
            f"{target}: {memory.what_failed[:500]} "
            f"({scope}{detail})."
        )
        if memory.guidance and view != "writing":
            lines.append(f"  Conditional guidance: {memory.guidance[:300]}")
    return "\n".join(lines)
