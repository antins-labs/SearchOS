"""Codex 风格的文本上下文压缩：阈值触发、任务续接、checkpoint 持久化。"""

from __future__ import annotations

import asyncio
import math
from typing import Any, NotRequired

from langchain.agents.middleware.types import AgentMiddleware, AgentState
from langchain_core.messages import RemoveMessage, SystemMessage
from langgraph.graph.message import REMOVE_ALL_MESSAGES

from searchos.harness.middleware.context.core.history import (
    TokenCounter,
    count_context_tokens,
    pinned,
    render_history,
    split_history,
    summarize_history,
)
from searchos.harness.middleware.context.utils.token_counts import (
    model_input_limit,
    request_overhead_tokens,
)


class _ContextState(AgentState):
    context_compaction: NotRequired[dict[str, int]]


class CompactionContextMiddleware(AgentMiddleware):
    """通过普通聊天模型实现可移植的续接摘要，不模拟 OpenAI 的加密状态。

    context_window 指 agent 模型窗口，默认从 model.profile 读取。
    所有预算按窗口比例计算；独立摘要模型较小时另行约束其输入预算。
    """

    name = "CompactionContextMiddleware"
    state_schema = _ContextState

    def __init__(
        self,
        model: Any,
        *,
        context_window: int | None = None,
        trigger_fraction: float = 0.8,
        keep_recent_fraction: float = 0.08,
        summary_fraction: float = 0.02,
        reserve_fraction: float = 0.08,
        token_counter: TokenCounter = count_context_tokens,
        timeout: float = 120,
    ) -> None:
        model_window = model_input_limit(model)
        if context_window is None:
            context_window = model_window
        if (
            not isinstance(context_window, int)
            or isinstance(context_window, bool)
            or context_window <= 0
        ):
            raise ValueError("Provide context_window or a model with profile.max_input_tokens")
        fractions = (trigger_fraction, keep_recent_fraction, summary_fraction, reserve_fraction)
        if any(not math.isfinite(f) or not 0 <= f < 1 for f in fractions):
            raise ValueError("Context fractions must be finite and in [0, 1)")
        if trigger_fraction <= 0 or summary_fraction <= 0:
            raise ValueError("Trigger and summary fractions must be positive")
        if keep_recent_fraction + summary_fraction + reserve_fraction >= trigger_fraction:
            raise ValueError("Retained context and summary must leave room below the trigger")
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("Timeout must be finite and positive")
        self.model = model
        self.context_window = context_window
        self.trigger_tokens = int(context_window * trigger_fraction)
        self.keep_recent_tokens = int(context_window * keep_recent_fraction)
        self.summary_tokens = int(context_window * summary_fraction)
        self.reserve_tokens = int(context_window * reserve_fraction)
        # A smaller summary model must not inherit the agent's larger input budget.
        summary_window = min(context_window, model_window or context_window)
        self._summary_input_budget = (
            int(summary_window * (1 - reserve_fraction)) - self.summary_tokens
        )
        if self.summary_tokens < 1 or self._summary_input_budget < 1:
            raise ValueError("Window too small for the configured summary budget")
        self.token_counter = token_counter
        self.timeout = timeout

    async def abefore_model(self, state: AgentState, runtime: Any) -> dict[str, Any] | None:
        messages = list(state["messages"])
        before = self.token_counter(messages) + self.reserve_tokens
        if before < self.trigger_tokens:
            return None
        prefix, tail = split_history(messages, self.keep_recent_tokens, self.token_counter)
        anchors = [message for message in prefix if pinned(message)]
        removable = [message for message in prefix if not pinned(message)]
        if not removable:
            if before >= self.context_window:
                raise ValueError("Context exceeds budget with no completed history to compact")
            return None
        retained = self.token_counter([*anchors, *tail]) + self.reserve_tokens
        if retained + self.summary_tokens + 64 >= self.trigger_tokens:
            raise ValueError("User instructions or newest interaction exceed compaction budget")
        # No state mutation until the entire summary succeeds, including all chunks.
        async with asyncio.timeout(self.timeout):
            summary = await self._summarize(
                render_history(prefix), render_history([*anchors, *tail])
            )
        handoff = SystemMessage(
            content=f"""Conversation summary:
{summary}""",
            additional_kwargs={"sf_synthetic": True, "sf_kind": "context_compaction"},
        )
        compacted = [*anchors, handoff, *tail]
        after = self.token_counter(compacted) + self.reserve_tokens
        if after >= min(before, self.trigger_tokens):
            raise ValueError("Compaction did not create sufficient context headroom")
        previous = state.get("context_compaction", {})
        return {
            "messages": [RemoveMessage(id=REMOVE_ALL_MESSAGES), *compacted],
            "context_compaction": {
                "count": previous.get("count", 0) + 1,
                "before_tokens": before,
                "after_tokens": after,
            },
        }

    async def awrap_model_call(self, request: Any, handler: Any) -> Any:
        # Run after context injection in the explicit list. Reserve remains a
        # safety margin for output and runtime reminders, not a substitute for
        # counting the system prompt and tool definitions.
        total = self.token_counter(list(request.messages)) + request_overhead_tokens(request)
        if total + self.reserve_tokens >= self.context_window:
            raise ValueError(
                "Actual model request exceeds compaction budget; increase reserve_fraction, "
                "reduce injected context, or place a final DynamicTrimMiddleware after injection"
            )
        return await handler(request)

    async def _summarize(self, transcript: str, retained_context: str) -> str:
        """按输入预算逐块合并，避免超长工具结果让摘要请求本身溢出。"""
        return await summarize_history(self.model, transcript, retained_context,
            summary_tokens=self.summary_tokens, input_budget=self._summary_input_budget,
            token_counter=self.token_counter)
