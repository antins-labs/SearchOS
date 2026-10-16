"""Orchestrator (paper §Agent Roles) — the Main Agent.

Assembles the orchestrator's tool bundle from the @tool surfaces in
``searchos.tools`` (schema editors + Frontier queue / scheduler). The spawn
lifecycle, scheduler, prompt, catalog, and post-mortem live in sibling modules.
"""

from __future__ import annotations


def get_orchestrator_tools(*, source_mode: str = "") -> list:
    """Orchestrator tools: schema editors + Frontier queue + scheduler.

    Skill / browser tools belong to sub-agents only — exposing them here lets
    a confused orchestrator hop across them at budget exhaustion.
    """
    from searchos.tools.schema import (
        add_columns,
        add_entities,
        create_schema,
        edit_entities,
        inspect_table,
        remove_entities,
    )
    from searchos.tools.socm_read import list_frontier, read_evidence
    from searchos.tools.tasks import check_agents, enqueue_tasks, stop_task
    from searchos.tools.python_execution import python
    from searchos.tools.research_plan import set_research_plan

    # Extraction owns extraction, evidence binding and cell projection.
    return [
        set_research_plan,
        create_schema,
        add_columns,
        add_entities,
        remove_entities,
        edit_entities,
        inspect_table,
        python,
        enqueue_tasks,
        stop_task,
        check_agents,
        read_evidence,
        list_frontier,
    ]
