"""Sensor layer (paper §3.2) — post-tool observation + signal surface.

Plugins implement ``base.Sensor`` and return control signals (``force_stop`` /
``hint`` / writer-trigger). The engine that runs them (per-step / checkpoint)
is wired alongside the orchestrator runtime.
"""

from searchos.harness.middleware.sensor.core.base import Sensor
from searchos.harness.middleware.sensor.core.coverage_stall_sensor import CoverageStallSensor
from searchos.harness.middleware.sensor.core.dispatch_round_sensor import DispatchRoundSensor
from searchos.harness.middleware.sensor.core.loops import (
    EmptyResultSensor,
    QueryRepetitionSensor,
    ReadingReminderSensor,
    StateStallSensor,
)
from searchos.harness.middleware.sensor.core.writer_trigger_sensor import (
    WriterTriggerSensor,
    WriterTriggerSignal,
)

__all__ = [
    "Sensor",
    "CoverageStallSensor",
    "DispatchRoundSensor",
    "EmptyResultSensor",
    "QueryRepetitionSensor",
    "ReadingReminderSensor",
    "StateStallSensor",
    "WriterTriggerSensor",
    "WriterTriggerSignal",
]
