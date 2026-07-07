"""Shared low-level helpers for harness middleware.

HarnessMiddleware and ExtractionMiddleware each carried near-identical
copies of these; extracted here so there is a single implementation.
"""

from __future__ import annotations

from typing import Any


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
