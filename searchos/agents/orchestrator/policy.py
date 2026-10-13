"""运行池有空位且没有待派发任务时提醒调度。"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from typing import Any

from searchos.harness.middleware.sensor.core.models import ControlState
from searchos.harness.middleware.utils.messages import inject_context


class DispatchPolicy:
    def __init__(
        self,
        workspace: Any,
        *,
        agents: Mapping[str, Any],
        capacity: int,
        cooldown_s: float = 0,
        max_reminders: int = 0,
        control: ControlState | None = None,
    ) -> None:
        self.workspace = workspace
        self.agents = agents
        self.capacity = capacity
        self.cooldown_s = cooldown_s
        self.max_reminders = max_reminders
        self.control = control
        self._last_size = -1
        self._last_time: float | None = None
        self._count = 0

    async def call_model(self, request: Any, handler: Callable) -> Any:
        if self.control is not None and self.control.stopped:
            return await handler(request)
        agents = [agent_id for agent_id, task in self.agents.items() if not task.done()]
        size = len(agents)
        if not 0 < size < self.capacity:
            self._last_size = -1
            return await handler(request)
        if size == self._last_size or (
            self.max_reminders > 0 and self._count >= self.max_reminders
        ):
            return await handler(request)
        now = time.monotonic()
        if self._last_time is not None and now - self._last_time < self.cooldown_s:
            return await handler(request)
        state = self.workspace.load_state()
        if not state.coverage_map.tables or any(
            task.status.value == "pending" for task in state.frontier.questions
        ):
            return await handler(request)
        self._last_size, self._last_time = size, now
        self._count += 1
        content = (
            "[AUTOMATED HARNESS — Frontier queue empty]\n"
            f"Only {size} sub-agent(s) running ({', '.join(agents[:6])}); "
            f"max_parallel_agents={self.capacity} and the Frontier OPEN queue is empty. "
            "Inspect the SOCM gaps and enqueue independent follow-up work in the same turn "
            "as check_agents. Skip gaps that depend on running tasks."
        )
        request = inject_context(request, content, "pool_nudge")
        return await handler(request)
