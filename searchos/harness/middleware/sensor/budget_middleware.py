"""按逻辑轮次和实际工具工作量执行预算。"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import asdict, replace
from typing import Any, Literal, NotRequired
from uuid import uuid4

from langchain.agents.middleware.types import AgentMiddleware, AgentState
from langchain_core.messages import AIMessage, ToolMessage

from searchos.harness.middleware.models import TaskContext
from searchos.harness.middleware.sensor.core.models import (
    BudgetState,
    ControlState,
    mark_agent_status,
)
from searchos.harness.middleware.utils.messages import (
    append_feedback,
    blocked_result,
    extract_tool_name,
    is_blocked,
)
from searchos.harness.middleware.utils.tools import tool_costs


class _BudgetCheckpointState(AgentState):
    budget_checkpoint: NotRequired[dict[str, Any]]


class BudgetMiddleware(AgentMiddleware):
    name = "BudgetMiddleware"
    state_schema = _BudgetCheckpointState
    _fields = {"search": "queries", "open": "opens", "find": "finds", "skill": "skills"}

    def __init__(
        self,
        budget: BudgetState,
        control: ControlState,
        *,
        workspace: Any = None,
        task: TaskContext = TaskContext(),
        drain_tools: frozenset[str] = frozenset(),
        on_exhausted: Callable[[], None] | None = None,
        wrap_up: str = "Summarize findings and unresolved limitations.",
        warn_iterations: bool = False,
        scope: Literal["run", "thread"] = "run",
    ) -> None:
        if scope not in {"run", "thread"}:
            raise ValueError("Budget scope must be 'run' or 'thread'")
        self.scope = scope
        self._thread_id = None
        self._epoch = uuid4().hex
        self._accounted_tools: set[str] = set()
        self._has_run = False
        self._resuming = False
        self.workspace = workspace
        self.task = task
        self.budget = budget
        self.control = control
        self.drain_tools = drain_tools
        self.on_exhausted = on_exhausted
        self.wrap_up = wrap_up
        self.warn_iterations = warn_iterations
        self._reserved = dict.fromkeys(self._fields, 0)
        self._notified: set[str] = set()
        self._exhausted = False
        self._rejected_rounds = 0
        self._round_rejected = False
        self._round_executed = False

    _usage_fields = (
        "consumed_queries",
        "consumed_opens",
        "consumed_finds",
        "consumed_skills",
        "current_iteration",
        "evaluator_tokens",
        "_start_ts",
    )

    def _restore_control(self, snapshot):
        for key, value in snapshot.items():
            if key == "blocked_tools":
                value = set(value)
            if hasattr(self.control, key):
                setattr(self.control, key, value)

    def _stop_snapshot(self):
        return {
            "reason": self.control.reason,
            "forced": self.control.forced,
            "blocked_tools": sorted(self.control.blocked_tools),
            "stop_message": self.control.stop_message,
        }

    def _rejection_snapshot(self):
        return {
            "rejected_rounds": self._rejected_rounds,
            "round_rejected": self._round_rejected,
            "round_executed": self._round_executed,
        }

    def _restore_rejections(self, snapshot):
        self._rejected_rounds = snapshot.get("rejected_rounds", 0)
        self._round_rejected = bool(snapshot.get("round_rejected"))
        self._round_executed = bool(snapshot.get("round_executed"))

    def _checkpoint(self):
        control = asdict(self.control)
        control["blocked_tools"] = sorted(control["blocked_tools"])
        return {
            "scope": self.scope,
            "epoch": self._epoch,
            "usage": {key: getattr(self.budget, key) for key in self._usage_fields},
            "control": control,
            "accounted_tools": sorted(self._accounted_tools),
            "notified": sorted(self._notified),
            "exhausted": self._exhausted,
            "rejections": self._rejection_snapshot(),
        }

    async def abefore_agent(self, state, runtime):
        from langgraph.config import get_config

        config = get_config()
        thread_id = config.get("configurable", {}).get("thread_id")
        if self.scope == "thread" and thread_id is None:
            raise ValueError("thread budget requires a thread_id and checkpointer")
        if self._thread_id is not None and str(thread_id) != self._thread_id:
            raise ValueError("Create a separate BudgetMiddleware instance for each thread")
        self._thread_id = str(thread_id)
        saved = state.get("budget_checkpoint")
        if (
            (self.scope == "thread" or self._resuming)
            and saved
            and saved.get("scope") == self.scope
        ):
            self._epoch = saved["epoch"]
            for key, value in saved.get("usage", {}).items():
                if key in self._usage_fields:
                    setattr(self.budget, key, value)
            self._restore_control(saved.get("control", {}))
            self._accounted_tools = set(saved.get("accounted_tools", ()))
            self._notified = set(saved.get("notified", ()))
            self._exhausted = bool(saved.get("exhausted"))
            self._restore_rejections(saved.get("rejections", {}))
            # Tool receipts are checkpointed with messages. They cover a restart
            # immediately after tools, before the next before_model snapshot.
            for message in state.get("messages", ()):
                model_receipt = getattr(message, "additional_kwargs", {}).get("sf_budget_model", {})
                if model_receipt.get("epoch") == self._epoch:
                    if self.budget._start_ts is None:
                        self.budget._start_ts = model_receipt.get("started_at")
                    if model_receipt.get("iteration", 0) > self.budget.current_iteration:
                        self._restore_rejections(model_receipt.get("rejections", {}))
                    self.budget.current_iteration = max(
                        self.budget.current_iteration, model_receipt.get("iteration", 0)
                    )
                    if model_receipt.get("control", {}).get("forced"):
                        self._restore_control(model_receipt["control"])
                receipt = getattr(message, "additional_kwargs", {}).get("sf_budget_receipt", {})
                call_id = getattr(message, "tool_call_id", "")
                if receipt.get("epoch") != self._epoch or call_id in self._accounted_tools:
                    continue
                for dimension, cost in receipt.get("costs", {}).items():
                    field = "consumed_" + self._fields[dimension]
                    setattr(self.budget, field, getattr(self.budget, field) + cost)
                self._accounted_tools.add(call_id)
                self._round_rejected |= bool(receipt.get("rejected"))
                self._round_executed |= any(receipt.get("costs", {}).values())
                if receipt.get("control", {}).get("forced"):
                    self._restore_control(receipt["control"])
        elif self._has_run or saved:
            for key in self._usage_fields:
                setattr(self.budget, key, None if key == "_start_ts" else 0)
            self._restore_control(asdict(ControlState()))
            self._epoch = uuid4().hex
            self._accounted_tools.clear()
            self._notified.clear()
            self._exhausted = False
            self._restore_rejections({})
        self._reserved = dict.fromkeys(self._fields, 0)
        self._has_run = True
        return {"budget_checkpoint": self._checkpoint()}

    async def abefore_model(self, state, runtime):
        if not self._has_run and state.get("budget_checkpoint"):
            self._resuming = True
            try:
                await self.abefore_agent(state, runtime)
            finally:
                self._resuming = False
        return {"budget_checkpoint": self._checkpoint()}

    async def aafter_model(self, state, runtime):
        return await self.abefore_model(state, runtime)

    async def aafter_agent(self, state, runtime):
        return await self.abefore_model(state, runtime)

    def _settle_exhaustion(self) -> None:
        if not self.budget.fully_exhausted or self._exhausted:
            return
        self._exhausted = True
        mark_agent_status(self.workspace, self.task, "budget_exhausted")
        self.control.stop(
            "budget_exhausted",
            message=(
                f"HARD STOP — {self.budget.exhaustion_reason.upper()} LIMIT REACHED\n"
                f"Budget exhausted ({self.budget.exhaustion_detail()}). "
                f"Tools still allowed: {', '.join(sorted(self.drain_tools)) or 'none'}. "
                f"{self.wrap_up}"
            ),
        )
        if self.on_exhausted is not None:
            self.on_exhausted()

    async def awrap_model_call(self, request: Any, handler: Callable) -> Any:
        self.budget._ensure_started()
        # 在模型轮次边界结算，避免把同一批并发拒绝累计成多轮。
        # 仍有检索动作实际执行时允许恢复；读取技能说明等辅助调用不清零。
        if self._round_executed:
            self._rejected_rounds = 0
        elif self._round_rejected:
            self._rejected_rounds += 1
        self._round_rejected = self._round_executed = False
        if self._rejected_rounds >= 3 and not self.control.forced:
            mark_agent_status(self.workspace, self.task, "budget_exhausted")
            self.control.stop(
                "budget_rejection_loop",
                message=(
                    "HARD STOP — REPEATED BUDGET REJECTIONS\n"
                    "Three tool rounds were rejected without executing another retrieval action. "
                    "Do not retry exhausted tools. " + self.wrap_up
                ),
            )
        self.budget.current_iteration += 1
        if self.budget.current_iteration == 1:
            caps = [
                f"{dimension}: {getattr(self.budget, f'max_{field}')}"
                for dimension, field in self._fields.items()
                if getattr(self.budget, f"max_{field}") > 0
            ]
            if caps:
                self.control.messages.append(
                    "[Harness BUDGET] Tool action limits: " + ", ".join(caps) + ". "
                    "Batch calls consume their underlying action counts. " + self.wrap_up
                )
        self._settle_exhaustion()
        # 工具额度耗尽只隐藏该工具，不把仍可阅读或执行技能的任务全局停止。
        if hasattr(request, "tools"):
            available = []
            for item in request.tools:
                name = (
                    item.get("name") or item.get("function", {}).get("name", "")
                    if isinstance(item, dict)
                    else item.name
                )
                costs = tool_costs(name, {})
                if name in self.drain_tools or all(
                    getattr(self.budget, f"max_{self._fields[dim]}") <= 0
                    or getattr(self.budget, f"consumed_{self._fields[dim]}") + cost
                    <= getattr(self.budget, f"max_{self._fields[dim]}")
                    for dim, cost in costs.items()
                ):
                    available.append(item)
            request = replace(request, tools=available)
        if self._notified and not self.control.forced:
            remaining_actions = []
            for dimension, field in self._fields.items():
                cap = getattr(self.budget, f"max_{field}")
                if cap > 0:
                    used = getattr(self.budget, f"consumed_{field}")
                    remaining_actions.append(f"{dimension}: {max(0, cap - used)} left")
            self.control.messages.append(
                "[Harness BUDGET] Remaining actions: " + ", ".join(remaining_actions) + ". "
                "Tools with zero capacity cannot be retried. Use a feasible remaining tool "
                "or summarize supported findings and unresolved gaps."
            )
        remaining = self.budget.max_iterations - self.budget.current_iteration
        if (
            self.warn_iterations
            and self.budget.max_iterations > 0
            and not self._exhausted
            and remaining <= max(3, self.budget.max_iterations // 4)
        ):
            self.control.messages.append(
                f"[Harness] Iteration budget: round {self.budget.current_iteration}/"
                f"{self.budget.max_iterations} ({remaining} left). Begin converging."
            )
        response = await handler(request)
        receipt = {
            "epoch": self._epoch,
            "iteration": self.budget.current_iteration,
            "control": self._stop_snapshot(),
            "started_at": self.budget._start_ts,
            "rejections": self._rejection_snapshot(),
        }

        def stamp(message):
            if not isinstance(message, AIMessage):
                return message
            return message.model_copy(
                update={
                    "additional_kwargs": {**message.additional_kwargs, "sf_budget_model": receipt}
                }
            )

        if isinstance(response, AIMessage):
            return stamp(response)
        if hasattr(response, "result"):
            return replace(response, result=[stamp(message) for message in response.result])
        return response

    async def awrap_tool_call(self, request: Any, handler: Callable) -> Any:
        state = getattr(request, "state", {})
        if not self._has_run and state.get("budget_checkpoint"):
            await self.abefore_model(state, None)
        self.budget._ensure_started()
        name = extract_tool_name(request)
        costs = tool_costs(name, request.tool_call.get("args", {}))
        self._settle_exhaustion()
        if self._exhausted and name not in self.drain_tools:
            return blocked_result(
                request,
                (
                    f"[Harness] {self.budget.exhaustion_reason.title()} limit reached; "
                    "tool blocked "
                    f"({self.budget.exhaustion_detail()}). Synthesize your final answer now. "
                    f"Only drain tools remain: {', '.join(sorted(self.drain_tools)) or 'none'}."
                ),
            )
        for dimension, cost in costs.items():
            field = self._fields[dimension]
            cap = getattr(self.budget, f"max_{field}")
            used = getattr(self.budget, f"consumed_{field}") + self._reserved[dimension]
            if cap > 0 and used + cost > cap:
                result = blocked_result(
                    request,
                    (
                        f"[Harness] {dimension} budget cannot fit this call "
                        f"({used}/{cap} used or reserved, call costs {cost}) — "
                        f"'{name}' is blocked. "
                        "Use a smaller batch only if capacity remains; otherwise switch to "
                        "an available tool or summarize findings and unresolved gaps. "
                        "Repeated rejected rounds will force a final summary."
                    ),
                )
                return self._receipt(result, request, {}, rejected=True)
        # No await occurs between checking and reserving a tool batch.
        for dimension, cost in costs.items():
            self._reserved[dimension] += cost
        try:
            result = await handler(request)
        except asyncio.CancelledError:
            if name == "exec":
                from searchos.tools.skill_execution import execution_started

                call_id = request.tool_call.get("id", "")
                if call_id not in self._accounted_tools and execution_started(call_id):
                    for dimension, cost in costs.items():
                        field = "consumed_" + self._fields[dimension]
                        setattr(self.budget, field, getattr(self.budget, field) + cost)
                    self._accounted_tools.add(call_id)
                    self._round_executed = True
                    # No ToolMessage exists on cancellation. This charge is captured
                    # by the next normal checkpoint; it is not a cross-store transaction.
            raise
        finally:
            for dimension, cost in costs.items():
                self._reserved[dimension] -= cost
        if is_blocked(result):
            return result
        artifact = getattr(result, "artifact", None)
        execution = artifact.get("execution", {}) if isinstance(artifact, dict) else {}
        if (
            name == "exec"
            and isinstance(execution, dict)
            and (execution.get("started") is False or execution.get("replayed") is True)
        ):
            return result
        for dimension, cost in costs.items():
            field = self._fields[dimension]
            attribute = f"consumed_{field}"
            setattr(self.budget, attribute, getattr(self.budget, attribute) + cost)
            cap = getattr(self.budget, f"max_{field}")
            if (
                cap > 0
                and getattr(self.budget, attribute) >= cap
                and dimension not in self._notified
            ):
                self._notified.add(dimension)
                result = append_feedback(
                    result,
                    (
                        f"[Harness] {dimension} budget is now exhausted "
                        f"({getattr(self.budget, attribute)}/{cap} used). "
                        "Use remaining tools or wrap up with supported findings."
                    ),
                )
        self._settle_exhaustion()
        return self._receipt(result, request, costs)

    def _receipt(self, result, request, costs, *, rejected=False):
        self._round_rejected |= rejected
        self._round_executed |= any(costs.values())
        if isinstance(result, ToolMessage) and (costs or rejected):
            call_id = request.tool_call.get("id", "")
            self._accounted_tools.add(call_id)
            receipt = {
                "epoch": self._epoch,
                "costs": costs,
                "rejected": rejected,
                "control": self._stop_snapshot(),
                "started_at": self.budget._start_ts,
            }
            result = result.model_copy(
                update={
                    "additional_kwargs": {**result.additional_kwargs, "sf_budget_receipt": receipt}
                }
            )
        return result
