"""Shared effort presets — budget-knob bundles applied to the settings singleton.

Consumed by both the TUI (``/effort``) and the web API (``PUT /api/settings/effort``
and per-run overrides). Each level bundles the budget knobs that the harness
reads live from the global ``settings`` singleton at run time, so applying a
level just mutates ``settings.*`` and takes effect on the next run. ``medium``
mirrors the shipped defaults; ``max`` pushes every knob to its deep-dig ceiling.
"""

from __future__ import annotations

EFFORT_KEYS: tuple[str, ...] = (
    "orch_max_iterations",
    "max_parallel_agents",
    "max_searches_per_sub_agent",
    "max_searches_per_sub_agent_ceiling",
    "max_finds_per_sub_agent",
    "default_max_time_s",
    "skill_router_top_k",
)

EFFORT_LEVELS: dict[str, dict[str, int]] = {
    "low": {
        "orch_max_iterations": 25, "max_parallel_agents": 8,
        "max_searches_per_sub_agent": 10, "max_searches_per_sub_agent_ceiling": 20,
        "max_finds_per_sub_agent": 10, "default_max_time_s": 600,
        "skill_router_top_k": 20,
    },
    "medium": {
        "orch_max_iterations": 50, "max_parallel_agents": 8,
        "max_searches_per_sub_agent": 20, "max_searches_per_sub_agent_ceiling": 40,
        "max_finds_per_sub_agent": 20, "default_max_time_s": 1800,
        "skill_router_top_k": 40,
    },
    "high": {
        "orch_max_iterations": 100, "max_parallel_agents": 8,
        "max_searches_per_sub_agent": 35, "max_searches_per_sub_agent_ceiling": 60,
        "max_finds_per_sub_agent": 35, "default_max_time_s": 3600,
        "skill_router_top_k": 60,
    },
    "max": {
        "orch_max_iterations": 150, "max_parallel_agents": 8,
        "max_searches_per_sub_agent": 50, "max_searches_per_sub_agent_ceiling": 80,
        "max_finds_per_sub_agent": 50, "default_max_time_s": 7200,
        "skill_router_top_k": 80,
    },
}


def apply_effort(level: str, overrides: dict[str, int] | None = None) -> dict[str, int]:
    """Apply an effort level (plus optional per-knob overrides) to ``settings``.

    Returns the resolved knob dict actually applied. Raises ``KeyError`` for an
    unknown level and ``ValueError`` for override keys outside ``EFFORT_KEYS``.
    """
    from searchos.config.settings import settings

    knobs = dict(EFFORT_LEVELS[level])
    if overrides:
        bad = set(overrides) - set(EFFORT_KEYS)
        if bad:
            raise ValueError(f"Unknown effort knobs: {sorted(bad)}")
        knobs.update(overrides)
    for key, val in knobs.items():
        if hasattr(settings, key):
            setattr(settings, key, val)
    return knobs
