"""上下文消息估算、任务锚点与安全裁剪。"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import BaseMessage
from langchain_core.utils.function_calling import convert_to_openai_tool


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


def trim_with_task_anchor(
    messages: list[BaseMessage],
    max_tokens: int,
) -> list[BaseMessage]:
    """保留用户指令和最新注入，以完整工具事务为单位裁剪旧历史。"""
    latest = {}
    pinned = set()
    for index, message in enumerate(messages):
        metadata = message.additional_kwargs
        kind = metadata.get("sf_kind")
        if kind:
            latest[kind] = index
        elif message.type == "system" or (
            message.type == "human" and not metadata.get("sf_synthetic")
        ):
            pinned.add(index)
    pinned.update(latest.values())

    # A transaction is indivisible even for parallel calls or intervening messages.
    groups = []
    current = []
    pending = set()
    for index, message in enumerate(messages):
        current.append(index)
        for call in getattr(message, "tool_calls", None) or ():
            pending.add(call["id"])
        if message.type == "tool":
            if message.tool_call_id not in pending:
                raise ValueError("DynamicTrim cannot trim an orphan ToolMessage")
            pending.remove(message.tool_call_id)
        if not pending:
            groups.append(current)
            current = []
    if pending:
        raise ValueError("DynamicTrim cannot trim unfinished tool calls")

    selected = set()
    for group in groups:
        if pinned.intersection(group):
            selected.update(group)
    if estimate_tokens([messages[i] for i in sorted(selected)]) > max_tokens:
        raise ValueError("Required context exceeds the DynamicTrim token budget")
    for group in reversed(groups):
        if selected.intersection(group):
            continue
        candidate = selected.union(group)
        if estimate_tokens([messages[i] for i in sorted(candidate)]) > max_tokens:
            break
        selected = candidate
    return [messages[i] for i in sorted(selected)]


def task_anchor_index(messages: list[BaseMessage]) -> int | None:
    for index, message in enumerate(messages):
        if message.type != "human":
            continue
        metadata = getattr(message, "additional_kwargs", {}) or {}
        if metadata.get("sf_synthetic") or metadata.get("sf_kind") == "socm_update":
            continue
        return index
    return None


def has_orphan_tool_message(messages: list[BaseMessage]) -> bool:
    known_call_ids: set[str] = set()
    for message in messages:
        if message.type == "ai":
            for call in getattr(message, "tool_calls", None) or []:
                call_id = call.get("id") if isinstance(call, dict) else None
                if call_id:
                    known_call_ids.add(str(call_id))
        elif message.type == "tool":
            call_id = getattr(message, "tool_call_id", None)
            if call_id and str(call_id) not in known_call_ids:
                return True
    return False
