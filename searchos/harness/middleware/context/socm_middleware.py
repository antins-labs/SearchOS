"""按角色投影更新单份 SOCM 消息，并随模型结果持久化到 checkpoint。"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import replace
from datetime import date
from typing import Any, Literal

from langchain.agents.middleware.types import AgentMiddleware, ModelResponse
from langchain_core.messages import HumanMessage, RemoveMessage

from searchos.harness.middleware.context.utils.projection import TaskProjection
from searchos.harness.middleware.models import TaskContext
from searchos.harness.middleware.sensor.core.models import ControlState
from searchos.socm.failure_memory.projection import render_failure_memory
from searchos.socm.planning.research_plan import render_research_plan
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
        agent_graphs: Mapping[str, Any] | None = None,
    ) -> None:
        if view not in {"task", "overview", "writing"}:
            raise ValueError(f"Unknown SOCM view: {view}")
        self.workspace = workspace
        self.task = task
        self.view = view
        self.control = control
        self._projection = TaskProjection(
            task.agent_id,
            task_id=task.task_id,
            task_text=task.task_text,
            target_table=task.target_table,
            agent_graphs=agent_graphs,
        )

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
            # 路由预置计划本身不代表研究已开始；计划随实际研究状态展示。
            if text:
                text = "\n\n".join(block for block in (render_research_plan(state), text) if block)
        failure_memory = render_failure_memory(
            state,
            task_id=self.task.task_id,
            agent_id=self.task.agent_id,
            target_table=self.task.target_table,
            view=self.view,
        )
        text = "\n\n".join(block for block in (text, failure_memory) if block)
        if not text:
            return ""
        return f"Current date (runtime local date): {date.today().isoformat()}\n\n{text}"

    async def awrap_model_call(self, request: Any, handler: Callable) -> ModelResponse:
        # 此处位于抽取 drain 之后，读取本次调用前已提交的最新研究状态。
        text = self.render()
        if self.control is not None:
            self.control.context_snapshot = text
        content = f"[AUTOMATED HARNESS — state snapshot]\n{text}" if text else ""
        previous = next(
            (m for m in request.messages if m.additional_kwargs.get("sf_kind") == "socm_update"),
            None,
        )
        messages = [
            m for m in request.messages if m.additional_kwargs.get("sf_kind") != "socm_update"
        ]
        updates = []
        if content:
            changed = previous is None or previous.content != content
            snapshot = (
                HumanMessage(
                    content=content,
                    id="socm-current",
                    additional_kwargs={"sf_synthetic": True, "sf_kind": "socm_update"},
                )
                if changed
                else previous
            )
            if changed:
                updates.append(snapshot)
            # 更新标记只用于当前请求的遥测；checkpoint 保留纯状态消息。
            messages.append(
                snapshot.model_copy(
                    update={
                        "additional_kwargs": {
                            **snapshot.additional_kwargs,
                            "sf_context_changed": changed,
                        }
                    }
                )
            )
        elif previous is not None:
            updates.append(RemoveMessage(id=previous.id))
        response = await handler(replace(request, messages=messages))
        # 相同 ID 由 messages reducer 原位替换；失败或取消不会提交本次投影。
        return replace(response, result=[*updates, *response.result]) if updates else response
