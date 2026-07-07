"""Search agent (paper §Agent Roles) — solves one search task, fills SOCM.

Browser + skill tools. Extraction middleware attaches at spawn time so its
open() findings flow into Evidence / Coverage.
"""

from __future__ import annotations

AGENT_TYPE = "search_agent"


def get_tools(skill_names: list[str] | None = None) -> list:
    """Browser + (when enabled) typed skill tools for the dispatched skills."""
    from searchos.tools.simple_browser import get_simple_browser_tools
    from searchos.config.settings import settings

    tools = list(get_simple_browser_tools())
    if settings.enable_skills:
        from searchos.tools.skill_catalog import get_skill_tools

        tools.extend(get_skill_tools(skill_names))
    return tools
