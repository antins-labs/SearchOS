"""Pydantic Settings — single source of truth for SearchOS configuration.

Secrets (API keys) stay in ``.env``, referenced by ``api_key_env`` name.
Per-field env override via the ``SF_`` prefix and ``__`` delimiter:

    SF_ROLES__JUDGE=glm5-strong
    SF_PROFILES__GLM5_STRONG__TEMPERATURE=0.0

Partial overrides deep-merge onto the defaults (a lone ``SF_ROLES__JUDGE``
keeps all other role bindings). Profile keys in env vars may use ``_``
in place of ``-`` (env names can't contain hyphens).

``profiles`` = named model endpoints; ``roles`` = role→profile bindings.
Every model use site resolves through ``config.models.get_model_for(role)``.
``SF_`` prefix retained for backward compat with existing ``.env`` files.

Open-source one-knob setup: set ``SF_PROVIDER`` (see ``config.providers``)
and profiles/roles defaults are generated for that vendor.

Layout of this module (full layering story in ``docs/configuration.md``):

    ModelProfile / ROLE_NAMES / builtin defaults   → config/profiles.py (re-exported)
    provider presets (SF_PROVIDER)                 → config/providers.py
    .env read/write                                → config/env_file.py
    effort tiers                                   → config/effort.py
    Settings sections below: models → budget → scheduler → harness →
    workspace → skills → search → browser → memory → extraction → ablation

The ``settings`` singleton is an import-time snapshot of the environment;
after changing env vars at runtime call ``reload_settings_in_place()``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from searchos.config.middleware import validate_pipelines
from searchos.config.model_purposes import RETIRED_MODEL_ROLES

# Re-exported for backward compat — many call sites import these from here.
from searchos.config.profiles import (  # noqa: F401
    ROLE_NAMES,
    ModelProfile,
    builtin_profiles,
    builtin_roles,
)

__all__ = [
    "AGENT_BUDGET_OVERRIDES",
    "ModelProfile",
    "ROLE_NAMES",
    "Settings",
    "builtin_profiles",
    "builtin_roles",
    "reload_settings_in_place",
    "settings",
]


def _default_profiles() -> dict[str, Any]:
    """SF_PROVIDER preset profiles when set, else the builtin fallbacks."""
    from searchos.config.providers import provider_default_profiles

    preset = provider_default_profiles()
    return preset if preset is not None else builtin_profiles()


def _default_roles() -> dict[str, str]:
    from searchos.config.providers import provider_default_roles

    preset = provider_default_roles()
    return preset if preset is not None else builtin_roles()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SF_", env_nested_delimiter="__")

    # --- Model profiles & role bindings ---
    profiles: dict[str, ModelProfile] = Field(default_factory=_default_profiles)
    roles: dict[str, str] = Field(default_factory=_default_roles)

    @model_validator(mode="before")
    @classmethod
    def _merge_partial_model_config(cls, data: Any) -> Any:
        """Deep-merge partial ``profiles``/``roles`` overrides onto defaults.

        pydantic-settings replaces dict fields wholesale when any nested env
        var targets them (a lone ``SF_ROLES__JUDGE=x`` would drop the other
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
            data["roles"] = {
                **_default_roles(),
                **{k: v for k, v in override_roles.items() if k not in RETIRED_MODEL_ROLES},
            }

        return data

    # --- LLM client ---
    # 6 retries ≈ 24s backoff — rides out an RPM-window 429 burst.
    llm_max_retries: int = 6

    # --- Budget ---
    default_max_time_s: int = 1800  # 0 = no wall-clock limit

    # --- Orchestrator budget (main loop only) ---
    orch_max_iterations: int = 50
    orch_trim_max_tokens: int = 128_000
    orch_max_dispatches: int = 0
    # Complete search waves with no reading, facts, task bindings or coverage growth.
    # 0 disables coverage-stall early termination.
    orch_coverage_stall_rounds: int = 3
    orch_premature_end_max_resumes: int = 2
    research_finalize_timeout_s: float = 60.0
    research_finalize_max_chars: int = 48_000
    hybrid_projection_max_chars: int = 24_000
    hybrid_projection_timeout_s: float = 20.0
    hybrid_observation_max_chars: int = 12_000
    hybrid_observation_review_max_chars: int = 48_000
    hybrid_observation_timeout_s: float = 30.0

    # --- Scheduler / Frontier dispatch ---
    max_parallel_agents: int = 8
    # Search 创建总限按未取消的 Frontier Task 计数；0 表示不限。
    # Explore 可在任意阶段按需创建，仍受并发与会话总预算约束。
    max_search_agents_per_session: int = 30
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
    max_skills_per_sub_agent: int = 20
    # Search-agent early stop: consecutive settled extraction batches with
    # no committed progress. 0 disables. Keep the legacy setting name for
    # env compatibility; harnesses without Extraction fall back to tool counts.
    search_agent_no_progress_tool_limit: int = 10

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
    browser_auth_dir: str = '.searchos/browser-auth'
    # 按需目录查询使用 skill_router 做语义匹配；关闭后保留名称/关键词查找。
    enable_skill_router: bool = True
    skill_router_top_k: int = 40  # 每次查询的候选上限，工具分页返回。
    skill_promotion_threshold: float = 0.6
    skill_optimization_threshold: float = 0.8
    max_anti_patterns_per_skill: int = 8

    # --- Search API (keys read via env; see docs/configuration.md) ---
    search_max_results: int = 10
    tavily_api_key: str = ""
    serper_api_key: str = ""

    # --- Browser ---
    browser_view_tokens: int = Field(default=4096, ge=1, le=8192)
    browser_backend: str = "jina"  # aiohttp | crawl4ai | search_engine | jina
    browser_disk_cache_enabled: bool = True  # per-URL disk cache; only ok results
    # Override via SF_BROWSER_DISK_CACHE_DIR.
    browser_disk_cache_dir: str = str(
        Path.home() / ".cache" / "searchos" / "page_cache"
    )
    jina_api_key: str = ""  # empty → unauthenticated quota (429-prone)
    # Web image reading is opt-in so existing evaluations keep their text-only
    # tool surface and Jina response shape. ``auto`` for Jina means all only
    # when the capability is enabled; otherwise it resolves to alt.
    enable_web_image_read: bool = False
    web_image_read_mode: Literal["auto", "native", "vision"] = "auto"
    jina_retain_images: Literal["auto", "alt", "all"] = "auto"
    web_image_fetch_timeout_s: float = 20.0
    web_image_max_bytes: int = 10 * 1024 * 1024
    web_image_capability_ttl_s: int = 24 * 60 * 60

    def effective_jina_retain_images(self) -> Literal["alt", "all"]:
        if self.jina_retain_images != "auto":
            return self.jina_retain_images
        return "all" if self.enable_web_image_read else "alt"

    # --- Local document search ---
    enable_local_tools: bool = False
    local_index_root: str = "./local-index/default"
    # Tool results become model context. Keep disabled until the user permits
    # the configured Local Search Agent model to receive catalog/source text.
    local_allow_model_access: bool = False

    # --- Trace skill generation (runtime, opt-in) ---
    # Legacy configuration names retained for existing installations.
    # Trace intent selects create/update requests across all three categories.
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
    use_layered_context: bool = False

    # Independent batches within one local document; provider limits still apply.
    local_recap_concurrency: int = 3

    # --- Extraction ---
    extraction_flush_concurrency: int = 5
    extraction_finalize_timeout_s: float = 30.0
    extraction_dual_mode: bool = True  # split FILL/DISCOVER judge calls
    # Inputs longer than this (chars) are split into segments before extraction
    # so a single judge call never overruns the input/output window — mainly
    # for skill JSON payloads, which can be huge. Segments extract concurrently.
    extraction_chunk_char_budget: int = 40_000
    # Structured payloads also split by their longest array. This prevents a
    # compact JSON response containing thousands of records from becoming one
    # enormous FILL/DISCOVER prompt even when its character count is modest.
    extraction_chunk_max_records: int = 50
    extraction_chunk_overlap_chars: int = 200  # overlap on non-JSON char splits
    # Cross-table backfill: after extracting a flush's pages for the
    # sub-agent's target_table, re-run extraction on the SAME pages for
    # every relation-linked table. Without it, evidence for a table the
    # orchestrator never targets is silently dropped even when every page
    # contains it. Costs one extra judge pass per linked table per flush.
    extraction_cross_table_backfill: bool = True

    # --- Ablation flags ---
    # Disable only role-facing SOCM prompt projections. The underlying SOCM
    # state, extraction writes, scheduler, and explicit state tools remain
    # available so this isolates the context-projection contribution.
    enable_socm_projection: bool = True
    middleware_pipelines: dict[str, list[str]] = Field(default_factory=dict)
    _validate_middleware = field_validator("middleware_pipelines")(validate_pipelines)
    enable_explore: bool = True  # False → orchestrator skips explore_agent
    # False → create_schema skips replaying explore summaries into extraction.
    enable_explore_replay: bool = True
    # True: concurrent coverage waves; False: legacy serial search/open/find.
    enable_explore_batch: bool = True
    # 单次 Explore 的波次上限；目标解决后可随时结束，产品与评测一致。
    explore_max_waves: int = Field(default=3, ge=1)
    judge_max_input_chars: int = 128_000
    skip_synthesis: bool = False  # eval: export table directly from CoverageMap


settings = Settings()


def reload_settings_in_place(fresh: Settings | None = None) -> None:
    """Rebuild configuration from the current environment, updating the
    singleton field by field.

    NEVER rebinds ``settings`` — ~50 call sites across the repo import it by
    name and hold the same object reference. Callers that already built a
    fresh instance (dry-run validation) can pass it in to reuse.

    NOTE: web-overlay values applied onto the singleton (effort knobs, role
    bindings, …) are reset to env defaults — the web layer must re-apply its
    overlay afterwards (``settings_store.apply_to_runtime``).
    """
    fresh = fresh if fresh is not None else Settings()
    for name in Settings.model_fields:
        setattr(settings, name, getattr(fresh, name))


# Per-agent budget overrides (max_searches, max_opens, max_finds, max_skills).
AGENT_BUDGET_OVERRIDES: dict[str, dict[str, int]] = {
    # 批量调用按实际 query/page 计量；find 继承公共的单 Agent 预算。
    "explore_agent": {"max_searches": 30, "max_opens": 36},
    "search_agent": {"max_searches": 15, "max_opens": 15, "max_finds": 15},
    "local_search_agent": {
        "max_searches": 15, "max_opens": 15, "max_finds": 15,
    },
}
