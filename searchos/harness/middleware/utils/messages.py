"""读取原生 middleware 请求和响应。"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from langchain_core.messages import HumanMessage, ToolMessage

from searchos.util.tool_output_budget import bounded_text


def extract_tool_name(request: Any, default: str = "unknown") -> str:
    """Tool name from a middleware ToolCallRequest (or duck-typed variants).

    ToolCallRequest carries ``tool_call`` as a dict with "name"/"args"/"id".
    ``default`` is returned when no name can be resolved.
    """
    if hasattr(request, "tool_call"):
        tool_call = request.tool_call
        if isinstance(tool_call, dict):
            return tool_call.get("name", default)
    if hasattr(request, "name"):
        return request.name
    if isinstance(request, dict):
        return request.get("name", default)
    return default


def unwrap_ai_message(response: Any) -> Any:
    """Unwrap langchain's ModelResponse down to the AIMessage.

    ``response`` can be:
    - ModelResponse (deepagents/langchain): has ``.result: list[BaseMessage]``
    - AIMessage directly
    - anything else — returned as-is
    """
    if hasattr(response, "result") and isinstance(response.result, list) and response.result:
        for msg in response.result:
            if hasattr(msg, "type") and msg.type == "ai":
                return msg
            if hasattr(msg, "content") and hasattr(msg, "tool_calls"):
                return msg
        return response.result[0]
    return response


def blocked_result(request: Any, text: str) -> ToolMessage:
    return ToolMessage(
        content=text,
        tool_call_id=request.tool_call.get("id", ""),
        additional_kwargs={"sf_blocked": True},
    )


def is_blocked(result: Any) -> bool:
    return bool((getattr(result, "additional_kwargs", {}) or {}).get("sf_blocked"))


def append_feedback(result: Any, text: str) -> Any:
    if isinstance(result, str):
        return result + "\n\n" + text
    if hasattr(result, "model_copy"):
        content = result.content
        content = (
            [*content, {"type": "text", "text": text}]
            if isinstance(content, list)
            else str(content) + "\n\n" + text
        )
        budget = (getattr(result, "additional_kwargs", {}) or {}).get("sf_output_token_budget")
        if isinstance(content, str) and isinstance(budget, int):
            content = bounded_text(content, budget)
        return result.model_copy(update={"content": content})
    if hasattr(result, "content"):
        from copy import copy

        result = copy(result)
        result.content = str(result.content) + "\n\n" + text
    return result


def inject_context(request: Any, content: str, kind: str) -> Any:
    """替换同类旧提示，不修改图中保存的原始消息。"""
    messages = [
        message
        for message in request.messages
        if (getattr(message, "additional_kwargs", {}) or {}).get("sf_kind") != kind
    ]
    messages.append(
        HumanMessage(
            content=content,
            additional_kwargs={"sf_synthetic": True, "sf_kind": kind},
        )
    )
    return replace(request, messages=messages)
