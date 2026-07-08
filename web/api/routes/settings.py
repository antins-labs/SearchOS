"""Settings routes — web counterpart of the TUI's /effort and /skill, plus
role bindings and search/browser backend switching.

Persistence model: env/.env is the base layer; ``settings_store`` holds the
web-set deltas in ``web_settings.json`` and applies them onto the global
``settings`` singleton. NOTE the 7 effort knobs are read live from that
singleton by running sessions, so changing effort affects in-flight runs too
(single-user local deployment tradeoff, same as the TUI).
"""

from __future__ import annotations

import os
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from api import settings_store
from api.settings_store import BROWSER_BACKENDS, SKILL_CATEGORIES, EffortLevel, store

router = APIRouter(prefix="/api/settings")


# --- payload models ---

class EffortUpdate(BaseModel, extra="forbid"):
    level: EffortLevel
    overrides: dict[str, int] = Field(default_factory=dict)


class SkillsUpdate(BaseModel, extra="forbid"):
    access_only: list[str] | None = None
    access_deny: list[str] | None = None
    strategy_deny: list[str] | None = None
    orchestrator_deny: list[str] | None = None


class SkillToggle(BaseModel, extra="forbid"):
    enabled: bool


class RolesUpdate(BaseModel, extra="forbid"):
    roles: dict[str, str]


class SearchBackendUpdate(BaseModel, extra="forbid"):
    provider: str | None = None


class MiscUpdate(BaseModel, extra="forbid"):
    max_time_s: int | None = Field(default=None, gt=0)
    search_max_results: int | None = Field(default=None, gt=0)
    enable_skills: bool | None = None
    browser_backend: Literal["aiohttp", "crawl4ai", "search_engine", "jina"] | None = None


# --- view builders ---

def _effort_view() -> dict:
    from searchos.config.effort import EFFORT_KEYS, EFFORT_LEVELS
    from searchos.config.settings import settings

    return {
        "level": store.effort.level or "medium",
        "knobs": {k: getattr(settings, k) for k in EFFORT_KEYS},
        "overrides": store.effort.overrides,
        "levels": EFFORT_LEVELS,
    }


def _skills_view() -> dict:
    from searchos.config.settings import settings

    catalog = settings_store.skill_catalog()
    return {
        "enable_skills": settings.enable_skills,
        "access_mode": "only" if store.skills.access_only is not None else "router",
        "categories": {
            cat: [
                {
                    "name": s.meta.name,
                    "description": (s.meta.description or s.meta.trigger or "").strip(),
                    "status": s.meta.status.value,
                    "enabled": settings_store.skill_enabled(cat, s.meta.name),
                }
                for s in skills
            ]
            for cat, skills in catalog.items()
        },
    }


def _key_set(env_name: str, fallback: str = "") -> bool:
    return bool(os.environ.get(env_name) or fallback)


def _models_view() -> dict:
    from searchos.config.providers import active_provider
    from searchos.config.settings import settings
    from searchos.tools.simple_browser.search import (
        SEARCH_PROVIDER_INFO,
        resolve_search_provider_name,
    )

    profiles = {}
    for name, p in settings.profiles.items():
        profiles[name] = {
            "model": p.model,
            "provider": p.provider,
            "api_base": p.api_base,
            "api_key_env": p.api_key_env,
            "api_key_set": _key_set(p.api_key_env, p.api_key_fallback),
            "temperature": p.temperature,
            "max_tokens": p.max_tokens,
            "enable_thinking": p.enable_thinking,
        }

    search_key_fallbacks = {
        "serper": settings.serper_api_key,
        "tavily": settings.tavily_api_key,
    }
    providers = [
        {
            "name": name,
            "label": info["label"],
            "api_key_env": info["api_key_env"],
            "key_set": _key_set(info["api_key_env"], search_key_fallbacks.get(name, "")),
            "doc_url": info["doc_url"],
        }
        for name, info in SEARCH_PROVIDER_INFO.items()
    ]

    return {
        "active_provider_preset": active_provider(),
        "profiles": profiles,
        "roles": dict(settings.roles),
        "role_overrides": dict(store.models.roles),
        "search": {
            "resolved": resolve_search_provider_name(store.models.search_provider or ""),
            "configured": store.models.search_provider,
            "providers": providers,
        },
        "browser_backend": settings.browser_backend,
    }


def _run_defaults_view() -> dict:
    from searchos.config.settings import settings

    rd = store.run_defaults
    return {
        "max_time_s": rd.max_time_s if rd.max_time_s is not None else settings.default_max_time_s,
        "search_max_results": settings.search_max_results,
        "enable_skills": settings.enable_skills,
    }


def _aggregate_view() -> dict:
    return {
        "effort": _effort_view(),
        "skills": _skills_view(),
        "models": _models_view(),
        "run_defaults": _run_defaults_view(),
    }


# --- endpoints ---

@router.get("")
async def get_settings():
    return _aggregate_view()


@router.put("/effort")
async def put_effort(req: EffortUpdate):
    from searchos.config.effort import EFFORT_KEYS

    bad = set(req.overrides) - set(EFFORT_KEYS)
    if bad:
        raise HTTPException(400, f"Unknown effort knobs: {sorted(bad)}. Valid: {list(EFFORT_KEYS)}")

    def patch(s):
        s.effort.level = req.level
        s.effort.overrides = req.overrides

    await settings_store.update(patch)
    return _effort_view()


@router.get("/skills")
async def get_skills():
    return _skills_view()


