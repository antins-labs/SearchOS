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
BROWSER_BACKENDS = ("aiohttp", "crawl4ai", "search_engine", "jina")
SKILL_CATEGORIES = ("orchestrator", "access", "strategy")


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


# --- skill catalog ---

_registry = None  # reused across requests; its mtime cache skips re-parsing


def skill_catalog() -> dict[str, list]:
    """Skills grouped by category, straight from the library directory.

    Uses SkillRegistry directly — never SearchSession, whose __init__ eagerly
    resolves every role model and raises without API keys.
    """
    global _registry
    from searchos.config.settings import settings
    from searchos.skills.catalog.registry import SkillRegistry
    from searchos.skills.core.models import SkillCategory

    lib = Path(settings.skill_library_path)
    if not lib.is_absolute():
        lib = Path(__file__).resolve().parent.parent.parent / lib
    if not settings.enable_skills or not lib.exists():
        return {name: [] for name in SKILL_CATEGORIES}

    if _registry is None:
        _registry = SkillRegistry()
    reg = _registry
    reg.load_directory(lib)
    return {
        cat.value: sorted(reg.list_by_category(cat), key=lambda s: s.meta.name)
        for cat in (SkillCategory.ORCHESTRATOR, SkillCategory.ACCESS, SkillCategory.STRATEGY)
    }


def skill_pools() -> dict[str, set[str]]:
    return {cat: {s.meta.name for s in skills} for cat, skills in skill_catalog().items()}


def skill_enabled(category: str, name: str) -> bool:
    """Enabled state per the TUI semantics (deny sets; access also has `only`)."""
    s = store.skills
    if category == "access":
        if name in s.access_deny:
            return False
        return s.access_only is None or name in s.access_only
    if category == "strategy":
        return name not in s.strategy_deny
    if category == "orchestrator":
        return name not in s.orchestrator_deny
    return True


def normalize_access_only(pool: set[str]) -> None:
    """TUI parity: a full (or superset) access pin hands control back to the router."""
    only = store.skills.access_only
    if only is not None and pool and set(only) >= pool:
        store.skills.access_only = None


# --- run-time merge ---

def effective_skill_kwargs(overrides=None) -> dict[str, set[str] | None]:
    """Merge store + per-run overrides into SearchSession.run skill kwargs.

    Request fields win per key when provided; names are intersected with the
    live catalog so stale entries in the persisted JSON never break a run.
    """
    pools = skill_pools()
    all_names = set().union(*pools.values()) if pools else set()

    def pick(field: str):
        if overrides is not None and getattr(overrides, field, None) is not None:
            return getattr(overrides, field)
        return getattr(store.skills, field)

    only = pick("access_only")
    kwargs: dict[str, set[str] | None] = {
        "access_only": (set(only) & pools.get("access", set())) if only is not None else None,
        "access_deny": set(pick("access_deny")) & all_names,
        "strategy_deny": set(pick("strategy_deny")) & all_names,
        "orchestrator_deny": set(pick("orchestrator_deny")) & all_names,
    }
    return kwargs
