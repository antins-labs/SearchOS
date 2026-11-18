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
    from searchos.tools.exec import exec_code
    from searchos.tools.schema import (
        add_columns,
        add_entities,
        create_schema,
        edit_entities,
        read_table,
        remove_entities,
    )
    from searchos.tools.socm_read import list_frontier, read_evidence
    from searchos.tools.tasks import check_agents, enqueue_tasks, stop_task

    # Extraction owns extraction, evidence binding and cell projection.
    return [
        create_schema,
        add_columns,
        add_entities,
        remove_entities,
        edit_entities,
        read_table,
        exec_code,
        enqueue_tasks,
        check_agents,
        stop_task,
        read_evidence,
        list_frontier,
    ]
