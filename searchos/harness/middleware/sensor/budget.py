"""Multi-dimensional budget tracker for agent tool usage."""

from __future__ import annotations


class BudgetState:
    """Multi-dimensional budget tracker.

    Five dimensions feed ``consumption_ratio`` / ``exhausted``:
    - ``max_queries`` — count of search_* tool calls
    - ``max_opens`` — count of open() tool calls (0 = disabled)
    - ``max_finds`` — count of find() tool calls (0 = disabled)
    - ``max_iterations`` — orchestrator rounds
    - ``max_time_s`` — wall-clock seconds since first ``consume_query`` /
      first ``consumption_ratio`` read, whichever is earlier

    Wall-clock is load-bearing: without it, a sub-agent that does 1
    search + many page-read calls (none of which consume query budget)
    can spin indefinitely. The clock starts on first use rather than
    ``__init__`` because BudgetState is often constructed well before
    the agent actually runs.
    """

    def __init__(
        self,
        max_queries: int = 100,
        max_time_s: int = 0,
        max_iterations: int = 0,
        max_opens: int = 0,
        max_finds: int = 0,
    ) -> None:
        self.max_queries = max_queries
        self.max_time_s = max_time_s
        self.max_iterations = max_iterations
        self.max_opens = max_opens
        self.max_finds = max_finds
        self.consumed_queries = 0
        self.consumed_opens = 0
        self.consumed_finds = 0
        self.elapsed_s = 0.0
        self.current_iteration = 0
        self.evaluator_tokens = 0
        self._start_ts: float | None = None

    def _ensure_started(self) -> None:
        if self._start_ts is None:
            import time
            self._start_ts = time.time()

    def consume_query(self, n: int = 1) -> None:
        self._ensure_started()
        self.consumed_queries += n

    def consume_open(self, n: int = 1) -> None:
        self._ensure_started()
        self.consumed_opens += n

    def consume_find(self, n: int = 1) -> None:
        self._ensure_started()
        self.consumed_finds += n

    def consume_evaluator_tokens(self, n: int) -> None:
        self.evaluator_tokens += n

    @property
    def elapsed_s_live(self) -> float:
        """Seconds since the clock started (0.0 if never started)."""
        if self._start_ts is None:
            return 0.0
        import time
        return time.time() - self._start_ts

    @property
    def consumption_ratio(self) -> float:
        """Highest ratio across all dimensions.

        Side effect: reading this starts the wall-clock if it wasn't
        already started, ensuring time-based exhaustion works even for
        agents that do zero search_* calls but many open() calls.
        """
        self._ensure_started()
        ratios = []
        if self.max_queries > 0:
            ratios.append(self.consumed_queries / self.max_queries)
        if self.max_opens > 0:
            ratios.append(self.consumed_opens / self.max_opens)
        if self.max_finds > 0:
            ratios.append(self.consumed_finds / self.max_finds)
        if self.max_iterations > 0:
            ratios.append(self.current_iteration / self.max_iterations)
        if self.max_time_s > 0:
            ratios.append(self.elapsed_s_live / self.max_time_s)
        return max(ratios) if ratios else 0.0

    @property
    def exhausted(self) -> bool:
        return self.consumption_ratio >= 1.0

    @property
    def queries_exhausted(self) -> bool:
        return self.max_queries > 0 and self.consumed_queries >= self.max_queries

    @property
    def opens_exhausted(self) -> bool:
        return self.max_opens > 0 and self.consumed_opens >= self.max_opens

    @property
    def finds_exhausted(self) -> bool:
        return self.max_finds > 0 and self.consumed_finds >= self.max_finds

    @property
    def hard_exhausted(self) -> bool:
        """Wall-clock or iteration budget spent — global, no tool can help."""
        if self.max_iterations > 0 and self.current_iteration >= self.max_iterations:
            return True
        if self.max_time_s > 0 and self.elapsed_s_live >= self.max_time_s:
            return True
        return False

    @property
    def all_action_dims_exhausted(self) -> bool:
        """Every ENABLED per-tool dimension is spent (and at least one is
        enabled) — the agent has no budgeted action left."""
        dims = []
        if self.max_queries > 0:
            dims.append(self.queries_exhausted)
        if self.max_opens > 0:
            dims.append(self.opens_exhausted)
        if self.max_finds > 0:
            dims.append(self.finds_exhausted)
        return bool(dims) and all(dims)

    @property
    def fully_exhausted(self) -> bool:
        """Justifies a FULL stop: global dims spent, or no budgeted action
        remains."""
        return self.hard_exhausted or self.all_action_dims_exhausted

    @property
    def exhaustion_reason(self) -> str:
        if self.max_iterations > 0 and self.current_iteration >= self.max_iterations:
            return "iteration"
        if self.max_time_s > 0 and self.elapsed_s_live >= self.max_time_s:
            return "time"
        if self.all_action_dims_exhausted:
            return "all_tools"
        return ""

    def exhaustion_detail(self) -> str:
        """Human-readable one-line detail of the exhaustion state."""
        reason = self.exhaustion_reason
        if reason == "iteration":
            return f"round {self.current_iteration}/{self.max_iterations}"
        if reason == "time":
            return f"{self.elapsed_s_live:.0f}s/{self.max_time_s}s elapsed"
        if reason == "all_tools":
            parts = []
            if self.max_queries > 0:
                parts.append(f"search {self.consumed_queries}/{self.max_queries}")
            if self.max_opens > 0:
                parts.append(f"open {self.consumed_opens}/{self.max_opens}")
            if self.max_finds > 0:
                parts.append(f"find {self.consumed_finds}/{self.max_finds}")
            return ", ".join(parts) or "all tool budgets spent"
        return ""
