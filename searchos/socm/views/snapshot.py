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

from searchos.socm.coverage.models import cell_is_actionable, cell_is_complete

if TYPE_CHECKING:
    from searchos.socm.state import SearchState


@dataclass
class CellInfo:
    attr: str
    status: str  # missing | filled | uncertain | hard_cell
    display_hint: str
    evidence_count: int
    best_alignment: str  # full | partial | loose | ""
    has_conflict: bool
    conflict_status: str = "clear"
    active_task_ids: list[str] = field(default_factory=list)
    requires_search: bool = True
    inferred: bool = False


@dataclass
class RowStatus:
    entity: str
    cells: list[CellInfo]
    key_values: dict[str, str] = field(default_factory=dict)

    @property
    def filled_cols(self) -> list[str]:
        return [c.attr for c in self.cells if cell_is_complete(c)]

    @property
    def missing_cols(self) -> list[str]:
        return [c.attr for c in self.cells if cell_is_actionable(c)]

    @property
    def evidence_count(self) -> int:
        return sum(c.evidence_count for c in self.cells)

    @property
    def is_complete(self) -> bool:
        return all(cell_is_complete(c) for c in self.cells)

    @property
    def is_empty(self) -> bool:
        return all(c.evidence_count == 0 and not c.inferred for c in self.cells)


@dataclass
class TableSnapshot:
    table_id: str
    label: str
    primary_key: list[str]
    data_columns: list[str]
    is_open_set: bool
    rows: list[RowStatus]
    column_descriptions: dict[str, str] = field(default_factory=dict)
    recent_entities: list[str] = field(default_factory=list)
    inferred_columns: list[str] = field(default_factory=list)

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

    def summary(self) -> dict:
        """全表统计与展示窗口独立；冲突计数单列。"""
        by_status: Counter[str] = Counter()
        by_attribute = {}
        complete = actionable = unassigned = conflicts = pending = 0
        for attr in self.data_columns:
            by_attribute[attr] = dict(unresolved=0, actionable=0, unavailable=0,
                                      conflicts=0, pending=0)
        for row in self.rows:
            for cell in row.cells:
                by_status[cell.status] += 1
                done, work = cell_is_complete(cell), cell_is_actionable(cell)
                conflict = cell.has_conflict or cell.conflict_status == "confirmed"
                waiting = cell.conflict_status == "pending"
                complete += done
                actionable += work
                unassigned += work and not cell.active_task_ids
                conflicts += conflict
                pending += waiting
                counts = by_attribute[cell.attr]
                counts["unresolved"] += not done
                counts["actionable"] += work
                counts["unavailable"] += cell.status == "hard_cell"
                counts["conflicts"] += conflict
                counts["pending"] += waiting
        return dict(total_rows=len(self.rows), filled_rows=sum(r.is_complete for r in self.rows),
                    unresolved_rows=sum(not r.is_complete for r in self.rows),
                    total_cells=sum(by_status.values()), completed_cells=complete,
                    by_status=dict(by_status), actionable_cells=actionable,
                    unassigned_actionable_cells=unassigned, conflicts=conflicts,
                    pending_comparisons=pending, by_attribute=by_attribute)


@dataclass
class FrontierSnapshot:
    by_status: dict[str, int] = field(default_factory=dict)
    open_by_kind: dict[str, int] = field(default_factory=dict)


@dataclass
class SearchStateSnapshot:
    tables: list[TableSnapshot]
    frontier: FrontierSnapshot
    total_rows: int
    rows_with_gaps: int
    task_evidence: list[dict] = field(default_factory=list)
    findings: list[dict] = field(default_factory=list)

    @staticmethod
    def from_state(state: SearchState) -> SearchStateSnapshot:
        cmap = state.coverage_map
        frontier = state.frontier
        owners = frontier.active_cell_tasks(cmap)

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
                        cells.append(
                            CellInfo(
                                attr=attr,
                                status="missing",
                                requires_search=ts.requires_search(attr),
                                display_hint="",
                                evidence_count=0,
                                best_alignment="",
                                has_conflict=False,
                                active_task_ids=owners.get(key, []),
                            )
                        )
                    else:
                        cells.append(
                            CellInfo(
                                attr=attr,
                                status=cell.status.value if cell.status else "missing",
                                requires_search=ts.requires_search(attr),
                                inferred=cell.inferred,
                                display_hint=cell.display_hint or "",
                                evidence_count=len(cell.supporting_evidence_ids),
                                best_alignment=cell.best_alignment or "",
                                has_conflict=cell.has_conflict,
                                conflict_status=cell.conflict_status,
                                active_task_ids=owners.get(key, []),
                            )
                        )
                row = RowStatus(entity=ent, cells=cells,
                                key_values=cmap.primary_key_values(ent, table_id=tid))
                rows.append(row)
                if not row.is_complete:
                    rows_with_gaps += 1

            total_rows += len(rows)
            tables.append(
                TableSnapshot(
                    table_id=tid,
                    label=ts.table_label or tid,
                    primary_key=list(ts.primary_key or []),
                    data_columns=data_cols,
                    is_open_set=ts.is_column_only,
                    rows=rows,
                    recent_entities=list(ts.entities[-30:]),
                    inferred_columns=[a for a in data_cols if not ts.requires_search(a)],
                    column_descriptions={
                        a: f"{d.type}: {d.desc}" for a, d in ts.column_desc.items()
                    },
                )
            )

        by_status: Counter[str] = Counter()
        open_by_kind: Counter[str] = Counter()
        for q in frontier.questions if frontier else []:
            s = q.status.value if q.status else ""
            by_status[s] += 1
            if s == "pending":
                open_by_kind[q.kind or "search"] += 1

        from searchos.socm.coverage import answer_evidence

        evidence = answer_evidence(state)
        active_ids = {node.id for node in evidence}
        task_evidence = [
            {
                "task_id": task.id,
                "question": task.question,
                "status": task.status.value,
                "agent_type": task.agent_type,
                "agent_id": task.assigned_agent_id,
                "table_id": task.table_id,
                "target_cells": list(task.target_cells),
                "priority": task.priority,
                "updated_at": task.updated_at,
                "evidence_count": len(
                    {
                        binding.evidence_id
                        for binding in state.evidence_graph.task_bindings
                        if binding.task_id == task.id and binding.evidence_id in active_ids
                    }
                ),
            }
            for task in frontier.questions
        ]
        findings = [
            {
                "id": node.id,
                "finding": node.finding,
                "value": node.value,
                "source": node.source,
                "source_urls": node.source_urls,
                "task_ids": sorted(
                    {
                        binding.task_id
                        for binding in state.evidence_graph.task_bindings
                        if binding.evidence_id == node.id
                    }
                ),
            }
            for node in sorted(evidence, key=lambda n: n.id)
            if not node.entity and not node.attribute
        ]
        return SearchStateSnapshot(
            task_evidence=task_evidence,
            findings=findings,
            tables=tables,
            frontier=FrontierSnapshot(
                by_status=dict(by_status),
                open_by_kind=dict(open_by_kind),
            ),
            total_rows=total_rows,
            rows_with_gaps=rows_with_gaps,
        )
