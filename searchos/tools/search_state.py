"""为 SOCM 工具提供当前工作区、Agent、任务与表的上下文绑定。"""

from __future__ import annotations

from contextvars import ContextVar
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from searchos.socm.workspace import WorkspaceManager

# ContextVar 隔离并发会话；新建 asyncio Task 时继承当前绑定。
_workspace_var: ContextVar["WorkspaceManager | None"] = ContextVar(
    "sf_workspace", default=None,
)
_current_agent_var: ContextVar[str] = ContextVar("sf_current_agent", default="main")
# 调度时绑定子任务，供 Evidence Extraction 限定 Judge 的抽取范围。
_current_task_var: ContextVar[str] = ContextVar("sf_current_task", default="")
_current_task_id_var: ContextVar[str] = ContextVar("sf_current_task_id", default="")
_current_table_var: ContextVar[str] = ContextVar("sf_current_table", default="")
_source_scope_var: ContextVar[dict | None] = ContextVar("sf_source_scope", default=None)


def set_workspace(ws: "WorkspaceManager") -> None:
    _workspace_var.set(ws)


def set_current_agent(name: str) -> None:
    _current_agent_var.set(name or "main")


def set_current_task(task: str) -> None:
    _current_task_var.set(task or "")


def set_current_table(table_id: str) -> None:
    _current_table_var.set(table_id or "")


def _ws() -> "WorkspaceManager":
    ws = _workspace_var.get()
    if ws is None:
        raise RuntimeError("Workspace not bound. Call set_workspace() first.")
    return ws


def get_workspace() -> "WorkspaceManager | None":
    return _workspace_var.get()
