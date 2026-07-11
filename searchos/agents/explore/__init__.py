"""Explore agent (paper §Agent Roles) — pre-search information-landscape scout.

Dispatched before search begins so the orchestrator can map where data lives
and plan a strategy. No extraction middleware attaches: its only output is the
final briefing message (see ``agent.md``).
"""

from __future__ import annotations

AGENT_TYPE = "explore_agent"


def get_tools(skill_names: list[str] | None = None) -> list:
    """根据开关选择并发覆盖波次或旧版串行浏览工具。"""
    from searchos.config.settings import settings
    from searchos.tools.simple_browser import explore_web, get_simple_browser_tools

    if settings.enable_explore_batch:
        return [explore_web]
    return list(get_simple_browser_tools())
