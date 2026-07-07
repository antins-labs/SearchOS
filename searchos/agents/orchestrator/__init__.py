"""Orchestrator (paper §Agent Roles) — the Main Agent.

Assembles the orchestrator's tool bundle from the @tool surfaces in
``searchos.tools`` (schema editors + Frontier queue / scheduler). The spawn
lifecycle, scheduler, prompt, catalog, and post-mortem live in sibling modules.
"""

from __future__ import annotations


def get_orchestrator_tools() -> list:
    """Orchestrator tools: schema editors + Frontier queue + scheduler.

    Skill / browser tools belong to sub-agents only — exposing them here lets
    a confused orchestrator hop across them at budget exhaustion.
    """
    from searchos.tools.schema import get_schema_tools
    from searchos.tools.tasks import get_task_tools

    return [*get_schema_tools(), *get_task_tools()]
