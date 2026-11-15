"""上下文消息估算、任务锚点与安全裁剪。"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import BaseMessage
from langchain_core.utils.function_calling import convert_to_openai_tool

# 模型未声明输入窗口时，上下文裁剪与工具输出共用此回退值。
DEFAULT_CONTEXT_TOKENS = 100_000


def model_input_limit(model: Any) -> int | None:
    profile = getattr(model, "profile", None)
    if isinstance(profile, dict):
        val = profile.get("max_input_tokens")
        if isinstance(val, int) and val > 0:
            return val
    return None


def estimate_tokens(messages: list[BaseMessage]) -> int:
    """粗估文本与图像内容块，不把 Base64 字符数当作图像 token。"""
    text_chars = 0
    image_tokens = 0
    for message in messages:
        calls = getattr(message, "tool_calls", None)
        if calls:
            text_chars += len(json.dumps(calls, ensure_ascii=False, default=str))
        content = message.content
        if isinstance(content, str):
            text_chars += len(content)
            continue
        if not isinstance(content, list):
            text_chars += len(str(content))
            continue
        for block in content:
            if isinstance(block, str):
                text_chars += len(block)
            elif isinstance(block, dict) and block.get("type") in {"image", "image_url"}:
                # Provider image-token formulas vary. Use a stable bounded
                # estimate; actual usage remains recorded by callbacks.
                image_tokens += 1_000
            elif isinstance(block, dict):
                text_chars += len(str(block.get("text") or block.get("content") or ""))
            else:
                text_chars += len(str(block))
    return int(text_chars / 2.5) + image_tokens + 8 * len(messages)


def request_overhead_tokens(request: Any) -> int:
    """计入消息列表之外的系统提示与工具定义；仍是跨厂商近似值。"""
    system = getattr(request, "system_message", None)
    tokens = estimate_tokens([system]) if system is not None else 0
    tools = getattr(request, "tools", None) or ()
    if tools:
        schemas = [convert_to_openai_tool(tool) for tool in tools]
        tokens += int(len(json.dumps(schemas, ensure_ascii=False, default=str)) / 2.5) + 8
    return tokens


