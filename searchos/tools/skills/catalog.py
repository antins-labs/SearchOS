"""技能发现、显式访问范围与技能包经验读取。"""

from __future__ import annotations

import json
from contextvars import ContextVar

from langchain_core.tools import tool

from searchos.skills.core.capabilities import read_capability_results

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


@tool(parse_docstring=True)
async def list_skills(category: str = "", availability: str = "", query: str = "", offset: int = 0, limit: int = 5) -> str:
    """Find skills for a task, source or capability. Returns names, descriptions, match reasons for
    ranked results, the match count and next_offset. Use load_skill to read instructions and limits
    before selecting a skill.

    An empty result can be followed by ordinary web retrieval. On a discovery error, retry or
    browse with an empty query.

    Args:
        category: access, strategy or orchestrator. Omit to browse access and strategy skills.
        availability: enabled or disabled. Omit to include the whole visible registry, which
            contains enabled skills at runtime.
        query: Natural-language need in any language, exact skill name, or source domain/URL (up to
            2000 characters). Omit to browse without ranking.
        offset: Zero-based starting index. Use next_offset for the next page.
        limit: Number of skills per page, 1–50 (default 5).
    """
    from searchos.config.settings import settings
    if not settings.enable_skills:
        return json.dumps({"skills": [], "count": 0, "note": "skill system disabled"})
    reg = _registry()
    if reg is None:
        return json.dumps({"skills": [], "count": 0, "error": "skill registry not bound"})
    if category and category not in {'access', 'strategy', 'orchestrator'}:
        return json.dumps({'skills': [], 'count': 0, 'error': 'invalid skill category'})
    if len(query) > 2000:
        return json.dumps({'skills': [], 'count': 0, 'error': 'Describe the current retrieval need in at most 2000 characters.'})
    candidates = []
    for s in reg.list_all():
        if not _skill_allowed(s):
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
        from searchos.skills.catalog.discovery import discover_skills
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
            **({'capability_results': results} if (results := read_capability_results(s)) else {}),
            **({'match_reason': matches[s.meta.name]} if s.meta.name in matches else {}),
        } for s in candidates]
    start, size = max(0, offset), min(50, max(1, limit))
    return json.dumps(
        {"skills": out[start:start + size], "count": len(out),
         "next_offset": start + size if start + size < len(out) else None},
        ensure_ascii=False,
    )


@tool(parse_docstring=True)
async def load_anti_patterns(skill_name: str, context: str = "") -> str:
    """Read a skill's recorded failures and suggested alternatives before retrying an approach.
    Returns the entries and their count.

    Args:
        skill_name: Exact skill name from list_skills.
        context: Optional description of the planned or failed attempt. Supplying it ranks entries
            by relevance.
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
