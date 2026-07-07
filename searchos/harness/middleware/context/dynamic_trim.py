"""Dynamic message trimming middleware — prevents context window overflow.

Adapted from insalphaproveprod/hellopython/src/core/agent/middleware/dynamic_trim_middleware.py

区别于 deepagents SummarizationMiddleware（LLM 摘要，修改 state）：
- DynamicTrimMiddleware 是临时性裁剪（只影响本次请求，不修改 state）
- 作为最后一道防线，放在 SummarizationMiddleware 之后
"""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import Any, Callable

from langchain.agents.middleware.types import AgentMiddleware
from langchain_core.messages import BaseMessage
from langchain_core.messages.utils import trim_messages

logger = logging.getLogger(__name__)

DEFAULT_MAX_TOKENS = 100_000
DEFAULT_FRACTION = 0.85


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
        estimated = self._estimate_tokens(request.messages)

        if estimated <= effective_max:
            return await handler(request)

        logger.warning(
            "Messages exceed limit: ~%d tokens > %d, trimming (%d messages)",
            estimated, effective_max, len(request.messages),
        )

        try:
            trimmed = trim_messages(
                request.messages,
                strategy="last",
                max_tokens=effective_max,
                start_on="human",
                end_on=["human", "tool"],
                include_system=True,
                token_counter=self._estimate_tokens,
            )
            logger.info("Trimmed: %d → %d messages", len(request.messages), len(trimmed))
            return await handler(replace(request, messages=trimmed))
        except Exception:
            logger.error("trim_messages failed, using fallback", exc_info=True)
            return await self._fallback_trim(request, handler)

    def _effective_max_tokens(self, request: Any) -> int:
        if self._max_tokens is not None:
            return self._max_tokens

        if self._max_tokens_fraction is not None:
            model = getattr(request, "model", None)
            max_input = self._get_model_max_input(model)
            if max_input:
                return int(max_input * self._max_tokens_fraction)

        return DEFAULT_MAX_TOKENS

    @staticmethod
    def _get_model_max_input(model: Any) -> int | None:
        profile = getattr(model, "profile", None)
        if isinstance(profile, dict):
            val = profile.get("max_input_tokens")
            if isinstance(val, int) and val > 0:
                return val
        return None

    @staticmethod
    def _estimate_tokens(messages: list[BaseMessage]) -> int:
        """粗估: 1 token ≈ 2.5 字符（中英混合折中）"""
        total = sum(len(str(m.content)) for m in messages)
        return int(total / 2.5)

    @staticmethod
    async def _fallback_trim(request: Any, handler: Callable) -> Any:
        """降级: 保留 system + 最近 50 条消息."""
        msgs = request.messages
        if len(msgs) <= 50:
            return await handler(request)

        system = [m for m in msgs if m.type == "system"]
        others = [m for m in msgs if m.type != "system"]
        trimmed = system + others[-50:]
        logger.warning("Fallback trim: %d → %d messages", len(msgs), len(trimmed))
        return await handler(replace(request, messages=trimmed))
