"""WriterTriggerSensor — passive writer spawn trigger.

Fires once per stage in ``COVERAGE_STAGES`` as ``coverage_score`` crosses
it. Orchestrator-explicit writer spawns are *not* handled here — those are
plain writer dispatches; the sensor is the passive path only.

The sensor is **stateful**: it remembers which stages have already fired,
so subsequent calls don't re-fire the same trigger. Own a single instance
for the session (e.g. on the Scheduler).

The sensor only reports; the caller (``maybe_spawn_writer``) consults the
signal and decides whether to enqueue a ``kind=write`` task + spawn.

Column-only schemas (declared with ``primary_key`` and 0 pre-listed
entities) never fire here: cells get autopromoted as evidence flows in, so
``filled / total`` starts near 1.0 and would burn every stage on the very
first tick. Column-only sessions rely on explicit orchestrator spawns.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# Single-stage trigger. Earlier this was four stages (0.2/0.4/0.6/0.8),
# which woke the writer up to 4× per session at 70-150s wall-time overhead
# per fire; one mid-run fire gives the writer a full-enough picture to
# produce a single final draft.
COVERAGE_STAGES: tuple[float, ...] = (0.5,)


@dataclass(frozen=True)
class WriterTriggerSignal:
    fire: bool
    trigger: str        # "" | "coverage_stage_<N>"
    reason: str         # short human-readable
    coverage: float
    filled_cells: int
    total_cells: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "fire": self.fire,
            "trigger": self.trigger,
            "reason": self.reason,
            "coverage": self.coverage,
            "filled_cells": self.filled_cells,
            "total_cells": self.total_cells,
        }


@dataclass
class WriterTriggerSensor:
    """Stateful evaluator — retains the fired-stages set across calls.

    Column-only mode never fires (see module docstring).
    """

    stages: tuple[float, ...] = COVERAGE_STAGES

    # Internal state
    _stages_fired: set[float] = field(default_factory=set)

    def evaluate(self, state: Any, **_: Any) -> WriterTriggerSignal:
        cmap = state.coverage_map
        cov = getattr(cmap, "coverage_score", 0.0)
        filled = getattr(cmap, "filled_cells", 0)
        total = getattr(cmap, "total_cells", 0)

        schema = getattr(cmap, "table_schema", None)
        column_only = bool(getattr(schema, "is_column_only", False))

        # Stage track — only meaningful in entity-mode. In column-only
        # mode, total grows via autopromote and filled/total often
        # starts near 1.0, which would burn all stages in one tick.
        if column_only:
            crossed: list[float] = []
        else:
            crossed = sorted(s for s in self.stages if cov >= s and s not in self._stages_fired)
        if crossed:
            top = crossed[-1]
            for s in crossed:
                self._stages_fired.add(s)
            return WriterTriggerSignal(
                fire=True,
                trigger=f"coverage_stage_{int(top * 100)}",
                reason=f"coverage {cov:.0%} crossed stage {top:.0%}",
                coverage=cov, filled_cells=filled, total_cells=total,
            )

        return WriterTriggerSignal(
            fire=False, trigger="", reason="no threshold crossed",
            coverage=cov, filled_cells=filled, total_cells=total,
        )
