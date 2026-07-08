"""Settings routes — web counterpart of the TUI's /effort and /skill.

Persistence model: env/.env is the base layer; ``settings_store`` holds the
web-set deltas in ``web_settings.json`` and applies them onto the global
``settings`` singleton. NOTE the 7 effort knobs are read live from that
singleton by running sessions, so changing effort affects in-flight runs too
(single-user local deployment tradeoff, same as the TUI).

Model/provider endpoints live in routes/models.py; shared response views in
``settings_views``; skill catalog semantics in ``skills_catalog``.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from api import settings_store, skills_catalog
from api.settings_store import EffortLevel
from api.settings_views import aggregate_view, effort_view, models_view, run_defaults_view, skills_view
from api.skills_catalog import SKILL_CATEGORIES

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


class MiscUpdate(BaseModel, extra="forbid"):
    max_time_s: int | None = Field(default=None, gt=0)
    search_max_results: int | None = Field(default=None, gt=0)
    enable_skills: bool | None = None
    browser_backend: Literal["aiohttp", "crawl4ai", "search_engine", "jina"] | None = None


# --- endpoints ---

@router.get("")
async def get_settings():
    return aggregate_view()


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
    return effort_view()


@router.get("/skills")
async def get_skills():
    return skills_view()


@router.put("/skills")
async def put_skills(req: SkillsUpdate):
    pools = skills_catalog.skill_pools()
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
        skills_catalog.normalize_access_only(pools.get("access", set()))

    await settings_store.update(patch)
    return skills_view()


@router.patch("/skills/{name}")
async def patch_skill(name: str, req: SkillToggle):
    pools = skills_catalog.skill_pools()
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
            skills_catalog.normalize_access_only(pools.get("access", set()))
        else:
            deny_field = f"{category}_deny"
            deny = getattr(s.skills, deny_field)
            if req.enabled:
                setattr(s.skills, deny_field, [n for n in deny if n != name])
            elif name not in deny:
                deny.append(name)

    await settings_store.update(patch)
    return skills_view()


@router.put("/skills/category/{category}")
async def put_skill_category(category: str, req: SkillToggle):
    if category not in SKILL_CATEGORIES:
        raise HTTPException(400, f"Unknown category: {category!r}. Valid: {list(SKILL_CATEGORIES)}")
    pools = skills_catalog.skill_pools()

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
    return skills_view()


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
    view = run_defaults_view()
    view["browser_backend"] = models_view()["browser_backend"]
    return view


@router.post("/reset")
async def reset_settings():
    settings_store.reset()
    return aggregate_view()
