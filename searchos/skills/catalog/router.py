"""Query-driven top-k pre-filter for the access-skill catalog.

The access library has grown to hundreds of (mostly site-specific) skills.
Injecting all of them into the orchestrator prompt every turn is wasteful and
noisy. This module runs a one-shot LLM router (role ``skill_router``, bound to
the main model) that scores the access skills against the user's query and
returns the top-k most relevant names. The orchestrator then sees only those;
the rest stay discoverable at runtime via ``list_skills`` / ``load_skill``.

Strategy skills are NOT routed here — they are methodology, small in number,
and kept whole by the catalog. This selector only narrows the access layer.

Fail-open by design: any error (no model, parse failure, empty result) returns
``None`` so the caller falls back to the full catalog. A broken router must
never break a run.
"""

from __future__ import annotations

import logging

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from searchos.skills.core.models import Skill, SkillCategory, SkillStatus
from searchos.skills.catalog.registry import SkillRegistry
from searchos.util.json_extract import extract_json_object

logger = logging.getLogger(__name__)


_SYSTEM = """You are a skill selector for a web-research agent.

You are given the user's research task and a numbered catalog of ACCESS skills.
Each access skill is a tool for reaching a specific data source — many are
tied to one website or domain (e.g. a particular stats portal, wiki, store, or
API), others are generic capabilities (e.g. scraping dynamic pages, extracting
academic papers, querying structured databases).

Pick the skills most likely to help accomplish THIS task, up to {top_k}:
- Include a site/domain-specific skill when the task plausibly needs that
  domain, entity, region, or language — even if the site is not named verbatim.
- Always keep broadly-useful generic capability skills.
- When unsure whether a skill helps, leave it out — the agent can still
  discover it at runtime. Precision over recall.

Return ONLY a JSON object, no prose:
{{"skills": ["exact_name_1", "exact_name_2", ...]}}
Use the exact names from the catalog. Return fewer than {top_k} if fewer are
relevant. Never invent names."""


def _selectable_access(registry: SkillRegistry) -> list[Skill]:
    """Access skills the catalog would otherwise surface (non-deprecated)."""
    return [
        s
        for s in registry.list_by_category(SkillCategory.ACCESS)
        if s.meta.status != SkillStatus.DEPRECATED
    ]


def _render_catalog(skills: list[Skill]) -> str:
    lines = []
    for i, s in enumerate(sorted(skills, key=lambda s: s.meta.name), 1):
        desc = (s.meta.description or s.meta.trigger or "").replace("\n", " ")[:120]
        lines.append(f"{i}. {s.meta.name}: {desc}")
    return "\n".join(lines)


async def select_access_skills(
    query: str,
    registry: SkillRegistry,
    *,
    top_k: int,
    model: BaseChatModel | None = None,
) -> set[str] | None:
    """Return the names of the top-k query-relevant access skills.

    ``None`` means "do not filter" — returned when there is nothing to gain
    (access count already <= top_k) or on any failure (fail-open).
    """
    candidates = _selectable_access(registry)
    if len(candidates) <= top_k:
        return None  # nothing to trim — keep the whole catalog

    valid = {s.meta.name for s in candidates}

    if model is None:
        from searchos.config.models import get_model_for
        try:
            model = get_model_for("skill_router")
        except Exception as exc:  # misconfigured role/key — don't kill the run
            logger.warning("skill_router model unavailable, keeping full catalog: %s", exc)
            return None

    messages = [
        SystemMessage(content=_SYSTEM.format(top_k=top_k)),
        HumanMessage(content=f"TASK:\n{query}\n\nACCESS SKILLS:\n{_render_catalog(candidates)}"),
    ]

    try:
        resp = await model.ainvoke(messages)
        obj = extract_json_object(getattr(resp, "content", "") or "")
    except Exception as exc:
        logger.warning("skill_router call failed, keeping full catalog: %s", exc)
        return None

    if not obj or not isinstance(obj.get("skills"), list):
        logger.warning("skill_router returned no usable selection, keeping full catalog")
        return None

    picked = {str(n) for n in obj["skills"] if str(n) in valid}
    if not picked:
        logger.warning("skill_router picked no valid names, keeping full catalog")
        return None

    logger.info(
        "skill_router: %d/%d access skills selected for query", len(picked), len(candidates)
    )
    return picked


__all__ = ["select_access_skills"]


# --- Orchestrator-layer playbook rendering -----------------------------------
# ``layer=orchestrator`` skills are injected directly (no router LLM call) into
# the orchestrator system prompt as a playbook block — distinct from the
# ``# Skills`` catalog (the *sub-agent* skill list).


def render_playbook(skills: list["Skill"]) -> str:
    """Render the given skill bodies as a single markdown block.

    Returns empty string when ``skills`` is empty so the caller can drop the
    section header in the prompt.
    """
    if not skills:
        return ""
    parts = []
    for s in skills:
        body = (s.body or "").strip()
        if not body:
            continue
        parts.append(f"## {s.meta.name}\n{body}")
    return "\n\n".join(parts)
