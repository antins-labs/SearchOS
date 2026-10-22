"""只把明确影响后续搜索选择的工具观察写入 SOCM。"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from langchain.agents.middleware.types import AgentMiddleware

from searchos.harness.middleware.models import TaskContext
from searchos.harness.middleware.utils.messages import extract_tool_name, is_blocked
from searchos.socm.failure_memory.extraction import extract_tool_failures
from searchos.socm.failure_memory.memory import assigned_task, record_failure, scope_for_task

logger = logging.getLogger(__name__)


class FailureRecordingMiddleware(AgentMiddleware):
    name = "FailureRecordingMiddleware"

    def __init__(self, workspace: Any, *, task: TaskContext = TaskContext()) -> None:
        self.workspace = workspace
        self.task = task

    async def awrap_tool_call(self, request: Any, handler: Callable) -> Any:
        from searchos.config.settings import settings

        if self.workspace is None or not settings.enable_failure_memory:
            return await handler(request)
        tool = extract_tool_name(request)
        if tool not in {
            "search",
            "local_catalog",
            "explore_web",
            "open",
            "read_visual",
            "exec",
        } and not tool.startswith("skill_"):
            return await handler(request)
        # 派发身份在执行前固定，避免并发收尾后归属到下一次 attempt。
        task_id, attempt = self.task.task_id, 0
        context = None
        try:
            state = self.workspace.load_state()
            task = assigned_task(state, task_id, self.task.agent_id)
            if task is not None:
                task_id, attempt = task.id, task.attempts
            context = {
                "task_id": task_id,
                "attempt": attempt,
                "agent_id": self.task.agent_id,
                "scope": scope_for_task(state, task_id, self.task.agent_id),
            }
        except Exception:
            logger.debug("Cannot resolve failure observation task", exc_info=True)
        result = await handler(request)
        if context is None or is_blocked(result):
            return result
        call = getattr(request, "tool_call", {})
        if not isinstance(call, dict):
            return result
        call_id = call.get("id", "")
        if not call_id:
            return result
        identity = f"{task_id or 'agent:' + self.task.agent_id}:{attempt}:{call_id}"
        try:
            records = extract_tool_failures(
                tool,
                call.get("args", {}),
                result,
                observation_id=identity,
                **context,
            )
            for memory in records:
                record_failure(self.workspace, memory)
        except Exception:
            # 记录异常不修改工具的原结果；实际执行异常由 handler 原样传播。
            logger.warning("Cannot collect search failure observation", exc_info=True)
        return result
