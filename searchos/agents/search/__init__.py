"""Web Search Agent：装配浏览器、技能和通用执行工具。"""

from __future__ import annotations

AGENT_TYPE = "search_agent"


def get_tools(skill_names: list[str] | None = None) -> list:
    """保留原工具入口，并接入通用 exec。"""
    from searchos.config.run_config import current_run_config
    from searchos.config.settings import settings
    from searchos.tools.simple_browser import get_simple_browser_tools
    from searchos.tools.exec import exec_code

    tools = list(get_simple_browser_tools(
        include_read_visual=current_run_config().enable_web_image_read,
    ))
    if settings.enable_skills:
        from searchos.tools.skills import get_skill_tools
        tools.extend(get_skill_tools(skill_names))
    tools.append(exec_code)
    return tools
