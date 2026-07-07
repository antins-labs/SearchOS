"""Pydantic Settings — single source of truth for SearchOS configuration.

Secrets (API keys) stay in ``.env``, referenced by ``api_key_env`` name.
Per-field env override via the ``SF_`` prefix and ``__`` delimiter:

    SF_ROLES__JUDGE=glm5-strong
    SF_PROFILES__GLM5_STRONG__TEMPERATURE=0.0

Partial overrides deep-merge onto the defaults (a lone ``SF_ROLES__JUDGE``
keeps the other 11 role bindings). Profile keys in env vars may use ``_``
in place of ``-`` (env names can't contain hyphens).

``profiles`` = named model endpoints; ``roles`` = role→profile bindings.
Every model use site resolves through ``config.models.get_model_for(role)``.
``SF_`` prefix retained for backward compat with existing ``.env`` files.

Open-source one-knob setup: set ``SF_PROVIDER`` (see ``config.providers``)
and profiles/roles defaults are generated for that vendor — coding plans
(Anthropic 协议) and pay-as-you-go OpenAI-compatible APIs alike.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

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


def _builtin_profiles() -> dict[str, ModelProfile]:
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


def _builtin_roles() -> dict[str, str]:
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


def _default_profiles() -> dict[str, Any]:
    """SF_PROVIDER preset profiles when set, else the builtin fallbacks."""
    from searchos.config.providers import provider_default_profiles

    preset = provider_default_profiles()
    return preset if preset is not None else _builtin_profiles()


def _default_roles() -> dict[str, str]:
    from searchos.config.providers import provider_default_roles

    preset = provider_default_roles()
    return preset if preset is not None else _builtin_roles()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SF_", env_nested_delimiter="__")

    # --- Model profiles ---
    profiles: dict[str, ModelProfile] = Field(default_factory=_default_profiles)

    # --- Role → profile bindings ---
    roles: dict[str, str] = Field(default_factory=_default_roles)

    @model_validator(mode="before")
    @classmethod
    def _merge_partial_model_config(cls, data: Any) -> Any:
        """Deep-merge partial ``profiles``/``roles`` overrides onto defaults.

        pydantic-settings replaces dict fields wholesale when any nested env
        var targets them (a lone ``SF_ROLES__JUDGE=x`` would drop the other 11
        bindings; ``SF_PROFILES__MAIN__TEMPERATURE=0`` would fail validation).
        Merging here restores the documented partial-override semantics. Env
        var names can't contain ``-``, so ``glm5_strong`` matches profile key
        ``glm5-strong``.
        """
        if not isinstance(data, dict):
            return data

        override_profiles = data.get("profiles")
        if isinstance(override_profiles, dict):
            merged: dict[str, Any] = {
                k: (v.model_dump() if isinstance(v, ModelProfile) else dict(v))
                for k, v in _default_profiles().items()
            }
            for key, val in override_profiles.items():
                target = key if key in merged else key.replace("_", "-")
                if target in merged and isinstance(val, dict):
                    merged[target] = {**merged[target], **val}
                elif target in merged:
                    merged[target] = val  # full replacement (e.g. ModelProfile)
                else:
                    merged[key] = val  # brand-new profile
            data["profiles"] = merged

        override_roles = data.get("roles")
        if isinstance(override_roles, dict):
            data["roles"] = {**_default_roles(), **override_roles}

        return data

    # 6 retries ≈ 24s backoff — rides out an RPM-window 429 burst.
    llm_max_retries: int = 6

    # --- Budget ---
    default_max_time_s: int = 1800  # 0 = no wall-clock limit

    # --- Orchestrator budget (main loop only) ---
    orch_max_iterations: int = 50
    orch_trim_max_tokens: int = 128_000
    orch_max_dispatches: int = 0
    orch_premature_end_max_resumes: int = 2

    # --- SOCM injection throttle (sub-agents only) ---
    socm_throttle_enabled: bool = False
    socm_throttle_min_rows: int = 3
    socm_throttle_max_turns: int = 3
    # Heartbeat: re-inject the latest snapshot every N real turns even when the
    # cell signature is frozen — once all cells reach `filled` the signature
    # stops changing and the agent would otherwise churn against a stale view.
    # 0 disables (pure signature-change behavior).
    socm_heartbeat_turns: int = 12
    socm_max_row_names_per_group: int = 200  # 0 = no cap

    # --- Scheduler / Frontier dispatch ---
    max_parallel_agents: int = 8
    enable_scheduler: bool = True  # False → legacy direct-dispatch (rollback)
    spawn_stagger_s: float = 0.5   # avoids a same-instant spawn burst tripping 429
    rate_limit_recycle_cooldown_s: float = 3  # before re-dispatching a 429-recycled task
    # Pool-nudge throttle: the "[Frontier queue empty]" reminder pressures the
    # orchestrator into speculative dispatch when fired repeatedly (it fires on
    # every pool-size change), so rate-limit it.
    pool_nudge_cooldown_s: float = 90.0  # min seconds between nudges; 0 = no cooldown
    pool_nudge_max_count: int = 5        # max nudges per run; 0 = no cap

    # --- Sub-agent dispatch budget ---
    max_searches_per_sub_agent: int = 20
    max_searches_per_sub_agent_ceiling: int = 40
    max_finds_per_sub_agent: int = 20

    # --- Writer ---
    enable_writer_agent: bool = False

    # --- Harness ---
    budget_warning_ratio: float = 0.7
    # False → keep full tool-result history (append-only requests, maximizes
    # prompt-cache reuse at the cost of longer prompts).
    compress_old_tool_results: bool = True

    # --- Evaluator ---
    coverage_threshold: float = 0.8
    quality_threshold: float = 0.6
    min_source_diversity: int = 2

    # --- Workspace ---
    workspace_root: str = "./searchos_workspace"
    blackboard_dir: str = "blackboard"
    evidence_dir: str = "evidence"
    intermediate_dir: str = "intermediate"
    agent_logs_dir: str = "agent_logs"
    output_dir: str = "output"
    trajectory_file: str = "trajectory.jsonl"
    conversation_file: str = "conversation.json"

    # --- Skill ---
    enable_skills: bool = True
    skill_library_path: str = "searchos/skills/library"
    skill_max_inject: int = 2
    # Access-catalog top-k pre-filter via the ``skill_router`` LLM role; fail-open.
    enable_skill_router: bool = True
    skill_router_top_k: int = 40
    skill_promotion_threshold: float = 0.6
    skill_optimization_threshold: float = 0.8
    max_anti_patterns_per_skill: int = 8

    # --- Search API ---
    search_max_results: int = 10

    # --- Browser ---
    browser_view_tokens: int = 2048
    browser_backend: str = "jina"  # aiohttp | crawl4ai | search_engine | jina
    browser_disk_cache_enabled: bool = True  # per-URL disk cache; only ok results
    browser_disk_cache_dir: str = str(Path.home() / ".cache" / "searchos" / "page_cache")  # override via SF_BROWSER_DISK_CACHE_DIR
    jina_api_key: str = ""  # empty → unauthenticated quota (429-prone)

    # --- Access-skill generation (runtime, opt-in) ---
    # After each run, an LLM triages the trajectory and bakes skills for the
    # most-repeated hosts (skills.evolution.host_miner). Expensive per build.
    enable_access_skill_generation: bool = False
    access_skill_max_per_run: int = 2
    access_skill_min_opens: int = 3  # fallback threshold when no triage model
    access_skill_obs_chars: int = 800

    # --- Failure memory (post-mortem) ---
    enable_failure_memory: bool = True
    max_post_mortems_per_session: int = 10
    post_mortem_min_evidence: int = 10
    failure_memory_decay_seconds: int = 1800
    failure_memory_max_inject: int = 5

    # --- Context trimming ---
    dynamic_trim_fraction: float = 0.85
    layered_context_layer1_max_tokens: int = 50_000
    layered_context_layer2_max_tokens: int = 8_000
    layered_context_layer3_max_tokens: int = 2_000

    # --- Providers ---
    tavily_api_key: str = ""
    serper_api_key: str = ""

    # --- Feature flags ---
    enable_trajectory_logging: bool = True

    # --- Extraction ---
    extraction_flush_concurrency: int = 5
    extraction_finalize_timeout_s: float = 30.0
    extraction_dual_mode: bool = True  # split FILL/DISCOVER judge calls
    # Inputs longer than this (chars) are split into segments before extraction
    # so a single judge call never overruns the input/output window — mainly
    # for skill JSON payloads, which can be huge. Segments extract concurrently.
    extraction_chunk_char_budget: int = 40_000
    extraction_chunk_overlap_chars: int = 200  # overlap on non-JSON char splits
    # Cross-table backfill: after extracting a flush's pages for the
    # sub-agent's target_table, re-run extraction on the SAME pages for
    # every relation-linked table. Without it, evidence for a table the
    # orchestrator never targets is silently dropped even when every page
    # contains it. Costs one extra judge pass per linked table per flush.
    extraction_cross_table_backfill: bool = True

    # --- Ablation flags ---
    enable_explore: bool = True  # False → orchestrator skips explore_agent
    enable_explore_replay: bool = True  # False → create_schema skips replaying explore summaries into extraction
    judge_max_input_chars: int = 128_000
    skip_synthesis: bool = False  # eval: export table directly from CoverageMap


settings = Settings()


# Per-agent budget overrides (max_searches, max_opens, max_finds).
AGENT_BUDGET_OVERRIDES: dict[str, dict[str, int]] = {
    "explore_agent": {"max_searches": 8, "max_opens": 8, "max_finds": 8},
    "search_agent": {"max_searches": 15, "max_opens": 15, "max_finds": 15},
}
