"""按来源与任务配置组装 Orchestrator 提示词。"""

from __future__ import annotations

from searchos.agents.date_context import render_temporal_grounding

from .prompts.evidence import render_evidence
from .prompts.research import render_research
from .prompts.sources import render_sources
from .prompts.tables import render_tables


def build_orchestrator_prompt(
    agent_catalog: str,
    skill_catalog: str,
    max_dispatches: int = 0,
    max_searches_per_agent: int = 8,
    max_skills_per_agent: int = 8,
    max_search_agents_per_session: int = 0,
    current_time: str = "",
    orch_toolset: str = "",
    enable_explore: bool = True,
    orchestrator_playbook: str = "",
    follow_up: bool = False,
    source_mode: str = "",
    local_sources: str = "",
    source_limitations: str = "",
    explore_on_start: bool = False,
    fixed_schema: bool = False,
    targeted_repair: bool = False,
) -> str:
    """公共职责各出现一次；仅注入当前配置可执行的工作指引。"""
    mode = source_mode or "web"
    explore = enable_explore and mode != "local" and not targeted_repair
    sections = [
        "You are the SearchOS Orchestrator. Coordinate research agents, assess evidence, "
        "and answer the user's question within the authorized scope and available resources.",
        render_temporal_grounding(current_time, "orchestrator"),
        render_sources(mode, local_sources=local_sources, limitations=source_limitations),
    ]
    limits = [
        f"Default retrieval actions per agent: {max_searches_per_agent}.",
        f"Dispatch rounds: {max_dispatches if max_dispatches > 0 else 'unlimited'}.",
        "Retrieval agents created per session: "
        f"{max_search_agents_per_session if max_search_agents_per_session > 0 else 'unlimited'}.",
        "The per-session creation budget spans dispatch rounds; simultaneous running slots "
        "are a separate limit. Runtime limits are authoritative.",
    ]
    if mode != "local":
        skill_limit = max_skills_per_agent if max_skills_per_agent > 0 else "unlimited"
        limits.append(f"Default per-agent budget for Exec batches that start an Access Skill: {skill_limit}.")
    sections.extend([
        "## Resources\n\n" + "\n".join(limits),
        "## Agents\n\n" + agent_catalog,
        orch_toolset,
    ])
    if mode != "local" and skill_catalog.strip():
        sections.append(
            "## Skills\n\n" + skill_catalog.strip() + "\n\n"
            "Search agents discover, load, and execute skills within their retrieval tasks. "
            "When the user specifies a platform or skill, include that requirement in the task "
            "brief and assign it directly to search_agent."
        )
    # 编排技能面向 Web 研究；修复任务使用选定单元格约束。
    if mode == "web" and not targeted_repair and orchestrator_playbook.strip():
        sections.append("## Research guidance\n\n" + orchestrator_playbook.strip())
    sections.extend([
        render_research(
            explore=explore,
            initial_explore=explore_on_start and not follow_up,
            repair=targeted_repair,
            fixed=fixed_schema,
            follow_up=follow_up,
            retrieval_agent="local_search_agent" if mode == "local" else "search_agent",
        ),
        render_tables(fixed=fixed_schema, repair=targeted_repair),
        render_evidence(repair=targeted_repair),
    ])
    return "\n\n".join(section.strip() for section in sections if section.strip()) + "\n"
