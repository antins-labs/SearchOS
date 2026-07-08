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

from pydantic import BaseModel, Field

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


class ProfileOverride(BaseModel, extra="forbid"):
    """Sparse per-field deltas on a base (env-defined) profile. None = keep base."""
    model: str | None = None
    api_base: str | None = None
    api_key_env: str | None = None


class CustomProfile(BaseModel, extra="forbid"):
    """A user-created profile. Self-contained — survives provider switches."""
    model: str
    provider: Literal["openai_compatible", "openai", "anthropic"] = "openai_compatible"
    api_base: str = ""
    api_key_env: str = "OPENAI_API_KEY"


class ModelsOverlay(BaseModel, extra="forbid"):
    roles: dict[str, str] = Field(default_factory=dict)  # sparse role→profile deltas
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
    for name, cp in store.models.custom_profiles.items():
        settings.profiles[name] = ModelProfile(
            model=cp.model, provider=cp.provider,
            api_base=cp.api_base, api_key_env=cp.api_key_env,
            max_tokens=16384,  # agent-work default; ModelProfile's 4096 is too tight
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
