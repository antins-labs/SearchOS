"""独立装载的重复查询、阅读提醒和停滞检测。"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from typing import Any

from searchos.harness.middleware.sensor.core.base import Sensor
from searchos.harness.middleware.sensor.utils.outcomes import tool_outcome
from searchos.harness.middleware.sensor.utils.queries import normalize_query

SEARCH_TOOLS = frozenset(
    {"web_search", "tavily_search", "serper_search", "browser_navigate", "search"}
)
READING_TOOLS = frozenset({"open", "find", "local_open", "local_find", "read_visual"})
FILE_TOOLS = frozenset({"read_file", "write_file", "list_files", "ls", "edit_file"})


class QueryRepetitionSensor(Sensor):
    trigger_on = "every_step"

    def __init__(
        self,
        *,
        window: int = 5,
        repetitions: int = 3,
        escalation: int = 2,
        search_tools: frozenset[str] = SEARCH_TOOLS,
        on_warning: Callable[[str, str], None] | None = None,
        on_loop: Callable[[str], None] | None = None,
    ) -> None:
        self.queries: deque[str] = deque(maxlen=window)
        self.repetitions = repetitions
        self.escalation = escalation
        self.search_tools = search_tools
        self.on_warning = on_warning
        self.on_loop = on_loop
        self._last_warning = ""
        self._warnings = 0
        self._escalated = False

    async def check(self, tool_name: str, tool_result: Any, tool_input: Any = None):
        if tool_name not in self.search_tools or not isinstance(tool_input, dict):
            return None
        query = str(tool_input.get("query") or tool_input.get("q") or "")
        normalized = normalize_query(query)
        if not normalized:
            return None
        self.queries.append(normalized)
        repeats = self.queries.count(normalized)
        if repeats < self.repetitions or normalized == self._last_warning:
            return None
        self._last_warning = normalized
        self._warnings += 1
        if self._warnings >= self.escalation and not self._escalated:
            self._escalated = True
            if self.on_loop is not None:
                self.on_loop(query)
            return {"force_stop": False, "reason": "query_repetition_hard_loop"}
        if self.on_warning is not None:
            self.on_warning(normalized, f"query repeated {repeats} times")
        return {
            "reason": "query_repetition",
            "inject_message": (
                f"[Harness WARNING] Query {query[:120]!r} repeated {repeats} times. "
                "Switch keywords, language or domain; read an existing source, "
                "or record an unresolved target."
            ),
        }


class ReadingReminderSensor(Sensor):
    trigger_on = "every_step"

    def __init__(
        self,
        *,
        threshold: int = 3,
        search_tools: frozenset[str] = SEARCH_TOOLS,
        reading_tools: frozenset[str] = READING_TOOLS,
    ) -> None:
        self.threshold = threshold
        self.search_tools = search_tools
        self.reading_tools = reading_tools
        self._searches = 0

    async def check(self, tool_name: str, tool_result: Any, tool_input: Any = None):
        if tool_name in self.search_tools:
            self._searches += 1
        elif tool_name in self.reading_tools:
            outcome = tool_outcome(tool_name, tool_result, tool_input)
            if not outcome.failed and not outcome.empty:
                self._searches = 0
        if self._searches < self.threshold:
            return None
        self._searches = 0
        return {
            "reason": "bare_search_without_progress",
            "inject_message": (
                f"[Harness WARNING] {self.threshold} searches without reading. "
                "Open the most relevant original source before issuing another query."
            ),
        }


class EmptyResultSensor(Sensor):
    trigger_on = "every_step"

    def __init__(
        self,
        *,
        threshold: int = 5,
        ignored_tools: frozenset[str] = FILE_TOOLS,
        on_warning: Callable[[str, str], None] | None = None,
    ) -> None:
        self.threshold = threshold
        self.ignored_tools = ignored_tools
        self.on_warning = on_warning
        self._empty = 0

    async def check(self, tool_name: str, tool_result: Any, tool_input: Any = None):
        if tool_name in self.ignored_tools:
            return None
        outcome = tool_outcome(tool_name, tool_result, tool_input)
        self._empty = self._empty + 1 if outcome.failed or outcome.empty else 0
        if self._empty < self.threshold:
            return None
        self._empty = 0
        if self.on_warning is not None:
            self.on_warning(
                f"no-progress:{tool_name}", f"{self.threshold} empty/error tool results"
            )
        return {
            "strategy_switch": True,
            "reason": f"search_loop_detected_after_{self.threshold}_steps",
        }


class StateStallSensor(Sensor):
    trigger_on = "every_step"

    def __init__(
        self,
        snapshot: Callable[[], tuple[float, int, int]],
        *,
        threshold: int = 6,
        on_stall: Callable[[str], None] | None = None,
    ) -> None:
        self.snapshot = snapshot
        self.threshold = threshold
        self.on_stall = on_stall
        self._previous: tuple[float, int] | None = None
        self._stalled = 0
        self._fired = False

    async def check(self, tool_name: str, tool_result: Any, tool_input: Any = None):
        coverage, evidence, pending = self.snapshot()
        current = (coverage, evidence)
        self._stalled = self._stalled + 1 if current == self._previous and pending == 0 else 0
        self._previous = current
        if self._fired or self._stalled < self.threshold:
            return None
        self._fired = True
        if self.on_stall is not None:
            self.on_stall(
                f"state-stall:{tool_name} (no new evidence across {self.threshold} steps)"
            )
        return {"force_stop": False, "reason": "state_delta_stall"}
