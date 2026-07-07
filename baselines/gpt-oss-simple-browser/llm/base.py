"""Abstract LLM interface for the search agent."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class TokenUsage:
    """Token usage stats from a single LLM call."""

    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def __iadd__(self, other: TokenUsage) -> TokenUsage:
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        return self

    def to_dict(self) -> dict:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
        }


@dataclass
class ToolCall:
    """A tool/function call from the LLM."""

    id: str
    name: str
    arguments: dict


@dataclass
class LLMResponse:
    """Unified response from any LLM provider."""

    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    thinking: str = ""  # Chain-of-thought / reasoning
    usage: TokenUsage = field(default_factory=TokenUsage)

    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0


class BaseLLM(ABC):
    """Abstract base for LLM providers with function/tool calling support."""

    @abstractmethod
    async def chat_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        system_prompt: str = "",
    ) -> LLMResponse:
        """Send messages with tool definitions and get a response.

        Args:
            messages: Conversation history in provider-native format.
            tools: Tool definitions in provider-native format.
            system_prompt: System-level instructions.

        Returns:
            LLMResponse with content and/or tool calls.
        """
        ...
