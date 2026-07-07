"""Claude (Anthropic) LLM implementation."""

from __future__ import annotations

import json
import logging

from anthropic import AsyncAnthropic

from .base import BaseLLM, LLMResponse, TokenUsage, ToolCall

logger = logging.getLogger(__name__)


class ClaudeLLM(BaseLLM):
    """Anthropic Claude with tool_use."""

    def __init__(
        self,
        model: str = "claude-sonnet-4-20250514",
        api_key: str | None = None,
        enable_thinking: bool = False,
        thinking_budget: int = 10000,
    ):
        self.model = model
        self.client = AsyncAnthropic(api_key=api_key)
        self.enable_thinking = enable_thinking
        self.thinking_budget = thinking_budget

    async def chat_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        system_prompt: str = "",
    ) -> LLMResponse:
        kwargs = {
            "model": self.model,
            "messages": messages,
            "max_tokens": 4096,
        }
        if system_prompt:
            kwargs["system"] = system_prompt
        if tools:
            kwargs["tools"] = tools

        response = await self.client.messages.create(**kwargs)

        # Extract content and tool calls from Claude's response blocks
        content_parts = []
        tool_calls = []
        thinking = ""

        for block in response.content:
            if block.type == "text":
                content_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(
                    ToolCall(
                        id=block.id,
                        name=block.name,
                        arguments=block.input if isinstance(block.input, dict) else {},
                    )
                )
            elif block.type == "thinking":
                thinking = block.thinking

        return LLMResponse(
            content="\n".join(content_parts),
            tool_calls=tool_calls,
            thinking=thinking,
        )
