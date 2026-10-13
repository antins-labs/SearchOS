"""压缩旧工具窗口，保留最近读取的完整结果。"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import replace
from typing import Any

from langchain.agents.middleware.types import AgentMiddleware
from langchain_core.messages import ToolMessage


class ToolHistoryMiddleware(AgentMiddleware):
    name = "ToolHistoryMiddleware"

    def __init__(self, *, keep_recent: int = 3, min_chars: int = 200) -> None:
        if keep_recent < 0 or min_chars < 0:
            raise ValueError("History limits must be non-negative")
        self.keep_recent = keep_recent
        self.min_chars = min_chars

    async def awrap_model_call(self, request: Any, handler: Callable) -> Any:
        indices = [i for i, msg in enumerate(request.messages) if isinstance(msg, ToolMessage)]
        older = indices[: -self.keep_recent] if self.keep_recent else indices
        if not older:
            return await handler(request)
        messages = list(request.messages)
        for index in older:
            msg = messages[index]
            if not isinstance(msg.content, str) or len(msg.content) < self.min_chars:
                continue
            title = next(
                (
                    line.strip()[:80]
                    for line in msg.content.splitlines()
                    if len(line.strip()) > 10 and not line.strip().startswith("---")
                ),
                "",
            )
            match = re.search(r"URL:\s*(https?://\S+)", msg.content)
            source = f" ({match.group(1)[:80]})" if match else ""
            messages[index] = msg.model_copy(
                update={
                    "content": f"[previous tool result] {title}{source} — full output omitted",
                }
            )
        return await handler(replace(request, messages=messages))
