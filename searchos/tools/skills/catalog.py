"""技能发现、访问范围和失败记忆读取。"""

from __future__ import annotations

import json
from contextvars import ContextVar

from langchain_core.tools import tool

_skill_access_policy_var: ContextVar[dict] = ContextVar("skill_access_policy", default={})


def _skill_allowed(skill) -> bool:
    policy = _skill_access_policy_var.get()
    from searchos.skills.names import canonical_skill_name, canonical_skill_names
    category, name = skill.meta.category.value, canonical_skill_name(skill.meta.name)
    if name in canonical_skill_names(policy.get(f"{category}_deny", ())):
        return False
    only = policy.get("access_only")
    return category != "access" or only is None or name in canonical_skill_names(only)


def _registry():
    from searchos.agents.runtime import _skill_registry_var
    return _skill_registry_var.get()


# Only hide a skill when it's failed repeatedly — a single extraction
# miss could be a transient network / judge hiccup. Plan §6.4 bans "已
# 被证实无效"; one observation doesn't证实.
SKILL_BAN_MIN_OBSERVATIONS = 2


def _banned_skills_from_state() -> set[str]:
    """Return skill names flagged as anti-patterns in the current session.

    Plan §6.4 with a guard: only skills with ``observed_count >=
    SKILL_BAN_MIN_OBSERVATIONS`` are hidden. A first-time failure still
    records the AntiPattern (for prompt-level "warn" surface) but
    doesn't yet remove the skill from discovery.
    """
    from searchos.tools.search_state import _workspace_var
    ws = _workspace_var.get()
    if ws is None:
        return set()
    try:
        state = ws.load_state()
    except Exception:
        return set()
    banned: set[str] = set()
    for p in getattr(state.strategy_log, "patterns", []) or []:
        kind = getattr(p.kind, "value", str(p.kind))
        if (kind == "skill" and p.signature
                and p.observed_count >= SKILL_BAN_MIN_OBSERVATIONS):
            banned.add(p.signature)
    return banned


@tool
async def list_skills(category: str = "", availability: str = "", query: str = "", offset: int = 0, limit: int = 5) -> str:
    """Discover skills for your current task, source or missing capability.

    query accepts a natural-language need in any language, an exact skill name,
    or a source domain/URL. Results are ranked candidates with match reasons;
    load_skill to check instructions and limitations before deciding to use one.
    Empty query browses the directory without model selection. No match is fine:
    continue with ordinary web tools. An error is not evidence of no matching skill.

    Args:
        category (str): ``"strategy"`` | ``"access"`` | ``"orchestrator"`` — empty = access + strategy.
        availability (str): ``"enabled"`` | ``"disabled"`` — empty = all.
            The runtime registry contains enabled Skills only.
    """
    from searchos.config.settings import settings
    if not settings.enable_skills:
        return json.dumps({"skills": [], "count": 0, "note": "skill system disabled"})
    reg = _registry()
    if reg is None:
        return json.dumps({"skills": [], "count": 0, "error": "skill registry not bound"})
    banned = _banned_skills_from_state()
    if category and category not in {'access', 'strategy', 'orchestrator'}:
        return json.dumps({'skills': [], 'count': 0, 'error': 'invalid skill category'})
    if len(query) > 2000:
        return json.dumps({'skills': [], 'count': 0, 'error': 'Describe the current retrieval need in at most 2000 characters.'})
    candidates = []
    for s in reg.list_all():
        if not _skill_allowed(s):
            continue
        if s.meta.name in banned:
            continue
        if category and s.meta.category.value != category:
            continue
        if availability and s.meta.availability.value != availability:
            continue
        if not category and s.meta.category.value == 'orchestrator':
            continue
        candidates.append(s)
    matches = {}
    if query.strip():
        from searchos.skills.catalog.router import discover_skills
        try:
            ranked = await discover_skills(query, candidates, limit=settings.skill_router_top_k,
                cache=getattr(reg, 'discovery_cache', None), semantic=settings.enable_skill_router)
        except Exception as exc:
            return json.dumps({'skills': [], 'count': 0, 'error': 'skill_discovery_failed',
                'error_type': type(exc).__name__,
                'note': 'Discovery could not complete. Retry later, browse with an empty query, or continue with web tools.'})
        by_name = {s.meta.name: s for s in candidates}
        candidates = [by_name[item['name']] for item in ranked]
        matches = {item['name']: item['reason'] for item in ranked}
    out = [{
            "name": s.meta.name,
            "description": (s.meta.description or s.meta.trigger or "")[:500],
            "category": s.meta.category.value,
            "trigger": s.meta.trigger,
            "compatibility": s.meta.compatibility,
            **({'match_reason': matches[s.meta.name]} if s.meta.name in matches else {}),
        } for s in candidates]
    start, size = max(0, offset), min(50, max(1, limit))
    return json.dumps(
        {"skills": out[start:start + size], "count": len(out),
         "next_offset": start + size if start + size < len(out) else None},
        ensure_ascii=False,
    )


@tool
async def load_anti_patterns(skill_name: str, context: str = "") -> str:
    """Return full anti-pattern entries for a Skill.

    Args:
        skill_name (str): name of a skill from ``list_skills``.
        context (str): optional description of the planned or failed attempt;
            when set, entries are reordered by relevance.
    """
    reg = _registry()
    if reg is None:
        return json.dumps({"error": "skill registry not bound"})
    s = reg.get(skill_name)
    if s is None:
        return json.dumps({"error": f"skill {skill_name!r} not found"})

    details = list(getattr(s, "anti_patterns_details", []) or [])
    if not details:
        return json.dumps({
            "skill": skill_name,
            "entries": [],
            "count": 0,
            "note": "no anti-patterns recorded for this skill",
        }, ensure_ascii=False)

    if context.strip():
        from searchos.skills.core.anti_patterns import (
            AntiPatternEntry,
            rank_by_context,
        )
        entries_typed = [
            AntiPatternEntry(
                name=d.get("name", ""),
                summary=d.get("summary", ""),
                what_failed=d.get("what_failed", ""),
                why=d.get("why", ""),
                instead=d.get("instead", ""),
                observed=int(d.get("observed", 1) or 1),
                last_seen=d.get("last_seen", ""),
                source=d.get("source", ""),
            )
            for d in details
        ]
        ranked = rank_by_context(entries_typed, context)
        details = [
            {
                "name": e.name,
                "summary": e.summary,
                "what_failed": e.what_failed,
                "why": e.why,
                "instead": e.instead,
                "observed": e.observed,
                "last_seen": e.last_seen,
                "source": e.source,
            }
            for e in ranked
        ]

    return json.dumps(
        {"skill": skill_name, "entries": details, "count": len(details)},
        ensure_ascii=False, indent=2,
    )
