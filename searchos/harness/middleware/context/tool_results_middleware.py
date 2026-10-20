"""模型可见工具结果的长度限制。"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from copy import copy
from typing import Any

from langchain.agents.middleware.types import AgentMiddleware
from langchain_core.utils.function_calling import convert_to_openai_tool

from searchos.config.settings import settings
from searchos.harness.middleware.context.utils.messages import model_input_limit
from searchos.harness.middleware.utils.messages import extract_tool_name
from searchos.util.tool_output_budget import (
    DEFAULT_CONTEXT_TOKENS,
    bounded_text,
    text_token_bound,
    tool_output_budget,
)


def _message_bound(message: Any) -> int:
    content = getattr(message, "content", "")
    text = (content if isinstance(content, str)
            else json.dumps(content, ensure_ascii=False, default=str))
    calls = getattr(message, "tool_calls", None)
    if calls:
        text += json.dumps(calls, ensure_ascii=False, default=str)
    return text_token_bound(text) + 8


class ToolResultLimitMiddleware(AgentMiddleware):
    name = "ToolResultLimitMiddleware"

    def __init__(self, limits: Mapping[str, int]) -> None:
        self.limits = dict(limits)
        if any(limit < 1 for limit in self.limits.values()):
            raise ValueError("Tool result limits must be positive")
        self._available_tokens = DEFAULT_CONTEXT_TOKENS

    async def awrap_model_call(self, request: Any, handler: Callable) -> Any:
        # 默认装配在 DynamicTrim 之后，扣除提示、工具定义、历史和输出额度。
        model = getattr(request, "model", None)
        window = model_input_limit(model) or DEFAULT_CONTEXT_TOKENS
        output = getattr(model, "max_tokens", None) or getattr(model, "max_output_tokens", 0)
        output = output if isinstance(output, int) and output > 0 else 0
        available = min(int(window * settings.dynamic_trim_fraction), window - output)
        available -= sum(_message_bound(message) for message in request.messages)
        system = getattr(request, "system_message", None)
        if system is not None:
            available -= _message_bound(system)
        schemas = [convert_to_openai_tool(tool) for tool in (getattr(request, "tools", None) or ())]
        available -= text_token_bound(json.dumps(schemas, ensure_ascii=False, default=str))
        self._available_tokens = max(0, available)
        return await handler(request)

    async def awrap_tool_call(self, request: Any, handler: Callable) -> Any:
        if extract_tool_name(request) == "explore_web":
            messages = (getattr(request, "state", None) or {}).get("messages", [])
            last = messages[-1] if messages else None
            calls = getattr(last, "tool_calls", None) or ()
            available = max(0, self._available_tokens - (_message_bound(last) if last else 0))
            token = tool_output_budget.set(available // max(1, len(calls)))
            try:
                # 工具在生成窗口时限制整次返回；不能事后只截 content、保留更长 artifact。
                result = await handler(request)
                content = getattr(result, "content", result)
                limit = tool_output_budget.get()
                if hasattr(result, "additional_kwargs"):
                    result = result.model_copy(update={"additional_kwargs": {
                        **result.additional_kwargs, "sf_output_token_budget": limit,
                    }})
                if isinstance(content, str) and text_token_bound(content) > limit:
                    # 抽取 middleware 可追加反馈；页面正文已在工具内部满足同一预算。
                    content = bounded_text(content, limit)
                    if isinstance(result, str):
                        return content
                    return result.model_copy(update={"content": content})
                return result
            finally:
                tool_output_budget.reset(token)
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
