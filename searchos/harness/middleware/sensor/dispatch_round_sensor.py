"""DispatchRoundSensor: hard-cap orchestrator dispatch rounds at the
harness layer.

``settings.orch_max_dispatches`` is the intended cap.
orchestrator_prompt renders it as "Max orchestrator dispatch rounds: N"
but that's soft — the LLM can and does ignore it, overshooting the cap
with extra rescue rounds that spawn more sub-agents and waste tokens.

This sensor counts ``dispatch_agent`` / ``dispatch_agents`` tool calls
on the orchestrator middleware. Each call = 1 round regardless of how
many agents ``dispatch_agents`` spawns — matches the "round" framing
in the prompt. On the max-th call, the sensor fires:
  - ``force_stop`` (prompt-level HARD STOP on next model turn)
  - ``hard_block_tools`` for dispatch_agent / dispatch_agents
    (handler-layer short-circuit for subsequent attempts)

Does NOT block ``check_agents`` (LLM still needs to collect results
from the dispatches that already ran) or ``synthesize_answer``
(the whole point is to push LLM there).

Explore is harness-prepended and runs before the orchestrator is built,
so it bypasses this sensor entirely — counter starts at 0 on the first
real orchestrator-side dispatch.
"""

from __future__ import annotations

import logging
from typing import Any

from searchos.harness.middleware.sensor.base import Sensor

logger = logging.getLogger(__name__)

_DISPATCH_TOOLS = {"enqueue_tasks"}


class DispatchRoundSensor(Sensor):
    """Orchestrator-only sensor that hard-blocks further dispatches
    once ``max_rounds`` have been consumed.

    State is per-instance; a fresh sensor is created per harness run,
    so the counter resets naturally between queries.
    """

    trigger_on: str = "every_step"

    def __init__(self, max_rounds: int) -> None:
        self._max = max_rounds
        self._count = 0

    async def check(
        self, tool_name: str, tool_result: Any, tool_input: Any = None,
    ) -> dict[str, Any] | None:
        if tool_name not in _DISPATCH_TOOLS:
            return None

        # max_rounds <= 0 means no limit.
        if self._max <= 0:
            return None

        self._count += 1

        if self._count >= self._max:
            logger.warning(
                "DispatchRoundSensor: %d dispatch rounds >= %d — "
                "hard-blocking dispatch_agent(s)",
                self._count, self._max,
            )
            return {
                "force_stop": True,
                "reason": f"dispatch_budget_exhausted_x{self._count}",
                "hard_block_tools": list(_DISPATCH_TOOLS),
            }
        return None
