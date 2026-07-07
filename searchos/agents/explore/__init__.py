"""Explore agent (paper §Agent Roles) — pre-search information-landscape scout.

Dispatched before search begins so the orchestrator can map where data lives
and plan a strategy. No extraction middleware attaches: its only output is the
final briefing message (see ``agent.md``).
"""

from __future__ import annotations

AGENT_TYPE = "explore_agent"


def get_tools(skill_names: list[str] | None = None) -> list:
    """Browse-only toolset — explore reads pages, writes no SOCM."""
    from searchos.tools.simple_browser import get_simple_browser_tools

    return list(get_simple_browser_tools())
