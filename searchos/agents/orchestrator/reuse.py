"""检索 Agent 的续派条件与可复用状态目录。"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def source_scope_key(scope: Any) -> str:
    def encode(value):
        if isinstance(value, (set, frozenset)):
            return sorted(value)
        raise TypeError(f"Unsupported source scope value: {type(value).__name__}")

    return hashlib.sha256(json.dumps(scope, sort_keys=True, default=encode).encode()).hexdigest()


def access_key() -> str:
    from dataclasses import asdict

    from searchos.tools.search_state import _source_scope_var
    from searchos.tools.simple_browser.state import get_source_controls
    from searchos.tools.skills.catalog import _skill_access_policy_var

    return source_scope_key({
        "sources": asdict(get_source_controls()),
        "skills": _skill_access_policy_var.get(),
        "scope": _source_scope_var.get(),
    })


def reuse_error(agent_id: str, agent_type: str, state: Any, *, check_busy=True) -> str:
    from searchos.agents.runtime import _ctx

    info = _ctx.agent_graphs.get(agent_id)
    if info is None:
        return f"unknown agent_id: {agent_id}"
    if agent_type not in {"search_agent", "local_search_agent"}:
        return "agent_id only supports search_agent and local_search_agent"
    if info.get("agent_type") != agent_type:
        return f"agent_id {agent_id} has a different agent type"
    if not info.get("reusable"):
        return f"agent_id {agent_id} does not support task reassignment"
    if (info.get("source_scope_key") != source_scope_key(state.source_scope)
            or info.get("access_key") != access_key()):
        return f"agent_id {agent_id} has an incompatible source scope or access policy"
    task = _ctx.task_pool.get(agent_id)
    if check_busy and task is not None and not task.done():
        return f"agent_id {agent_id} is busy"
    snapshot = info["graph"].get_state({"configurable": {"thread_id": info["thread_id"]}})
    if snapshot.next:
        return f"agent_id {agent_id} has an unfinished execution checkpoint"
    return ""


def reusable_agents() -> list[dict[str, Any]]:
    from searchos.agents.runtime import _ctx
    from searchos.tools.skills.execution import loaded_package_names

    state = _ctx.workspace.load_state()
    result = []
    for agent_id, info in _ctx.agent_graphs.items():
        if reuse_error(agent_id, info.get("agent_type", ""), state):
            continue
        result.append({
            "agent_id": agent_id,
            "agent_type": info["agent_type"],
            "task_id": info.get("assigned_task_id", ""),
            "task": info.get("task", ""),
            "loaded_skills": loaded_package_names(
                _ctx.workspace.path, info.get("assigned_task_id") or agent_id,
            ),
        })
    return result
