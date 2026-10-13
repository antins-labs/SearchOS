"""Per-run token usage tracking via a langchain callback + ContextVar.

``start_tracking()`` at run() start sets a per-task accumulator; the callback
(registered on every model in config.models) routes each response's token
counts to it, so concurrent runs never mix totals.
"""

from __future__ import annotations

import logging
from contextvars import ContextVar
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

logger = logging.getLogger(__name__)


# Agent-loop roles. cache_hit_rate is computed over these only —
# middleware/auxiliary calls (extraction, judge, ...) are
# one-shot prompts with unique content, so counting them just dilutes the
# metric. Their numbers stay available in the per-role breakdown.
MAIN_LOOP_ROLES = frozenset({"orchestrator", "sub_agent", "synthesis"})

_ROLE_KEYS = ("prompt_tokens", "completion_tokens", "cached_prompt_tokens",
              "llm_calls", "cache_hit_calls")


class TokenUsage:
    """Mutable accumulator for a single search session's token consumption."""

    __slots__ = (
        "prompt_tokens", "completion_tokens", "total_tokens",
        "cached_prompt_tokens", "llm_calls", "cache_hit_calls",
        "by_role",
    )

    def __init__(self) -> None:
        self.prompt_tokens: int = 0
        self.completion_tokens: int = 0
        self.total_tokens: int = 0
        self.cached_prompt_tokens: int = 0
        self.llm_calls: int = 0
        self.cache_hit_calls: int = 0
        self.by_role: dict[str, dict[str, int]] = {}

    def add(self, prompt: int, completion: int, total: int,
            cached: int = 0, role: str = "unknown") -> None:
        self.prompt_tokens += prompt
        self.completion_tokens += completion
        self.total_tokens += total
        self.cached_prompt_tokens += cached
        self.llm_calls += 1
        if cached:
            self.cache_hit_calls += 1
        bucket = self.by_role.setdefault(role, dict.fromkeys(_ROLE_KEYS, 0))
        bucket["prompt_tokens"] += prompt
        bucket["completion_tokens"] += completion
        bucket["cached_prompt_tokens"] += cached
        bucket["llm_calls"] += 1
        if cached:
            bucket["cache_hit_calls"] += 1

    def to_dict(self) -> dict[str, int]:
        # int counters only: _PhaseTracker diffs these dicts key-by-key.
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "cached_prompt_tokens": self.cached_prompt_tokens,
            "llm_calls": self.llm_calls,
            "cache_hit_calls": self.cache_hit_calls,
        }

    @property
    def cache_hit_rate(self) -> float:
        """Token-level hit rate over MAIN_LOOP_ROLES only.

        Falls back to the global ratio when no per-role data exists (e.g.
        models built before role tagging, or ad-hoc scripts).
        """
        prompt = cached = 0
        for role, b in self.by_role.items():
            if role in MAIN_LOOP_ROLES:
                prompt += b["prompt_tokens"]
                cached += b["cached_prompt_tokens"]
        if not prompt:
            if not self.prompt_tokens:
                return 0.0
            return self.cached_prompt_tokens / self.prompt_tokens
        return cached / prompt

    def __repr__(self) -> str:
        return (
            f"TokenUsage(prompt={self.prompt_tokens}, "
            f"completion={self.completion_tokens}, "
            f"total={self.total_tokens}, cached={self.cached_prompt_tokens}, "
            f"calls={self.llm_calls})"
        )


_current_usage: ContextVar[TokenUsage | None] = ContextVar(
    "sf_token_usage", default=None,
)


def start_tracking() -> TokenUsage:
    """Begin a fresh token-tracking session in the current asyncio task."""
    usage = TokenUsage()
    _current_usage.set(usage)
    return usage


def get_usage() -> TokenUsage | None:
    """Return the active session's accumulated usage, or None if not tracking."""
    return _current_usage.get()


def _extract_cached_tokens(token_usage: dict) -> int:
    """Cached prompt tokens, across provider dialects.

    OpenAI/Qwen: prompt_tokens_details.cached_tokens (dict or pydantic obj);
    DeepSeek: top-level prompt_cache_hit_tokens;
    Anthropic-compatible proxies: cache_read_input_tokens.
    """
    details = token_usage.get("prompt_tokens_details") or {}
    if not isinstance(details, dict):
        details = getattr(details, "__dict__", None) or {}
    cached = (details.get("cached_tokens")
              or (token_usage.get("input_token_details") or {}).get("cache_read")
              or token_usage.get("prompt_cache_hit_tokens")
              or token_usage.get("cache_read_input_tokens")
              or 0)
    try:
        return int(cached)
    except (TypeError, ValueError):
        return 0


def extract_token_usage(response: LLMResult) -> tuple[int, int, int, int]:
    """Pull ``(prompt, completion, total, cached)`` from an LLMResult.

    token_usage may sit in llm_output or generation_info; field names differ
    by provider (prompt/completion vs input/output). None coerces to 0.
    """
    def parse(data: dict) -> tuple[int, int, int, int]:
        prompt = int(data.get("prompt_tokens") or data.get("input_tokens") or 0)
        completion = int(data.get("completion_tokens") or data.get("output_tokens") or 0)
        cached = _extract_cached_tokens(data)
        return prompt, completion, int(data.get("total_tokens") or prompt + completion), cached

    # Provider aggregates and message metadata describe the same calls: choose
    # one representation, never add both. Streaming commonly has no llm_output.
    output = response.llm_output or {}
    aggregate = output.get("token_usage") or output.get("usage")
    if aggregate:
        return parse(aggregate)
    totals = [0, 0, 0, 0]
    for generations in response.generations or []:
        for generation in generations:
            message = getattr(generation, "message", None)
            info = getattr(generation, "generation_info", None) or {}
            metadata = getattr(message, "response_metadata", None) or {}
            data = (getattr(message, "usage_metadata", None)
                    or info.get("token_usage") or info.get("usage")
                    or metadata.get("token_usage") or metadata.get("usage"))
            if data:
                totals = [a + b for a, b in zip(totals, parse(data))]
                # Alternative generations share one input and usage record.
                break
    return tuple(totals)


class TokenTrackingCallback(BaseCallbackHandler):
    """Routes each response's token usage to the task-local TokenUsage.

    One instance per role (see ``get_model_for``) so usage lands in the
    right per-role bucket.
    """

    def __init__(self, role: str = "unknown") -> None:
        self.role = role

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        usage = _current_usage.get()
        if usage is None:
            return
        prompt, completion, total, cached = extract_token_usage(response)
        if total or prompt or completion:
            usage.add(prompt=prompt, completion=completion, total=total,
                      cached=cached, role=self.role)
