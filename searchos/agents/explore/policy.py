"""Explore 只限制波次上限，结束时机由目标完成情况决定。"""

from collections.abc import Callable
from typing import Any

from searchos.harness.middleware.sensor.core.models import ControlState
from searchos.harness.middleware.utils.messages import (
    blocked_result,
    call_with_context,
    extract_tool_name,
)


class ExplorePolicy:
    def __init__(self, *, max_waves: int, control: ControlState) -> None:
        if max_waves < 1:
            raise ValueError("max_waves must be positive")
        self.max_waves = max_waves
        self.control = control
        self.waves_used = 0

    async def call_tool(self, request: Any, handler: Callable) -> Any:
        if extract_tool_name(request) == "explore_web":
            if self.waves_used >= self.max_waves:
                return blocked_result(
                    request,
                    "[Harness EXPLORE_MAX_WAVES] Exploration wave budget exhausted. "
                    "Return the task's requested result and identify remaining gaps.",
                )
            # 在 await 前预留次数，避免同轮并发调用突破上限；失败也消耗尝试次数。
            self.waves_used += 1
        return await handler(request)

    async def call_model(self, request: Any, handler: Callable) -> Any:
        if self.control.stopped:
            return await handler(request)
        remaining = self.max_waves - self.waves_used
        if remaining:
            guidance = (
                f"[Harness EXPLORE_BUDGET] At most {remaining} explore_web wave(s) remain. "
                "There is no minimum wave count. Return the requested result as soon as the "
                "assigned uncertainty is resolved. Continue only for a concrete remaining gap."
            )
        else:
            guidance = (
                "[Harness EXPLORE_MAX_WAVES] No exploration waves remain. "
                "Return the supported briefing and identify unresolved uncertainty; "
                "do not call explore_web again."
            )
        return await call_with_context(
            request, handler, content=guidance, kind="explore_budget",
        )
