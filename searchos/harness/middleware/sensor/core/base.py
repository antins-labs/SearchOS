"""Middleware protocol ABC: Sensor — the post-tool observation seam.

The Sensor layer's extension point: a plugin inspects each tool result and
returns control signals (e.g. ``force_stop``) or None.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any

from langchain.agents.middleware.types import AgentMiddleware

from searchos.harness.middleware.sensor.core.models import ControlState
from searchos.harness.middleware.utils.messages import extract_tool_name, is_blocked


class Sensor(ABC):
    """反馈控制：在工具执行后检查状态。"""

    trigger_on: str = "every_step"  # "every_step" | "checkpoint"

    @abstractmethod
    async def check(
        self,
        tool_name: str,
        tool_result: Any,
        tool_input: Any = None,
    ) -> dict[str, Any] | None:
        """Return control signals (e.g. force_stop) or None."""
        ...


class _SensorMiddleware(AgentMiddleware):
    def __init__(self, sensor: Sensor, control: ControlState) -> None:
        self.sensor = sensor
        self.control = control

    @property
    def name(self) -> str:
        return f"{type(self.sensor).__name__}Middleware"

    async def awrap_tool_call(self, request: Any, handler: Callable) -> Any:
        result = await handler(request)
        if is_blocked(result):
            return result
        signal = await self.sensor.check(
            extract_tool_name(request),
            result,
            tool_input=request.tool_call.get("args", {}),
        )
        if not signal:
            return result
        if signal.get("force_stop"):
            self.control.stop(signal.get("reason", "sensor_forced_stop"))
        if signal.get("hard_block_tools"):
            self.control.blocked_tools.update(signal["hard_block_tools"])
            self.control.reason = signal.get("reason", self.control.reason or "sensor_block")
        if signal.get("inject_message"):
            self.control.messages.append(signal["inject_message"])
        if signal.get("strategy_switch"):
            self.control.strategy_switch = True
        return result
