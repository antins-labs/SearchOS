"""模型 profile 原语 — ``ModelProfile``、角色清单与内置默认值。

``profiles`` = 命名的模型端点；``roles`` = 角色→profile 绑定；组合规则与
env 覆写语义见 ``searchos/config/settings.py``（这些名字也从那里 re-export，
既有 ``from searchos.config.settings import ModelProfile`` 不受影响）。
"""

from __future__ import annotations

import os
from typing import Any, Literal

from pydantic import Field

from searchos.util.base_model import CamelModel


class ModelProfile(CamelModel):
    """One named model endpoint. Reusable across roles."""

    model: str
    provider: Literal["openai_compatible", "openai", "anthropic"] = "openai_compatible"
    api_base: str = ""
    api_key_env: str = "OPENAI_API_KEY"
    # Local deployments (Ollama/vLLM) require a placeholder key even when the
    # server does no auth; used when the env var above is unset/empty.
    api_key_fallback: str = ""
    temperature: float | None = 0.7  # None omits the param (some gateways reject it)
    max_tokens: int = 4096
    enable_thinking: bool = False
    # How the thinking switch is spelled on the wire (openai-compatible only):
    #   chat_template_kwargs → extra_body.chat_template_kwargs.enable_thinking
    #                          (vLLM / SiliconFlow)
    #   enable_thinking      → extra_body.enable_thinking (DashScope)
    #   none                 → never sent (OpenAI/Gemini/OpenRouter reject
    #                          unknown params, so nothing is injected)
    thinking_style: Literal["chat_template_kwargs", "enable_thinking", "none"] = (
        "chat_template_kwargs"
    )
    rpm: int = 0  # requests/min over a sliding 60s window; 0 disables
    tpm: int = 0  # tokens/min, post-paid from actual usage; 0 disables
    extra: dict[str, Any] = Field(default_factory=dict)  # forwarded to SDK verbatim


# rpm/tpm limiters are shared process-wide per (api_base, model, api_key_env).


ROLE_NAMES = (
    "orchestrator",   # main agent ReAct loop
    "sub_agent",      # search / explore sub-agent loops
    "synthesis",      # writer agent + final answer
    "skill_evolver",  # access-skill generation triage (host_miner judge)
    "post_mortem",    # FailureMemory distillation
    "judge",          # sensor / layered-context judging
    "extraction",     # evidence extraction middleware
    "alias_resolver", # orphan-evidence row/column bind
    "skill_runtime",  # T2/T3 access-skill executors
    "reformat",       # eval: reformat raw answer into benchmark shape
    "skill_router",   # pre-filter the access-skill catalog down to query-relevant top-k
)


def builtin_profiles() -> dict[str, ModelProfile]:
    """Fallback profiles when no ``SF_PROVIDER`` preset is chosen.

    Gateway endpoints are not baked in: set ``SF_BUILTIN_OPENAI_BASE`` /
    ``SF_BUILTIN_ANTHROPIC_BASE`` in the environment (or pick an
    ``SF_PROVIDER`` preset, which bypasses these profiles entirely).
    """
    openai_base = os.environ.get("SF_BUILTIN_OPENAI_BASE", "")
    anthropic_base = os.environ.get("SF_BUILTIN_ANTHROPIC_BASE", "")
    return {
        "glm5-strong": ModelProfile(
            model="GLM-5", api_base=openai_base,
            api_key_env="OPENAI_API_KEY", temperature=0.7, max_tokens=16384, rpm=90,
        ),
        "glm5-thinking": ModelProfile(
            model="GLM-5", api_base=openai_base,
            api_key_env="OPENAI_API_KEY", temperature=1.0, max_tokens=65536,
            enable_thinking=True, rpm=90,
        ),
        "glm5-judge": ModelProfile(
            model="GLM-5", api_base=openai_base,
            api_key_env="OPENAI_API_KEY", temperature=0.0, max_tokens=16384, rpm=90,
        ),
        # reformat emits the FULL answer table verbatim — a 600+ row join
        # blows past 16k output tokens and gets hard-truncated mid-row.
        # Give it a large output ceiling; deterministic temp.
        "glm5-reformat": ModelProfile(
            model="GLM-5", api_base=openai_base,
            api_key_env="OPENAI_API_KEY", temperature=0.0, max_tokens=65536, rpm=90,
        ),
        "qwen3.5-35b": ModelProfile(
            model="Qwen3.5-35B-A3B", api_base=openai_base,
            api_key_env="SF_EXTRACTION_API_KEY", temperature=0.0, max_tokens=32768, rpm=90,
        ),
        "qwen3.5-synthesis": ModelProfile(
            model="Qwen3.5-35B-A3B", api_base=openai_base,
            api_key_env="SF_EXTRACTION_API_KEY", temperature=0.3, max_tokens=32768, rpm=90,
        ),
        # Native Anthropic protocol. Distinct SF_OPUS_API_KEY so opus doesn't
        # share the GLM quota. temperature=None: some gateways 400 if any
        # temperature is passed.
        "claude-opus-4-7": ModelProfile(
            model="claude-opus-4-7", provider="anthropic",
            api_base=anthropic_base,
            api_key_env="SF_OPUS_API_KEY", temperature=None, max_tokens=32768,
        ),
    }


def builtin_roles() -> dict[str, str]:
    return {
        "orchestrator":   "glm5-strong",
        "sub_agent":      "glm5-strong",
        "synthesis":      "qwen3.5-synthesis",
        "skill_evolver":  "glm5-strong",
        "post_mortem":    "glm5-strong",
        "judge":          "glm5-judge",
        "extraction":     "qwen3.5-35b",
        "alias_resolver": "qwen3.5-35b",
        "skill_runtime":  "qwen3.5-35b",
        "reformat":       "glm5-reformat",
        "skill_router":   "glm5-strong",
    }


__all__ = ["ModelProfile", "ROLE_NAMES", "builtin_profiles", "builtin_roles"]
