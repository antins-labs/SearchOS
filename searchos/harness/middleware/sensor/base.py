"""Middleware protocol ABC: Sensor — the post-tool observation seam.

The Sensor layer's extension point: a plugin inspects each tool result and
returns control signals (e.g. ``force_stop``) or None.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


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
