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
    max_execs_per_agent: int = 8,
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
    initial_planning_effort: int = 2,
) -> str:
    """公共职责各出现一次；仅注入当前配置可执行的工作指引。"""
    mode = source_mode or "web"
    explore = enable_explore and mode != "local" and not targeted_repair
    sections = [
        """You are the SearchOS Orchestrator. Coordinate research agents, assess evidence, and answer the user's question within the authorized scope and available resources.""",
        render_temporal_grounding(current_time, "orchestrator"),
        render_sources(mode, local_sources=local_sources, limitations=source_limitations),
    ]
    planning = {
        1: "Resolve only the choices needed for the first useful tool call, then act immediately.",
        2: "Briefly identify the scope, first sources, and independent tasks, then start gathering evidence.",
        3: "Assess meaningful source alternatives and task dependencies before choosing the first actions.",
        4: "Work through consequential ambiguities, source alternatives, and dependencies before acting; stop planning once the first actions are well supported.",
    }[initial_planning_effort]
    sections.append(f"""## Initial planning

Planning effort: {initial_planning_effort}/4. {planning}
Apply this depth to the initial decision only. Preserve the user's full requested scope at every effort level. Use retrieved evidence and live state to refine subsequent work; avoid precomputing hypothetical findings or repeating the operating instructions.""")
    limits = [
        f"""Default retrieval actions per agent: {max_searches_per_agent}.""",
        f"""Dispatch rounds: {max_dispatches if max_dispatches > 0 else 'unlimited'}.""",
        f"""Retrieval agents created per session: {max_search_agents_per_session if max_search_agents_per_session > 0 else 'unlimited'}.""",
        """The per-session creation budget spans dispatch rounds; simultaneous running slots are a separate limit. Runtime limits are authoritative.""",
    ]
    if mode != "local":
        exec_limit = max_execs_per_agent if max_execs_per_agent > 0 else "unlimited"
        limits.append(f"""Default per-agent Exec call budget: {exec_limit}.""")
    resources = "\n".join(limits)
    sections.extend([
        f"""## Resources

{resources}""",
        f"""## Agents

{agent_catalog}""",
        orch_toolset,
    ])
    if mode != "local" and skill_catalog.strip():
        sections.append(
            f"""## Skills

{skill_catalog.strip()}

Search agents discover, load, and execute skills within their retrieval tasks. When the user specifies a platform or skill, include that requirement in the task brief and assign it directly to search_agent."""
        )
    # 编排技能面向 Web 研究；修复任务使用选定单元格约束。
    if mode == "web" and not targeted_repair and orchestrator_playbook.strip():
        sections.append(f"""## Research guidance

{orchestrator_playbook.strip()}""")
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
