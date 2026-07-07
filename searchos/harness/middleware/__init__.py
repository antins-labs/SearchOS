"""Middleware: three-layer stack — paper §3.

Fixed order (§3.4): Context → Sensor → Extraction.

- **Context** (``middleware.context``): per-agent context management — prompt
  assembly, SOCM snapshot injection, compression, skill injection. Read-only.
- **Sensor** (``middleware.sensor``): post-tool observation — budget, loops,
  writer-trigger, dispatch-round. Emits signals; read-only on SOCM (writes only
  anti-patterns + write-kind frontier tasks). The ``Sensor`` protocol, the
  budget tracker, and the ``HarnessMiddleware`` engine that drives them all
  live there.
- **Extraction** (``middleware.extraction``): sole writer of Evidence/Coverage.
  Runs last so Sensor signals can short-circuit before any SOCM mutation.
"""

from searchos.harness.middleware.sensor.base import Sensor
from searchos.harness.middleware.sensor.budget import BudgetState


def build_layered_stack(
    *,
    control: list | None = None,
    sensor: list | None = None,
    extraction: list | None = None,
) -> list:
    """Flatten pre-instantiated middleware (grouped by layer) into one ordered
    list: Context first, then Sensor, then Extraction.

    Prompts must exist before observation (Sensor needs a crystallized turn to
    score), and observation must precede mutation (a ``force_stop`` shouldn't
    race the Extraction write).
    """
    return [*(control or []), *(sensor or []), *(extraction or [])]


__all__ = ["Sensor", "BudgetState", "build_layered_stack"]
