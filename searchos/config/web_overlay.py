"""The web-settings overlay — a JSON delta on top of the env-based settings.

The env/.env layer stays the base configuration; this overlay holds only the
deltas the user sets from the web Settings page (effort level, skill toggles,
provider connections, model cards, role bindings, run defaults). Sparse
semantics throughout: ``None`` / absent means "no override, env base wins". The
file lives next to ``.env`` at the repo root (``web_settings.json``, override
with ``SF_WEB_SETTINGS_PATH``) — deliberately NOT inside the workspace root,
whose subdirectories are scanned as sessions.

This module owns the DATA MODEL and the read/apply path so it can be shared by
both entry points: the web app (which additionally writes via
``web/api/settings_store.py``) and the ``searchos`` CLI/TUI (read-only). Keeping
it under ``searchos.config`` avoids a ``searchos → web`` dependency.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator

logger = logging.getLogger(__name__)

EffortLevel = Literal["low", "medium", "high", "max"]


class EffortOverlay(BaseModel, extra="forbid"):
    level: EffortLevel | None = None
    overrides: dict[str, int] = Field(default_factory=dict)


class SkillsOverlay(BaseModel, extra="forbid"):
    access_only: list[str] | None = None   # None = router decides
    access_deny: list[str] = Field(default_factory=list)
    strategy_deny: list[str] = Field(default_factory=list)
    orchestrator_deny: list[str] = Field(default_factory=list)
    # Reactive generation runs after a search and installs generated access
    # skills for later runs. None keeps the env/code default.
    enable_access_skill_generation: bool | None = None
    access_skill_max_per_run: int | None = Field(default=None, ge=1, le=10)


class ProviderConnection(BaseModel, extra="forbid"):
    """A user-defined provider connection referenced by model cards.

    Holds only the wire connection (protocol / endpoint / which env vars carry
    the keys) plus how the thinking switch is spelled. The API key VALUES live in
    .env under the names in ``api_key_envs`` — never here. One connection may
    carry SEVERAL keys (different quota / team / project); the first is the
    default and a model card may select another via its own ``api_key_env``.
    Model cards point at one of these by name via ``provider_ref`` and inherit
    all of these fields, so a card only has to carry a model id and sampling.
    """
    protocol: Literal["openai_compatible", "openai", "anthropic"] = "openai_compatible"
    api_base: str = ""
    api_key_envs: list[str] = Field(default_factory=lambda: ["OPENAI_API_KEY"])
    thinking_style: Literal["chat_template_kwargs", "enable_thinking", "none"] = "none"
    label: str = ""  # optional human label (e.g. the preset it was seeded from)

    @model_validator(mode="before")
    @classmethod
    def _migrate_singular_key(cls, data):
        # Back-compat: an earlier overlay stored a single ``api_key_env`` string.
        if isinstance(data, dict) and "api_key_env" in data and "api_key_envs" not in data:
            data = dict(data)
            env = data.pop("api_key_env")
            data["api_key_envs"] = [env] if env else []
        return data

    @property
    def primary_key_env(self) -> str:
        return self.api_key_envs[0] if self.api_key_envs else "OPENAI_API_KEY"

    def resolve_key_env(self, chosen: str | None) -> str:
        """Which key a card uses: its explicit pick if it's one of ours, else
        our default (first) key."""
        return chosen if chosen and chosen in self.api_key_envs else self.primary_key_env


class ProfileOverride(BaseModel, extra="forbid"):
    """Sparse per-field deltas on a base (env-defined) profile. None = keep base.

    ``provider_ref`` re-points the profile at a user-defined provider connection
    (its protocol/base/key_env/thinking_style win); temperature/enable_thinking
    let a base card tune sampling without becoming a full custom profile.
    """
    model: str | None = None
    api_base: str | None = None
    api_key_env: str | None = None
    provider_ref: str | None = None
    temperature: float | None = None
    enable_thinking: bool | None = None
    rpm: int | None = Field(default=None, ge=0)
    tpm: int | None = Field(default=None, ge=0)


class CustomProfile(BaseModel, extra="forbid"):
    """A user-created model card. Points at a provider connection via
    ``provider_ref`` (inheriting protocol/base/key_env/thinking_style); the inline
    provider/api_base/api_key_env are only a fallback for legacy cards with no
    ref."""
    model: str
    provider_ref: str | None = None
    provider: Literal["openai_compatible", "openai", "anthropic"] = "openai_compatible"
    api_base: str = ""
    api_key_env: str = "OPENAI_API_KEY"
    # Sampling knobs. temperature None → omit the param (gateways that reject it).
    temperature: float | None = None
    max_tokens: int = 16384
    enable_thinking: bool = False
    thinking_style: Literal["chat_template_kwargs", "enable_thinking", "none"] = "none"
    rpm: int = Field(default=0, ge=0)
    tpm: int = Field(default=0, ge=0)


class ModelsOverlay(BaseModel, extra="forbid"):
    roles: dict[str, str] = Field(default_factory=dict)  # sparse role→profile deltas
    provider_connections: dict[str, ProviderConnection] = Field(default_factory=dict)
    profile_overrides: dict[str, ProfileOverride] = Field(default_factory=dict)
    custom_profiles: dict[str, CustomProfile] = Field(default_factory=dict)
    search_provider: str | None = None
    browser_backend: str | None = None


class RunDefaults(BaseModel, extra="forbid"):
    max_time_s: int | None = None
    search_max_results: int | None = None
    enable_skills: bool | None = None
    enable_explore_batch: bool | None = None


class AdvancedOverlay(BaseModel, extra="forbid"):
    """First-class runtime knobs that ``effort`` does not cover. Sparse: None =
    no override, env/code default wins.

    ``https_proxy`` is not a ``settings`` field — the HTTP libraries read it from
    ``os.environ``, so ``apply_to_runtime`` exports it there (and to ``HTTP_PROXY``).
    ``browser_disk_cache_dir`` / ``llm_max_retries`` map straight onto ``settings``.
    Concurrency / iteration / wall-clock time stay in ``effort`` (see
    ``config.effort.EFFORT_KEYS``) — duplicating them here would re-create the
    two-homes problem this overlay exists to remove.
    """
    llm_max_retries: int | None = None
    orch_coverage_stall_rounds: int | None = None
    browser_disk_cache_dir: str | None = None
    https_proxy: str | None = None  # applied to both HTTP_PROXY and HTTPS_PROXY
    use_layered_context: bool | None = None


class WebSettings(BaseModel, extra="forbid"):
    version: int = 1
    effort: EffortOverlay = Field(default_factory=EffortOverlay)
    skills: SkillsOverlay = Field(default_factory=SkillsOverlay)
    models: ModelsOverlay = Field(default_factory=ModelsOverlay)
    run_defaults: RunDefaults = Field(default_factory=RunDefaults)
    advanced: AdvancedOverlay = Field(default_factory=AdvancedOverlay)


# Shipped out of the box so the Providers section is never empty: a Theta
# (AntChat) connection with its endpoint pre-filled; the user only adds a key.
# Seeded whenever the overlay has no connections yet (fresh install or a
# never-populated file); deleting it sticks until the next fresh start.
DEFAULT_PROVIDER_CONNECTIONS: dict[str, ProviderConnection] = {
    "theta": ProviderConnection(
        protocol="openai_compatible",
        api_base="https://antchat.alipay.com/v1",
        api_key_envs=["ANTCHAT_API_KEY"],
        thinking_style="none",
        label="Theta (AntChat)",
    ),
}


def _seed_default_connections() -> None:
    if not store.models.provider_connections:
        store.models.provider_connections.update(
            {name: c.model_copy() for name, c in DEFAULT_PROVIDER_CONNECTIONS.items()}
        )


# Single module-level instance, NEVER rebound — other modules import it by
# name, so load/reset copy field values in place instead of replacing it.
store = WebSettings()


def _replace_store(src: WebSettings) -> None:
    for name in WebSettings.model_fields:
        setattr(store, name, getattr(src, name))


def overlay_path() -> Path:
    """Where the JSON overlay lives — repo root ``web_settings.json`` unless
    ``SF_WEB_SETTINGS_PATH`` overrides it (kept identical to ``api.deps``)."""
    default = Path(__file__).resolve().parents[2] / "web_settings.json"
    return Path(os.environ.get("SF_WEB_SETTINGS_PATH", str(default)))


def load_overlay_file() -> None:
    """Read the JSON overlay file INTO the store, without applying it.

    Safe before the ``settings`` singleton exists (e.g. the CLI setup wizard,
    which edits the overlay and must run before settings are constructed). A
    missing/corrupt file leaves an empty overlay.
    """
    path = overlay_path()
    if not path.exists():
        _replace_store(WebSettings())  # deterministic: file absent → empty store
        return
    try:
        _replace_store(WebSettings.model_validate_json(path.read_text()))
    except Exception:
        logger.warning("Corrupt %s — starting with empty overlay", path, exc_info=True)
        _replace_store(WebSettings())


def save_overlay() -> None:
    """Atomically persist the current store to the overlay file (tmp + replace)."""
    path = overlay_path()
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(store.model_dump_json(indent=2) + "\n")
    os.replace(tmp, path)


# Legacy .env knobs that now live in the overlay. The value carriers here are
# NON-secret (search backend name, skill flag, cache dir, proxy) — key VALUES
# never migrate. ``searchos --setup`` offers to strip these from .env once the
# overlay owns them; the migration itself is non-destructive (seed only).
MIGRATABLE_ENV_KEYS: tuple[str, ...] = (
    "SF_ENABLE_SKILLS",
    "SF_ENABLE_EXPLORE_BATCH",
    "SF_ENABLE_ACCESS_SKILL_GENERATION",
    "SF_ACCESS_SKILL_MAX_PER_RUN",
    "SF_SEARCH_PROVIDER",
    "SF_BROWSER_DISK_CACHE_DIR",
    "HTTP_PROXY",
    "HTTPS_PROXY",
)


def migrate_legacy_env_into_overlay() -> list[str]:
    """Seed overlay fields from legacy .env/env knobs when unset (non-destructive).

    Runs inside ``load_and_apply`` after the file is read: where the overlay has
    no value yet but the old env var is set, copy it in so the overlay becomes
    the single source of truth without changing behavior. Idempotent — a second
    run finds the overlay populated and skips. Never deletes from .env (that is
    an explicit ``searchos --setup`` step). Returns the env var names seeded.
    """
    seeded: list[str] = []

    raw_skills = os.environ.get("SF_ENABLE_SKILLS", "").strip().lower()
    if store.run_defaults.enable_skills is None and raw_skills:
        store.run_defaults.enable_skills = raw_skills in {"1", "true", "yes", "on"}
        seeded.append("SF_ENABLE_SKILLS")

    raw_explore_batch = os.environ.get("SF_ENABLE_EXPLORE_BATCH", "").strip().lower()
    if store.run_defaults.enable_explore_batch is None and raw_explore_batch:
        store.run_defaults.enable_explore_batch = raw_explore_batch in {
            "1", "true", "yes", "on",
        }
        seeded.append("SF_ENABLE_EXPLORE_BATCH")

    raw_access_generation = os.environ.get(
        "SF_ENABLE_ACCESS_SKILL_GENERATION", "",
    ).strip().lower()
    if store.skills.enable_access_skill_generation is None and raw_access_generation:
        store.skills.enable_access_skill_generation = raw_access_generation in {
            "1", "true", "yes", "on",
        }
        seeded.append("SF_ENABLE_ACCESS_SKILL_GENERATION")

    raw_access_max = os.environ.get("SF_ACCESS_SKILL_MAX_PER_RUN", "").strip()
    if store.skills.access_skill_max_per_run is None and raw_access_max:
        try:
            parsed_access_max = int(raw_access_max)
            if 1 <= parsed_access_max <= 10:
                store.skills.access_skill_max_per_run = parsed_access_max
                seeded.append("SF_ACCESS_SKILL_MAX_PER_RUN")
            else:
                logger.warning(
                    "Ignoring SF_ACCESS_SKILL_MAX_PER_RUN outside 1..10: %r",
                    raw_access_max,
                )
        except ValueError:
            logger.warning(
                "Ignoring invalid SF_ACCESS_SKILL_MAX_PER_RUN: %r", raw_access_max,
            )

    search = os.environ.get("SF_SEARCH_PROVIDER", "").strip()
    if store.models.search_provider is None and search:
        store.models.search_provider = search
        seeded.append("SF_SEARCH_PROVIDER")

    cache_dir = os.environ.get("SF_BROWSER_DISK_CACHE_DIR", "").strip()
    if store.advanced.browser_disk_cache_dir is None and cache_dir:
        store.advanced.browser_disk_cache_dir = cache_dir
        seeded.append("SF_BROWSER_DISK_CACHE_DIR")

    proxy = os.environ.get("HTTPS_PROXY", "").strip() or os.environ.get("HTTP_PROXY", "").strip()
    if store.advanced.https_proxy is None and proxy:
        store.advanced.https_proxy = proxy
        # Report whichever proxy var(s) are present so cleanup can strip them.
        seeded.extend(v for v in ("HTTP_PROXY", "HTTPS_PROXY") if os.environ.get(v))

    if seeded:
        save_overlay()
    return seeded


def load_and_apply() -> None:
    """Read the JSON overlay (lenient) and apply it to the runtime settings.

    Safe to call from any entry point (web app or CLI): a missing/corrupt file
    yields an empty overlay, the default connections are seeded, legacy .env
    knobs are migrated in, then the overlay is applied onto the ``settings``
    singleton.
    """
    load_overlay_file()
    _seed_default_connections()
    migrate_legacy_env_into_overlay()
    apply_to_runtime()


def apply_to_runtime() -> None:
    """Apply the overlay onto the global settings singleton.

    Skills / search_provider / max_time_s are consumed lazily at
    run construction, so only effort, role bindings, and scalar knobs need to
    be pushed here.
    """
    from searchos.config.effort import apply_effort
    from searchos.config.settings import settings

    if store.effort.level:
        try:
            apply_effort(store.effort.level, store.effort.overrides or None)
        except ValueError:
            logger.warning("Stale effort overrides %s — level applied without them",
                           store.effort.overrides, exc_info=True)
            apply_effort(store.effort.level)

    # Custom profiles before roles/overrides — bindings may point at them.
    # Name collisions with env/preset profiles are blocked at creation time;
    # should one arise later (e.g. via a provider switch) the custom wins,
    # deterministically.
    from searchos.config.profiles import ModelProfile
    conns = store.models.provider_connections
    for name, cp in store.models.custom_profiles.items():
        # A provider_ref inherits the connection wholesale; only the model id and
        # sampling knobs stay on the card. Fall back to inline fields when unset
        # (or the ref was deleted out from under it).
        conn = conns.get(cp.provider_ref) if cp.provider_ref else None
        settings.profiles[name] = ModelProfile(
            model=cp.model,
            provider=conn.protocol if conn else cp.provider,
            api_base=conn.api_base if conn else cp.api_base,
            api_key_env=conn.resolve_key_env(cp.api_key_env) if conn else cp.api_key_env,
            temperature=cp.temperature,
            max_tokens=cp.max_tokens,  # agent-work default; ModelProfile's 4096 is too tight
            enable_thinking=cp.enable_thinking,
            thinking_style=conn.thinking_style if conn else cp.thinking_style,
            rpm=cp.rpm,
            tpm=cp.tpm,
        )

    for name, ov in store.models.profile_overrides.items():
        profile = settings.profiles.get(name)
        if profile is None:
            logger.warning("Profile override for missing profile %r — skipped", name)
            continue
        for field in ("model", "api_base", "api_key_env"):
            value = getattr(ov, field)
            if value is not None:
                setattr(profile, field, value)
        # A provider_ref wins over inline connection fields for this base card.
        conn = conns.get(ov.provider_ref) if ov.provider_ref else None
        if conn:
            profile.provider = conn.protocol
            profile.api_base = conn.api_base
            profile.api_key_env = conn.resolve_key_env(ov.api_key_env)
            profile.thinking_style = conn.thinking_style
        if ov.temperature is not None:
            profile.temperature = ov.temperature
        if ov.enable_thinking is not None:
            profile.enable_thinking = ov.enable_thinking
        if ov.rpm is not None:
            profile.rpm = ov.rpm
        if ov.tpm is not None:
            profile.tpm = ov.tpm

    for role, profile in store.models.roles.items():
        if role not in settings.roles:
            logger.warning("Persisted binding for unknown role %r — skipped", role)
            continue
        if profile not in settings.profiles:
            logger.warning("Role %r bound to missing profile %r — skipped", role, profile)
            continue
        settings.roles[role] = profile

    if store.models.browser_backend:
        settings.browser_backend = store.models.browser_backend
    if store.run_defaults.search_max_results is not None:
        settings.search_max_results = store.run_defaults.search_max_results
    if store.run_defaults.enable_skills is not None:
        settings.enable_skills = store.run_defaults.enable_skills
    if store.run_defaults.enable_explore_batch is not None:
        settings.enable_explore_batch = store.run_defaults.enable_explore_batch
    if store.skills.enable_access_skill_generation is not None:
        settings.enable_access_skill_generation = (
            store.skills.enable_access_skill_generation
        )
    if store.skills.access_skill_max_per_run is not None:
        settings.access_skill_max_per_run = store.skills.access_skill_max_per_run

    # Advanced knobs. Proxy is not a settings field — the HTTP stack reads it
    # from the environment, so export it there (and to HTTP_PROXY); clearing the
    # override removes the env vars so a bare os.environ base can show through.
    adv = store.advanced
    if adv.llm_max_retries is not None:
        settings.llm_max_retries = adv.llm_max_retries
    if adv.orch_coverage_stall_rounds is not None:
        settings.orch_coverage_stall_rounds = adv.orch_coverage_stall_rounds
    if adv.browser_disk_cache_dir is not None:
        settings.browser_disk_cache_dir = adv.browser_disk_cache_dir
    if adv.use_layered_context is not None:
        settings.use_layered_context = adv.use_layered_context
    if adv.https_proxy is not None:
        for var in ("HTTP_PROXY", "HTTPS_PROXY"):
            if adv.https_proxy:
                os.environ[var] = adv.https_proxy
            else:
                os.environ.pop(var, None)


__all__ = [
    "EffortLevel",
    "EffortOverlay",
    "SkillsOverlay",
    "ProviderConnection",
    "ProfileOverride",
    "CustomProfile",
    "ModelsOverlay",
    "RunDefaults",
    "AdvancedOverlay",
    "WebSettings",
    "DEFAULT_PROVIDER_CONNECTIONS",
    "MIGRATABLE_ENV_KEYS",
    "store",
    "overlay_path",
    "load_overlay_file",
    "save_overlay",
    "load_and_apply",
    "apply_to_runtime",
    "migrate_legacy_env_into_overlay",
]
