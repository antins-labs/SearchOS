"""检查任务重试是否重复已排除的查询和来源路线。"""

from collections.abc import Callable
from typing import Any

from langchain.agents.middleware.types import AgentMiddleware

from searchos.harness.middleware.sensor.utils.outcomes import tool_outcome
from searchos.harness.middleware.utils.messages import blocked_result, extract_tool_name, is_blocked
from searchos.socm.planning.retry_routes import check_and_record_route, record_route_outcome, route_signature


class RetryRouteMiddleware(AgentMiddleware):
    name = "RetryRouteMiddleware"

    def __init__(self, workspace: Any, *, agent_id: str) -> None:
        self.workspace = workspace
        self.agent_id = agent_id

    async def awrap_tool_call(self, request: Any, handler: Callable) -> Any:
        error = check_and_record_route(
            self.workspace,
            self.agent_id,
            extract_tool_name(request),
            request.tool_call.get("args", {}),
        )
        if error:
            return blocked_result(request, error)
        name = extract_tool_name(request)
        args = request.tool_call.get("args", {})
        if name not in {
            "exec",
            "search",
            "open",
            "read_visual",
            "find",
            "explore_web",
            "local_catalog",
            "local_open",
            "local_find",
        } and not name.startswith("skill_"):
            return await handler(request)
        signature = route_signature(name, args)
        result = await handler(request)
        if is_blocked(result):
            return result
        artifact = getattr(result, "artifact", None) or {}
        execution = artifact.get("execution", {}) if isinstance(artifact, dict) else {}
        if name == "exec" and (execution.get("started") is False or execution.get("replayed")):
            return result
        outcome = tool_outcome(name, result, args)
        artifact = getattr(result, "artifact", None) or {}
        detail = artifact.get("outcome", artifact) if isinstance(artifact, dict) else {}
        # Generic failures may be transient; only an explicit non-retryable result blocks.
        label = "success"
        if outcome.failed:
            label = "permanent_error" if detail.get("retryable") is False else "transient_error"
        elif outcome.empty:
            label = "empty"
        record_route_outcome(self.workspace, self.agent_id, signature, label)
        return result
