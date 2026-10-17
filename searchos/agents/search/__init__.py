"""Web Search agent (paper §Agent Roles) — solves one web search task.

Browser + skill tools only. Local-document retrieval belongs to the separate
``local_search_agent`` so web runs do not carry local tools or instructions.
"""

from __future__ import annotations

AGENT_TYPE = "search_agent"


def get_tools(skill_names: list[str] | None = None) -> list:
    """Browser + (when enabled) fixed skill discovery and exec tools."""
    from searchos.config.run_config import current_run_config
    from searchos.config.settings import settings
    from searchos.tools.simple_browser import get_simple_browser_tools

    tools = list(get_simple_browser_tools(
        include_read_visual=current_run_config().enable_web_image_read,
    ))
    if settings.enable_skills:
        from searchos.tools.skills import get_skill_tools

        tools.extend(get_skill_tools(skill_names))
    return tools
