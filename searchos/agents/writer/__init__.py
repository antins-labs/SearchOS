"""Writer agent (paper §Agent Roles) — long-lived structured drafter.

Drafts the final report from settled SOCM material via outline / section
tools. See ``agent.md`` for the persona.
"""

from __future__ import annotations

AGENT_TYPE = "writer_agent"


def get_tools(skill_names: list[str] | None = None) -> list:
    """Outline + section drafting tools (read-only SOCM views included)."""
    from searchos.tools.writer import get_writer_tools

    return list(get_writer_tools())
