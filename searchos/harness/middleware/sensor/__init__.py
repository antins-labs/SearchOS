"""Sensor layer (paper §3.2) — post-tool observation + signal surface.

Plugins implement ``base.Sensor`` and return control signals (``force_stop`` /
``hint`` / writer-trigger). The engine that runs them (per-step / checkpoint)
is wired alongside the orchestrator runtime.
"""

from searchos.harness.middleware.sensor.budget import BudgetState
from searchos.harness.middleware.sensor.base import Sensor
from searchos.harness.middleware.sensor.dispatch_round_sensor import DispatchRoundSensor
from searchos.harness.middleware.sensor.loop_sensor import LoopSensorImpl
from searchos.harness.middleware.sensor.writer_trigger_sensor import (
    WriterTriggerSensor,
    WriterTriggerSignal,
)

__all__ = [
    "BudgetState",
    "Sensor",
    "DispatchRoundSensor",
    "LoopSensorImpl",
    "WriterTriggerSensor",
    "WriterTriggerSignal",
]
