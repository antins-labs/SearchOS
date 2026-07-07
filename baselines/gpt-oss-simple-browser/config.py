"""Configuration for the search agent."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class AgentConfig:
    """Agent configuration, configurable via constructor or environment variables."""

    llm_provider: str = "openai"
    llm_model: str | None = "Kimi-K2-Instruct"
    search_page_size: int = 10
    max_iterations: int = 20
    enable_thinking: bool = False
    thinking_budget: int = 1024
    view_tokens: int = 1024
    line_wrap_width: int = 100
    verbose: bool = False

    @property
    def model_name(self) -> str:
        if self.llm_model:
            return self.llm_model
        if self.llm_provider == "claude":
            return "claude-sonnet-4-20250514"
        return "GLM-5"

    @property
    def api_key(self) -> str:
        if self.llm_provider == "claude":
            key = os.environ.get("ANTHROPIC_API_KEY", "")
        else:
            key = os.environ.get("OPENAI_API_KEY", "")
        if not key:
            raise ValueError(
                f"API key not set. Please set "
                f"{'ANTHROPIC_API_KEY' if self.llm_provider == 'claude' else 'OPENAI_API_KEY'} "
                f"environment variable."
            )
        return key
