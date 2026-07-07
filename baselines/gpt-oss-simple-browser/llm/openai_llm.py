"""OpenAI LLM implementation."""

from __future__ import annotations

import json
import logging

from openai import AsyncOpenAI

from .base import BaseLLM, LLMResponse, TokenUsage, ToolCall

logger = logging.getLogger(__name__)


class OpenAILLM(BaseLLM):
    """OpenAI chat completions with function calling."""

    def __init__(
        self,
        model: str = "gpt-4o",
        api_key: str | None = None,
        enable_thinking: bool = False,
        thinking_budget: int = 1024,
    ):
        import os
        self.model = model
        base_url = os.environ.get("OPENAI_API_BASE")
        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self.enable_thinking = enable_thinking
        self.thinking_budget = thinking_budget

    async def chat_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        system_prompt: str = "",
    ) -> LLMResponse:
        # Build messages list with system prompt
        full_messages = []
        if system_prompt:
            full_messages.append({"role": "system", "content": system_prompt})
        full_messages.extend(messages)

        kwargs = {
            "model": self.model,
            "messages": full_messages,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        if self.enable_thinking:
            kwargs["extra_body"] = {"enable_thinking": True}
        else:
            kwargs["extra_body"] = {"enable_thinking": False}
            
        response = await self.client.chat.completions.create(**kwargs)
        choice = response.choices[0]
        message = choice.message

        # Extract content
        content = message.content or ""

        # Extract thinking/reasoning (OpenAI-compatible models)
        thinking = getattr(message, "reasoning_content", None) or ""

        # Extract tool calls
        tool_calls = []
        if message.tool_calls:
            for tc in message.tool_calls:
                try:
                    args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    args = {"raw": tc.function.arguments}
                tool_calls.append(
                    ToolCall(
                        id=tc.id,
                        name=tc.function.name,
                        arguments=args,
                    )
                )

        # Extract token usage
        usage = TokenUsage()
        if response.usage:
            usage = TokenUsage(
                input_tokens=response.usage.prompt_tokens or 0,
                output_tokens=response.usage.completion_tokens or 0,
            )

        return LLMResponse(content=content, tool_calls=tool_calls, thinking=thinking, usage=usage)
