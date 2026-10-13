"""每次模型请求注入当前 SOCM 投影，不依赖临时消息被持久化。"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import date
from typing import Any, Literal

from langchain.agents.middleware.types import AgentMiddleware

from searchos.harness.middleware.context.utils.projection import TaskProjection
from searchos.harness.middleware.models import TaskContext
from searchos.harness.middleware.sensor.core.models import ControlState
from searchos.harness.middleware.utils.messages import inject_context
from searchos.socm.views.render import render_compact_summary, render_orchestrator_view
from searchos.socm.views.snapshot import SearchStateSnapshot


class SOCMContextMiddleware(AgentMiddleware):
    name = "SOCMContextMiddleware"

    def __init__(
        self,
        workspace: Any,
        *,
        task: TaskContext,
        view: Literal["task", "overview", "writing"] = "task",
        control: ControlState | None = None,
        guidance: str | None = None,
        heartbeat_turns: int = 0,
        agent_graphs: Mapping[str, Any] | None = None,
    ) -> None:
        if view not in {"task", "overview", "writing"}:
            raise ValueError(f"Unknown SOCM view: {view}")
        self.workspace = workspace
        self.task = task
        self.view = view
        self.control = control
        self.guidance = (
            guidance
            if guidance is not None
            else {
                "task": (
                    "Continue your assigned task; adjust searches to its remaining targets "
                    "and avoid unrelated work."
                ),
                "overview": (
                    "Adjust dispatch using current gaps and in-flight tasks; "
                    "avoid duplicate assignments."
                ),
                "writing": "Ground writing in current evidence and report unresolved limitations.",
            }[view]
        )
        # Compatibility parameter: snapshots must remain visible on every request.
        self.heartbeat_turns = heartbeat_turns
        self._projection = TaskProjection(
            task.agent_id,
            task_text=task.task_text,
            target_table=task.target_table,
            agent_graphs=agent_graphs,
        )
        self._last_text = ""

    def bind_control(self, controls: tuple[ControlState, ...]) -> None:
        if self.control is not None or not controls:
            return
        if len(controls) != 1:
            raise ValueError("SOCMContextMiddleware requires explicit control when multiple exist")
        self.control = controls[0]

    def render(self) -> str:
        if self.workspace is None:
            return ""
        state = self.workspace.load_state()
        if self.view == "task":
            text = self._projection(state)
        else:
            snapshot = SearchStateSnapshot.from_state(state)
            text = (
                render_orchestrator_view(snapshot)
                if self.view == "overview"
                else render_compact_summary(snapshot)
            )
        # 每轮读取运行环境日期；无表时也注入，覆盖首次任务派发。
        temporal = (
            "[Runtime time]\n"
            f"Current date (runtime local date): {date.today().isoformat()}\n"
            "Resolve relative dates against this date unless the user explicitly specifies "
            "another reference date. Dates in source data or generated task briefs do not "
            "change the current date."
        )
        return "\n\n".join(block for block in (temporal, text) if block)

    async def awrap_model_call(self, request: Any, handler: Callable) -> Any:
        text = self.render()
        if self.control is not None:
            self.control.context_snapshot = text
        stopped = self.control is not None and self.control.stopped
        guidance = (
            "Search is stopped. Use these records only to summarize partial findings and "
            "unresolved limitations; do not call tools or resume searching."
            if stopped
            else self.guidance
        )
        content = f"[AUTOMATED HARNESS — state snapshot]\n{guidance}\n\n{text}" if text else ""
        if content:
            request = inject_context(request, content, "socm_update")
            self._last_text = content
        return await handler(request)
