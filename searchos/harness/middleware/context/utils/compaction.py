"""压缩所需的消息计量、完整交互边界与文本表示。"""

from __future__ import annotations

import json
from collections.abc import Callable

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from searchos.harness.middleware.context.utils.messages import estimate_tokens

TokenCounter = Callable[[list[BaseMessage]], int]


def count_context_tokens(messages: list[BaseMessage]) -> int:
    """估算消息正文、工具参数和消息开销；不等价于厂商 tokenizer。"""
    return estimate_tokens(messages)


def pinned(message: BaseMessage) -> bool:
    if message.additional_kwargs.get("sf_kind") == "socm_update":
        return True
    if isinstance(message, SystemMessage):
        return True
    return isinstance(message, HumanMessage) and not message.additional_kwargs.get("sf_synthetic")


def split_history(
    messages: list[BaseMessage], keep_tokens: int, counter: TokenCounter
) -> tuple[list[BaseMessage], list[BaseMessage]]:
    """仅在完整工具事务之间切分；未完成的事务不允许压缩。"""
    boundaries = [0]
    pending: set[str] = set()
    for i, message in enumerate(messages):
        for call in getattr(message, "tool_calls", None) or []:
            pending.add(call["id"])
        if message.type == "tool":
            call_id = message.tool_call_id
            if call_id not in pending:
                raise ValueError("Cannot compact history with an orphan tool result")
            pending.remove(call_id)
        if not pending:
            boundaries.append(i + 1)
    if pending:
        raise ValueError("Cannot compact history with unfinished tool calls")
    # Oversized complete interactions are summarized, never split or silently dropped.
    cut = len(messages)
    for boundary in reversed(boundaries[:-1]):
        if counter(messages[boundary:]) > keep_tokens:
            break
        cut = boundary
    return messages[:cut], messages[cut:]


def render_history(messages: list[BaseMessage]) -> str:
    """把历史当作数据交给摘要模型，保留来源和调用标识，避免传递图片 Base64。"""
    rows = []
    for message in messages:
        content = message.content
        if isinstance(content, list):
            content = [
                block
                if isinstance(block, str)
                else (
                    block.get("text", "")
                    if block.get("type") in {"text", "input_text"}
                    else {"omitted_block_type": block.get("type", "unknown")}
                )
                for block in content
            ]
        row = {"role": message.type, "content": content}
        if message.type == "tool":
            row["tool_call_id"] = message.tool_call_id
        if getattr(message, "tool_calls", None):
            row["tool_calls"] = message.tool_calls
        rows.append(json.dumps(row, ensure_ascii=False, default=str))
    return "\n".join(rows)
