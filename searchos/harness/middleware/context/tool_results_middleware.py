"""模型可见工具结果的长度限制。"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from copy import copy
from typing import Any

from langchain.agents.middleware.types import AgentMiddleware

from searchos.harness.middleware.utils.messages import extract_tool_name


class ToolResultLimitMiddleware(AgentMiddleware):
    name = "ToolResultLimitMiddleware"

    def __init__(self, limits: Mapping[str, int]) -> None:
        self.limits = dict(limits)
        if any(limit < 1 for limit in self.limits.values()):
            raise ValueError("Tool result limits must be positive")

    async def awrap_tool_call(self, request: Any, handler: Callable) -> Any:
        result = await handler(request)
        limit = self.limits.get(extract_tool_name(request))
        text = getattr(result, "content", result)
        if limit is None or not isinstance(text, str) or len(text) <= limit:
            return result
        text = text[:limit] + f"\n\n... [truncated from {len(text)} to {limit} chars]"
        if isinstance(result, str):
            return text
        if hasattr(result, "model_copy"):
            return result.model_copy(update={"content": text})
        result = copy(result)
        result.content = text
        return result