@router.put("/skills")
async def put_skills(req: SkillsUpdate):
    pools = settings_store.skill_pools()
    all_names = set().union(*pools.values()) if pools else set()

    unmatched = []
    for field in ("access_only", "access_deny", "strategy_deny", "orchestrator_deny"):
        names = getattr(req, field)
        if names:
            unmatched.extend(n for n in names if n not in all_names)
    if unmatched:
        raise HTTPException(400, {"detail": "Unknown skills", "unmatched": sorted(set(unmatched))})

    def patch(s):
        if req.access_only is not None:
            s.skills.access_only = req.access_only
        if req.access_deny is not None:
            s.skills.access_deny = req.access_deny
        if req.strategy_deny is not None:
            s.skills.strategy_deny = req.strategy_deny
        if req.orchestrator_deny is not None:
            s.skills.orchestrator_deny = req.orchestrator_deny
        settings_store.normalize_access_only(pools.get("access", set()))

    await settings_store.update(patch)
    return _skills_view()


@router.patch("/skills/{name}")
async def patch_skill(name: str, req: SkillToggle):
    pools = settings_store.skill_pools()
    category = next((cat for cat, names in pools.items() if name in names), None)
    if category is None:
        raise HTTPException(404, f"Unknown skill: {name!r}")

    def patch(s):
        # Same semantics as TUI /skill on|off (tui/app.py _cmd_skill).
        if category == "access":
            if req.enabled:
                s.skills.access_deny = [n for n in s.skills.access_deny if n != name]
                if s.skills.access_only is not None and name not in s.skills.access_only:
                    s.skills.access_only.append(name)
            else:
                if name not in s.skills.access_deny:
                    s.skills.access_deny.append(name)
                if s.skills.access_only is not None:
                    s.skills.access_only = [n for n in s.skills.access_only if n != name]
            settings_store.normalize_access_only(pools.get("access", set()))
        else:
            deny_field = f"{category}_deny"
            deny = getattr(s.skills, deny_field)
            if req.enabled:
                setattr(s.skills, deny_field, [n for n in deny if n != name])
            elif name not in deny:
                deny.append(name)

    await settings_store.update(patch)
    return _skills_view()


@router.put("/skills/category/{category}")
async def put_skill_category(category: str, req: SkillToggle):
    if category not in SKILL_CATEGORIES:
        raise HTTPException(400, f"Unknown category: {category!r}. Valid: {list(SKILL_CATEGORIES)}")
    pools = settings_store.skill_pools()

    def patch(s):
        if category == "access":
            if req.enabled:
                s.skills.access_only = None
                s.skills.access_deny = []
            else:
                s.skills.access_only = []
        else:
            deny_field = f"{category}_deny"
            setattr(s.skills, deny_field, sorted(pools.get(category, set())) if not req.enabled else [])

    await settings_store.update(patch)
    return _skills_view()


@router.get("/models")
async def get_models():
    return _models_view()


@router.put("/models/roles")
async def put_roles(req: RolesUpdate):
    from searchos.config.settings import ROLE_NAMES, settings

    warnings = []
    for role, profile in req.roles.items():
        if role not in ROLE_NAMES:
            raise HTTPException(400, f"Unknown role: {role!r}. Valid: {list(ROLE_NAMES)}")
        if profile not in settings.profiles:
            raise HTTPException(400, f"Unknown profile: {profile!r}. Valid: {list(settings.profiles)}")
        p = settings.profiles[profile]
        if not _key_set(p.api_key_env, p.api_key_fallback):
            warnings.append(
                f"Profile {profile!r} needs {p.api_key_env} which is not set — runs using role "
                f"{role!r} will fail until it is added to .env"
            )

    def patch(s):
        s.models.roles.update(req.roles)

    await settings_store.update(patch)
    return {"roles": dict(settings.roles), "role_overrides": dict(store.models.roles), "warnings": warnings}


@router.put("/search-backend")
async def put_search_backend(req: SearchBackendUpdate):
    from searchos.config.settings import settings
    from searchos.tools.simple_browser.search import SEARCH_PROVIDER_INFO

    if req.provider is not None:
        if req.provider not in SEARCH_PROVIDER_INFO:
            raise HTTPException(
                400, f"Unknown search provider: {req.provider!r}. Valid: {list(SEARCH_PROVIDER_INFO)}")
        if req.provider in ("serper", "tavily"):
            env_name = SEARCH_PROVIDER_INFO[req.provider]["api_key_env"]
            fallback = settings.serper_api_key if req.provider == "serper" else settings.tavily_api_key
            if not _key_set(env_name, fallback):
                raise HTTPException(400, f"{env_name} not set in .env — add it before switching")

    def patch(s):
        s.models.search_provider = req.provider

    await settings_store.update(patch)
    return _models_view()["search"]


@router.put("/misc")
async def put_misc(req: MiscUpdate):
    def patch(s):
        if req.max_time_s is not None:
            s.run_defaults.max_time_s = req.max_time_s
        if req.search_max_results is not None:
            s.run_defaults.search_max_results = req.search_max_results
        if req.enable_skills is not None:
            s.run_defaults.enable_skills = req.enable_skills
        if req.browser_backend is not None:
            s.models.browser_backend = req.browser_backend

    await settings_store.update(patch)
    view = _run_defaults_view()
    view["browser_backend"] = _models_view()["browser_backend"]
    return view


@router.post("/reset")
async def reset_settings():
    settings_store.reset()
    return _aggregate_view()
