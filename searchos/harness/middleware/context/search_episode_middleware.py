"""在搜索轮次边界裁剪上下文并记录进展。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Any

from langchain.agents.middleware.types import AgentMiddleware

from searchos.harness.middleware.context.core.search_episodes import (
    SearchEpisodeHistory,
    tool_calls,
)
from searchos.harness.middleware.utils.messages import unwrap_ai_message


class SearchEpisodeMiddleware(AgentMiddleware):
    name = "SearchEpisodeMiddleware"

    def __init__(
        self, workspace: Any, *, evidence_source: Any = None, history_max_tokens: int = 8_000
    ) -> None:
        self._history = SearchEpisodeHistory(workspace, evidence_source, history_max_tokens)
        self._evidence_source = evidence_source

    async def awrap_model_call(self, request: Any, handler: Callable) -> Any:
        messages = list(request.messages)
        folded, starts = self._history.fold_messages(messages)
        model_request = request if folded is messages else replace(request, messages=folded)
        response = await handler(model_request)
        message = unwrap_ai_message(response)
        if any(call.name == "search" for call in tool_calls(message)):
            source = self._evidence_source
            if starts and source is not None and hasattr(source, "await_idle"):
                await source.await_idle(timeout=5.0)
            self._history.record_message(message, messages, starts)
        return response
