"""阅读活动记录与独立的无进展停止机制。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from langchain.agents.middleware.types import AgentMiddleware

from searchos.harness.middleware.extraction import ExtractionCoordinator
from searchos.harness.middleware.models import TaskContext
from searchos.harness.middleware.sensor.core.models import ControlState, mark_agent_status
from searchos.harness.middleware.sensor.utils.outcomes import tool_outcome
from searchos.harness.middleware.sensor.utils.progress import task_progress
from searchos.harness.middleware.utils.messages import (
    append_feedback,
    extract_tool_name,
    is_blocked,
)
from searchos.harness.middleware.utils.tools import tool_costs


class ReadingProgressMiddleware(AgentMiddleware):
    name = "ReadingProgressMiddleware"

    def __init__(self, sources: set[str]) -> None:
        self.sources = sources

    async def awrap_tool_call(self, request: Any, handler: Callable) -> Any:
        result = await handler(request)
        if not is_blocked(result):
            self.observe(extract_tool_name(request), result, request.tool_call.get("args", {}))
        return result

    def observe(self, name: str, result: Any, args: Any = None) -> None:
        outcome = tool_outcome(name, result, args)
        if outcome.reading_key:
            self.sources.add(outcome.reading_key)


class ProgressGuardMiddleware(AgentMiddleware):
    name = "ProgressGuardMiddleware"

    def __init__(
        self,
        coordinator: ExtractionCoordinator,
        control: ControlState,
        *,
        limit: int,
        task: TaskContext = TaskContext(),
        on_stop: Callable[[], None] | None = None,
    ) -> None:
        self.coordinator = coordinator
        self.workspace = getattr(coordinator, "workspace", None)
        self.control = control
        self.limit = limit
        self.task = task
        self.on_stop = on_stop

    async def awrap_model_call(self, request: Any, handler: Callable) -> Any:
        count = self.coordinator.progress.consecutive_empty_batches
        if self.limit > 0 and count >= self.limit and not self.control.stopped:
            self.control.stop(f"no_progress_batches_x{count}")
            mark_agent_status(self.workspace, self.task, "no_progress")
            if self.on_stop is not None:
                self.on_stop()
        return await handler(request)


class ToolProgressMiddleware(AgentMiddleware):
    name = "ToolProgressMiddleware"

    def __init__(
        self,
        control: ControlState,
        *,
        limit: int,
        workspace: Any = None,
        task: TaskContext = TaskContext(),
        on_stop: Callable[[], None] | None = None,
    ) -> None:
        self.control = control
        self.limit = limit
        self.workspace = workspace
        self.task = task
        self.on_stop = on_stop
        self.empty_calls = 0
        self._recovery_used = False

    async def awrap_tool_call(self, request: Any, handler: Callable) -> Any:
        before = task_progress(self.workspace, self.task)
        result = await handler(request)
        if is_blocked(result):
            return result
        after = task_progress(self.workspace, self.task)
        if before is None or after is None:
            return result
        from types import SimpleNamespace

        delta = SimpleNamespace(coverage_gain=0, new_evidence_count=len(after - before))
        return self.observe(
            extract_tool_name(request), delta, result, request.tool_call.get("args", {})
        )

    def observe(self, name: str, delta: Any, result: Any, args: Any = None) -> Any:
        if self.control.stopped or self.limit <= 0 or not tool_costs(name, args):
            return result
        if delta.coverage_gain > 0 or delta.new_evidence_count > 0:
            self.empty_calls = 0
            return result
        self.empty_calls += 1
        if self.empty_calls < self.limit:
            return result
        text = getattr(result, "content", result)
        if (
            not self._recovery_used
            and name == "search"
            and isinstance(text, str)
            and "URL: search://results" in text
            and "https://" in text
        ):
            self._recovery_used = True
            self.empty_calls = 0
            return append_feedback(
                result,
                (
                    "[Harness] Search has located sources but no verified facts. "
                    "Stop issuing search queries; "
                    "use open on relevant original pages now. One bounded reading recovery remains."
                ),
            )
        self.control.stop(f"no_progress_tools_x{self.empty_calls}")
        mark_agent_status(self.workspace, self.task, "no_progress")
        if self.on_stop is not None:
            self.on_stop()
        return append_feedback(
            result,
            (
                f"[Harness] No-progress stop armed after {self.empty_calls} consecutive tools. "
                "Do not call another retrieval tool; write findings and unresolved gaps."
            ),
        )
