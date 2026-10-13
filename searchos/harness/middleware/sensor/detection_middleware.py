"""直接装载的查询重复、阅读提醒、空结果与状态停滞检测。"""

from __future__ import annotations

from typing import Any

from searchos.harness.middleware.models import TaskContext
from searchos.harness.middleware.sensor.core.base import _SensorMiddleware
from searchos.harness.middleware.sensor.core.loops import (
    EmptyResultSensor,
    QueryRepetitionSensor,
    ReadingReminderSensor,
    StateStallSensor,
)
from searchos.harness.middleware.sensor.core.models import ControlState
from searchos.harness.middleware.sensor.utils.progress import task_progress
from searchos.harness.middleware.sensor.utils.queries import normalize_query


class _DetectionRecords:
    """检测组件内部使用的状态记录；调用方无需组装回调。"""

    def __init__(self, workspace: Any, task: TaskContext) -> None:
        self.workspace = workspace
        self.task = task

    def warn(self, signature: str, reason: str) -> None:
        if self.workspace is None:
            return
        from searchos.socm import AntiPatternKind
        from searchos.socm.strategy import record_strategy_pattern

        record_strategy_pattern(
            self.workspace,
            kind=AntiPatternKind.QUERY,
            signature=signature,
            reason=reason,
            created_by="sensor",
        )

    def loop(self, query: str) -> None:
        if self.workspace is None:
            return
        from searchos.socm import AntiPatternKind, StrategyPattern

        def update(state):
            agent_id = self.task.agent_id
            state.agent_status[agent_id] = "looped"
            dead_ends = state.agent_dead_ends.setdefault(agent_id, [])
            if query[:240] not in dead_ends:
                dead_ends.append(query[:240])
            state.strategy_log.record(
                StrategyPattern(
                    kind=AntiPatternKind.QUERY,
                    signature=normalize_query(query),
                    reason=f"research stalled (agent {agent_id})",
                    created_by="sensor",
                )
            )
            return state

        self.workspace.atomic_update_state(update)


class QueryRepetitionMiddleware(_SensorMiddleware):
    def __init__(
        self,
        control: ControlState,
        *,
        workspace: Any = None,
        task: TaskContext = TaskContext(),
        window: int = 5,
        repetitions: int = 3,
        escalation: int = 2,
    ) -> None:
        records = _DetectionRecords(workspace, task)
        super().__init__(
            QueryRepetitionSensor(
                window=window,
                repetitions=repetitions,
                escalation=escalation,
                on_warning=records.warn,
                on_loop=records.loop,
            ),
            control,
        )

    name = "QueryRepetitionMiddleware"


class ReadingReminderMiddleware(_SensorMiddleware):
    def __init__(self, control: ControlState, *, threshold: int = 3) -> None:
        super().__init__(ReadingReminderSensor(threshold=threshold), control)

    name = "ReadingReminderMiddleware"


class EmptyResultMiddleware(_SensorMiddleware):
    def __init__(
        self,
        control: ControlState,
        *,
        workspace: Any = None,
        task: TaskContext = TaskContext(),
        threshold: int = 5,
    ) -> None:
        records = _DetectionRecords(workspace, task)
        super().__init__(EmptyResultSensor(threshold=threshold, on_warning=records.warn), control)

    name = "EmptyResultMiddleware"


class StateStallMiddleware(_SensorMiddleware):
    def __init__(
        self,
        workspace: Any,
        *,
        control: ControlState,
        task: TaskContext,
        threshold: int = 6,
    ) -> None:
        self.workspace = workspace
        self.task = task
        records = _DetectionRecords(workspace, task)
        super().__init__(
            StateStallSensor(self._snapshot, threshold=threshold, on_stall=records.loop),
            control,
        )

    name = "StateStallMiddleware"

    def _snapshot(self) -> tuple[frozenset, int, int]:
        progress = task_progress(self.workspace, self.task)
        if progress is None:
            return (frozenset(), 0, 1)
        return (progress, 0, getattr(self.workspace, "extraction_pending_total", 0))


class DispatchRoundMiddleware(_SensorMiddleware):
    def __init__(self, control: ControlState, *, max_rounds: int) -> None:
        from searchos.harness.middleware.sensor.core.dispatch_round_sensor import (
            DispatchRoundSensor,
        )

        super().__init__(DispatchRoundSensor(max_rounds=max_rounds), control)

    name = "DispatchRoundMiddleware"


class CoverageStallMiddleware(_SensorMiddleware):
    def __init__(
        self,
        workspace: Any,
        *,
        control: ControlState,
        agent_graphs: Any,
        max_stalled_rounds: int = 3,
    ) -> None:
        from searchos.harness.middleware.sensor.core.coverage_stall_sensor import (
            CoverageStallSensor,
        )

        self.agent_graphs = agent_graphs
        super().__init__(
            CoverageStallSensor(
                workspace,
                max_stalled_rounds=max_stalled_rounds,
                source_progress=self._source_progress,
            ),
            control,
        )

    name = "CoverageStallMiddleware"

    def _source_progress(self) -> set[str]:
        return {
            key for info in self.agent_graphs.values() for key in info.get("source_progress", ())
        }
