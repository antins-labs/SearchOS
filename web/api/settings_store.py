"""Persisted web settings — a JSON overlay on top of the env-based settings.

The env/.env layer stays the base configuration; this store holds only the
deltas the user sets from the web UI (effort level, skill toggles, role
bindings, run defaults). Sparse semantics throughout: ``None`` / absent means
"no override, env base wins". The file lives next to ``.env`` at the repo root
(``web_settings.json``, override with ``SF_WEB_SETTINGS_PATH``) — deliberately
NOT inside the workspace root, whose subdirectories are scanned as sessions.
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from api.deps import WEB_SETTINGS_PATH

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


class WebSettings(BaseModel, extra="forbid"):
    version: int = 1
    effort: EffortOverlay = Field(default_factory=EffortOverlay)
    skills: SkillsOverlay = Field(default_factory=SkillsOverlay)
    models: ModelsOverlay = Field(default_factory=ModelsOverlay)
    run_defaults: RunDefaults = Field(default_factory=RunDefaults)


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


_LOCK = asyncio.Lock()
# Single module-level instance, NEVER rebound — other modules import it by
# name, so load/reset copy field values in place instead of replacing it.
store = WebSettings()


def _replace_store(src: WebSettings) -> None:
    for name in WebSettings.model_fields:
        setattr(store, name, getattr(src, name))


# --- persistence ---

def _path() -> Path:
    return Path(WEB_SETTINGS_PATH)


def save() -> None:
    """Atomic write: tmp file + os.replace."""
    path = _path()
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(store.model_dump_json(indent=2) + "\n")
    os.replace(tmp, path)


def load_and_apply() -> None:
    """Startup: read the JSON overlay (lenient) and apply it to the runtime."""
    path = _path()
    if path.exists():
        try:
            _replace_store(WebSettings.model_validate_json(path.read_text()))
        except Exception:
            logger.warning("Corrupt %s — starting with empty overlay", path, exc_info=True)
            _replace_store(WebSettings())
    _seed_default_connections()
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


async def update(patch_fn, reload: bool = False) -> WebSettings:
    """Mutate the store under the lock, apply to runtime, persist atomically.

    ``patch_fn(store)`` mutates in place; validation errors raised inside it
    propagate before anything is saved. ``reload=True`` rebuilds the settings
    singleton from env before replaying the overlay — required whenever the
    patch REMOVES an override (plain replay can't restore the base value).
    """
    from searchos.config.settings import reload_settings_in_place

    async with _LOCK:
        patch_fn(store)
        if reload:
            reload_settings_in_place()
        apply_to_runtime()
        save()
        return store


async def update_env(env_updates: dict[str, str], patch_fn=None) -> None:
    """Write env vars (keys / provider knobs) through to .env and the runtime.

    Full transaction under the lock:
      1. update os.environ first (empty value → pop)
      2. dry-run ``Settings()`` — an invalid combination (e.g. a local preset
         without SF_MODEL) raises BEFORE anything touches disk; the previous
         os.environ values are restored on failure
      3. atomic .env write
      4. rebuild the settings singleton in place from the new env
      5. optional store patch (e.g. clearing role overrides), then re-apply
         the web overlay — reload resets effort knobs etc. to env defaults,
         so this replay is mandatory, not an optimization
    Never log values here — key material must not reach any log line.
    """
    from searchos.config import env_file
    from searchos.config.settings import Settings, reload_settings_in_place

    from api import deps

    async with _LOCK:
        prev = {k: os.environ.get(k) for k in env_updates}
        try:
            for key, value in env_updates.items():
                if value:
                    os.environ[key] = value
                else:
                    os.environ.pop(key, None)
            fresh = Settings()  # dry-run against the new env
        except Exception:
            for key, value in prev.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
            raise

        env_file.update_env_file(Path(deps.ENV_FILE_PATH), env_updates)
        reload_settings_in_place(fresh)
        if patch_fn is not None:
            patch_fn(store)
        apply_to_runtime()
        save()


def reset() -> None:
    """Delete the overlay file and restore the pure env-based settings.

    Both singletons must be mutated IN PLACE — every module holds a reference
    to the same objects, so swapping them out would leave stale copies behind.
    """
    _path().unlink(missing_ok=True)
    _replace_store(WebSettings())

    from searchos.config.settings import reload_settings_in_place
    reload_settings_in_place()
