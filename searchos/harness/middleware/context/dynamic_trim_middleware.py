"""Dynamic message trimming middleware — prevents context window overflow.

Adapted from insalphaproveprod/hellopython/src/core/agent/middleware/dynamic_trim_middleware.py

区别于 deepagents SummarizationMiddleware（LLM 摘要，修改 state）：
- DynamicTrimMiddleware 是临时性裁剪（只影响本次请求，不修改 state）
- 作为最后一道防线，放在 SummarizationMiddleware 之后
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import replace
from typing import Any

from langchain.agents.middleware.types import AgentMiddleware

from searchos.harness.middleware.context.utils.messages import (
    estimate_tokens,
    model_input_limit,
    request_overhead_tokens,
    trim_with_task_anchor,
)
from searchos.util.tool_output_budget import DEFAULT_CONTEXT_TOKENS

logger = logging.getLogger(__name__)

DEFAULT_MAX_TOKENS = DEFAULT_CONTEXT_TOKENS


class DynamicTrimMiddleware(AgentMiddleware):
    """在每次 LLM 调用前动态裁剪消息，防止溢出.

    两种模式:
    - max_tokens: 固定 token 上限
    - max_tokens_fraction: 按模型窗口比例（如 0.85 = 85%）
    """

    name: str = "DynamicTrimMiddleware"

    def __init__(
        self,
        max_tokens: int | None = None,
        max_tokens_fraction: float | None = None,
    ) -> None:
        if max_tokens is not None and max_tokens_fraction is not None:
            raise ValueError("不能同时指定 max_tokens 和 max_tokens_fraction")

        self._max_tokens = max_tokens
        self._max_tokens_fraction = max_tokens_fraction

        if self._max_tokens is None and self._max_tokens_fraction is None:
            self._max_tokens = DEFAULT_MAX_TOKENS

    async def awrap_model_call(self, request: Any, handler: Callable) -> Any:
        effective_max = self._effective_max_tokens(request)
        overhead = request_overhead_tokens(request)
        if overhead >= effective_max:
            raise ValueError("System prompt and tool schemas exceed the DynamicTrim token budget")
        estimated = estimate_tokens(request.messages) + overhead

        if estimated <= effective_max:
            return await handler(request)

        logger.warning(
            "Messages exceed limit: ~%d tokens > %d, trimming (%d messages)",
            estimated,
            effective_max,
            len(request.messages),
        )

        trimmed = trim_with_task_anchor(request.messages, effective_max - overhead)
        logger.info("Trimmed: %d → %d messages", len(request.messages), len(trimmed))
        return await handler(replace(request, messages=trimmed))

    def _effective_max_tokens(self, request: Any) -> int:
        if self._max_tokens is not None:
            return self._max_tokens

        if self._max_tokens_fraction is not None:
            model = getattr(request, "model", None)
            max_input = model_input_limit(model)
            if max_input:
                return int(max_input * self._max_tokens_fraction)

        return DEFAULT_MAX_TOKENS
