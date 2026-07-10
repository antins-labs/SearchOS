"""Shared temporal-grounding policy for every runtime agent role."""

from __future__ import annotations

from typing import Literal

AgentRole = Literal["orchestrator", "explore_agent", "search_agent", "writer_agent"]

_ROLE_RULES: dict[AgentRole, str] = {
    "orchestrator": (
        "Before dispatch, derive a temporal contract: as-of cutoff, target period/range, "
        "and required freshness. Put it verbatim in every relevant task brief and in "
        "time-sensitive column_desc. Never send a bare 'latest' task."
    ),
    "explore_agent": (
        "Your briefing must state the interpreted time window, each key source's update "
        "cadence, and the freshest effective date you actually verified. Flag stale hubs."
    ),
    "search_agent": (
        "Make the target period explicit in queries. In your final report, state the "
        "value's effective period/as-of date and the page publication/update date when "
        "visible; a recent article can still report an old fact."
    ),
    "writer_agent": (
        "Keep every claim attached to its evidence period. Never merge mismatched periods "
        "under one 'current' label; state the as-of date, compare periods explicitly, or "
        "add a freshness caveat."
    ),
}


def render_temporal_grounding(current_date: str, role: AgentRole) -> str:
    """Render a compact, role-specific temporal contract for a system prompt."""
    return f"""\
# Temporal Grounding

Runtime as-of date: {current_date}. Treat it as a hard upper bound for completed real-world events unless the user explicitly asks for forecasts or plans.

- Resolve relative phrases (today, currently, latest, this year, last N years, recently) against this date before planning or searching. Prefer explicit ISO dates or named periods in tasks and answers.
- Classify the request as timeless, point-in-time, bounded period, trend, or current/latest. If the user supplies a cutoff, it overrides the runtime date and evidence after that cutoff cannot answer the question.
- Distinguish event/effective date, reporting period, page publication/update date, and retrieval date. They are not interchangeable.
- For current/latest facts, verify the value is effective for the requested as-of point; search with an explicit year/date and prefer the freshest authoritative source. A page merely being recently published is insufficient.
- Never present a future announcement, target, projection, scheduled event, or plan as completed fact. Label it with its future date and status.
- Never silently compare or combine values from different periods. Preserve the source's period and expose temporal uncertainty when freshness cannot be verified.

Role requirement: {_ROLE_RULES[role]}
"""


__all__ = ["AgentRole", "render_temporal_grounding"]
