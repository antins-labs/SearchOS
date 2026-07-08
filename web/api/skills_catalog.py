"""Skill catalog access + enabled-state semantics for the web settings API.

Reads the on-disk skill library via SkillRegistry — never SearchSession,
whose __init__ eagerly resolves every role model and raises without API keys.
Enabled/deny semantics mirror the TUI (/skill): deny sets per category, plus
an optional `access_only` pin (None = the skill router decides).
"""

from __future__ import annotations

from pathlib import Path

from api.settings_store import store

SKILL_CATEGORIES = ("orchestrator", "access", "strategy")

_registry = None  # reused across requests; its mtime cache skips re-parsing


def skill_catalog() -> dict[str, list]:
    """Skills grouped by category, straight from the library directory."""
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
