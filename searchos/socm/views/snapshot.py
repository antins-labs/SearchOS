"""SearchStateSnapshot: one-shot aggregation of SearchState for SOCM views.

A read-only denormalization of the persisted state (coverage cells reshaped
into table→row→cell, plus Frontier status counts). Build once via
``SearchStateSnapshot.from_state(state)``, then pass to any ``views.render_*``
function — avoids repeated load_state() and duplicated cell-iteration.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from searchos.socm.state import SearchState


@dataclass
class CellInfo:
    attr: str
    status: str          # missing | filled | uncertain | hard_cell
    display_hint: str
    evidence_count: int
    best_alignment: str  # full | partial | loose | ""
    has_conflict: bool
    conflict_status: str = "clear"


@dataclass
class RowStatus:
    entity: str
    cells: list[CellInfo]

    @property
    def filled_cols(self) -> list[str]:
        return [c.attr for c in self.cells if c.status == "filled"]

    @property
    def missing_cols(self) -> list[str]:
        return [c.attr for c in self.cells if c.status not in ("filled", "hard_cell")]

    @property
    def evidence_count(self) -> int:
        return sum(c.evidence_count for c in self.cells)

    @property
    def is_complete(self) -> bool:
        return len(self.missing_cols) == 0

    @property
    def is_empty(self) -> bool:
        return all(c.evidence_count == 0 for c in self.cells)


@dataclass
class TableSnapshot:
    table_id: str
    label: str
    primary_key: list[str]
    data_columns: list[str]
    is_open_set: bool
    rows: list[RowStatus]
    column_descriptions: dict[str, str] = field(default_factory=dict)

    @property
    def is_empty(self) -> bool:
        return len(self.rows) == 0

    @property
    def complete_rows(self) -> list[RowStatus]:
        return [r for r in self.rows if r.is_complete]

    @property
    def partial_rows(self) -> list[RowStatus]:
        return [r for r in self.rows if not r.is_complete and not r.is_empty]

    @property
    def empty_rows(self) -> list[RowStatus]:
        return [r for r in self.rows if r.is_empty and not r.is_complete]


@dataclass
class RunningTaskSnap:
    """One in-flight (RUNNING) Frontier task, projected for orchestrator view.

    Lets the orchestrator see *what* each running sub-agent is working on
    (table / target cells / task text) instead of a bare RUNNING count, so it
    stops re-dispatching work already in flight.
    """
    agent_id: str        # assigned_agent_id, or "unassigned"
    table_id: str
    targets: list[str]   # first few target_cells, for cell-level alignment
    text: str            # short task text (question or task_prompt)


@dataclass
class FrontierSnapshot:
    by_status: dict[str, int] = field(default_factory=dict)
    open_by_kind: dict[str, int] = field(default_factory=dict)
    running_tasks: list[RunningTaskSnap] = field(default_factory=list)


@dataclass
class SearchStateSnapshot:
    tables: list[TableSnapshot]
    frontier: FrontierSnapshot
    total_rows: int
    rows_with_gaps: int
    research_mode: str = "table"
    task_evidence: list[dict] = field(default_factory=list)

    @staticmethod
    def from_state(state: "SearchState") -> "SearchStateSnapshot":
        cmap = state.coverage_map
        frontier = state.frontier

        tables: list[TableSnapshot] = []
        total_rows = 0
        rows_with_gaps = 0

        for tid, ts in cmap.tables.items():
            pk_attrs = set(ts.primary_key or [])
            data_cols = [a for a in ts.attributes if a not in pk_attrs]

            rows: list[RowStatus] = []
            for ent in sorted(ts.entities):
                cells: list[CellInfo] = []
                for attr in data_cols:
                    key = cmap.cell_key(tid, ent, attr)
                    cell = cmap.cells.get(key)
                    if cell is None:
                        cells.append(CellInfo(
                            attr=attr, status="missing", display_hint="",
                            evidence_count=0, best_alignment="", has_conflict=False,
                        ))
                    else:
                        cells.append(CellInfo(
                            attr=attr,
                            status=cell.status.value if cell.status else "missing",
                            display_hint=cell.display_hint or "",
                            evidence_count=len(cell.supporting_evidence_ids),
                            best_alignment=cell.best_alignment or "",
                            has_conflict=cell.has_conflict,
                            conflict_status=cell.conflict_status,
                        ))
                row = RowStatus(entity=ent, cells=cells)
                rows.append(row)
                if not row.is_complete:
                    rows_with_gaps += 1

            total_rows += len(rows)
            tables.append(TableSnapshot(
                table_id=tid,
                label=ts.table_label or tid,
                primary_key=list(ts.primary_key or []),
                data_columns=data_cols,
                is_open_set=ts.is_column_only,
                rows=rows,
                column_descriptions={a: f"{d.type}: {d.desc}" for a, d in ts.column_desc.items()},
            ))

        by_status: Counter[str] = Counter()
        open_by_kind: Counter[str] = Counter()
        running_tasks: list[RunningTaskSnap] = []
        for q in (frontier.questions if frontier else []):
            s = q.status.value if q.status else ""
            by_status[s] += 1
            if s == "pending":
                open_by_kind[q.kind or "search"] += 1
            elif s == "running":
                running_tasks.append(RunningTaskSnap(
                    agent_id=q.assigned_agent_id or "unassigned",
                    table_id=q.table_id or "",
                    targets=list(q.target_cells or [])[:4],
                    text=(q.question or q.task_prompt or "")[:80],
                ))

        from searchos.socm.coverage import answer_evidence
        active_ids = {node.id for node in answer_evidence(state)}
        task_evidence = [{
            "task_id": task.id, "question": task.question, "status": task.status.value,
            "agent_type": task.agent_type, "result_mode": task.result_mode,
            "evidence_count": len({binding.evidence_id
                for binding in state.evidence_graph.task_bindings
                if binding.task_id == task.id and binding.evidence_id in active_ids}),
        } for task in frontier.questions] if state.research_mode == "findings" else []
        return SearchStateSnapshot(
            research_mode=state.research_mode,
            task_evidence=task_evidence,
            tables=tables,
            frontier=FrontierSnapshot(
                by_status=dict(by_status),
                open_by_kind=dict(open_by_kind),
                running_tasks=running_tasks,
            ),
            total_rows=total_rows,
            rows_with_gaps=rows_with_gaps,
        )
