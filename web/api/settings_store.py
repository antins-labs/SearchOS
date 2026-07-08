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


class ModelsOverlay(BaseModel, extra="forbid"):
    roles: dict[str, str] = Field(default_factory=dict)  # sparse role→profile deltas
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


async def update(patch_fn) -> WebSettings:
    """Mutate the store under the lock, apply to runtime, persist atomically.

    ``patch_fn(store)`` mutates in place; validation errors raised inside it
    propagate before anything is saved.
    """
    async with _LOCK:
        patch_fn(store)
        apply_to_runtime()
        save()
        return store


def reset() -> None:
    """Delete the overlay file and restore the pure env-based settings.

    Both singletons must be mutated IN PLACE — every module holds a reference
    to the same objects, so swapping them out would leave stale copies behind.
    """
    _path().unlink(missing_ok=True)
    _replace_store(WebSettings())

    from searchos.config.settings import reload_settings_in_place
    reload_settings_in_place()
