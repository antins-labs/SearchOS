"""Per-task workspace/agent/task ContextVar bindings shared by all
SOCM-aware tools.

Historical note: this module used to expose agent-level write tools
(``update_frontier``, ``add_evidence``, ``mark_coverage``,
``log_strategy``, ``batch_record``, ``add_entity``). Per plan §5.7
权限矩阵, Evidence/Coverage/Frontier writes belong to the Extraction
middleware and dedicated orchestrator tools — never to a
general-purpose agent tool. Those tools were removed along with
``analyst_agent`` in the slim pass.

What remains is the ContextVar plumbing: every tool that needs the
current WorkspaceManager or the current agent/task label imports from
here.
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from searchos.socm.workspace import WorkspaceManager

# Per-asyncio-task context. Replaces module-level globals so concurrent
# `harness.run()` calls in the same process (benchmark batches, API
# handlers, tests) don't overwrite each other's bindings. `ContextVar`
# values are forked on `asyncio.create_task`, giving each logical run
# its own isolated view.
_workspace_var: ContextVar["WorkspaceManager | None"] = ContextVar(
    "sf_workspace", default=None,
)
_current_agent_var: ContextVar[str] = ContextVar("sf_current_agent", default="main")
# Task string of the currently-executing sub-agent, set at dispatch time.
# EvidenceExtractionMiddleware reads this so the judge prompt can be
# framed around the specific sub-task ("extract findings relevant to
# THIS task") instead of a generic global query.
_current_task_var: ContextVar[str] = ContextVar("sf_current_task", default="")
_current_table_var: ContextVar[str] = ContextVar("sf_current_table", default="")


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
