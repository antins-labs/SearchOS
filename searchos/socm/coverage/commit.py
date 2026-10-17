"""Evidence 与单元格投影的验证、提交和状态刷新。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from searchos.socm.coverage.models import CellEvidenceBinding, CellStatus, CoverageCell
from searchos.socm.coverage.projection import (
    answer_evidence,
    evidence_matches_cell,
    evidence_source_allowed,
    evidence_table_id,
    project_cell_evidence,
)
from searchos.socm.evidence.graph import EvidenceNode, EvidenceStatus

if TYPE_CHECKING:
    from searchos.socm.state import SearchState


def bind_cell_evidence(state: SearchState, bindings: list[tuple[str, CellEvidenceBinding]],
                       *, overwrite: bool = False,
                       validation_values: dict[tuple[str, str], Any] | None = None) -> int:
    """提交已核验的投影。调用方负责语义支持检查；这里校验身份、范围和列约束。"""
    from searchos.socm.evidence.values import is_missing_value

    cmap = state.coverage_map
    allowed = {node.id for node in answer_evidence(state)}
    seen = set()
    for key, binding in bindings:
        target = cmap.cell_binding(key)
        if key not in cmap.cells or target is None:
            raise ValueError(f"Unknown or excluded cell: {key}")
        if binding.evidence_id not in allowed or binding.status != EvidenceStatus.ACTIVE:
            raise ValueError("Cell evidence must be active and in the current source scope")
        if is_missing_value(binding.value) or binding.alignment not in {"full", "partial", "loose"}:
            raise ValueError("A non-empty value and valid alignment are required")
        tid, entity, attr = target
        if attr in cmap.tables[tid].primary_key:
            index = cmap.tables[tid].primary_key.index(attr)
            parts = entity.split("|")
            expected = parts[index] if index < len(parts) else entity
            if binding.value != expected:
                raise ValueError("Cell projection cannot redefine row identity")
        desc = cmap.tables[tid].column_desc.get(attr)
        checked_value = (validation_values or {}).get((key, binding.evidence_id), binding.value)
        if desc and desc.check and (reason := desc.check.violation(checked_value)):
            raise ValueError(reason)
        identity = (key, binding.evidence_id)
        if identity in seen:
            raise ValueError("Duplicate cell evidence binding in one batch")
        seen.add(identity)
        previous = next((b for b in cmap.evidence_bindings.get(key, []) if b.evidence_id == binding.evidence_id), None)
        if previous is None and binding.evidence_id in cmap.cells[key].supporting_evidence_ids:
            node = state.evidence_graph.get_node(binding.evidence_id)
            view = project_cell_evidence(cmap, node, *target)
            if view is not None:
                previous = CellEvidenceBinding(evidence_id=node.id, value=view.value or view.finding,
                                                alignment=view.alignment or "loose")
        if previous is not None and previous != binding and not overwrite:
            raise ValueError("Changing or reactivating a projection requires an explicit overwrite")
    touched = set()
    added = 0
    reset_keys = set()
    # Preserve the original cell use before a legacy node is shared. Later
    # clearing that cell must change its binding, not the shared source fact.
    for _, binding in bindings:
        node = state.evidence_graph.get_node(binding.evidence_id)
        tid = evidence_table_id(cmap, node)
        original = cmap._resolve_cell_key(node.entity, node.attribute, table_id=tid) if tid else None
        if original and node.id in cmap.cells[original].supporting_evidence_ids:
            records = cmap.evidence_bindings.setdefault(original, [])
            if not any(b.evidence_id == node.id for b in records):
                records.append(CellEvidenceBinding(evidence_id=node.id, value=node.value or node.finding,
                                                   alignment=node.alignment or "loose"))
    for key, binding in bindings:
        records = cmap.evidence_bindings.setdefault(key, [])
        cell = cmap.cells[key]
        for fid in cell.supporting_evidence_ids:
            node = state.evidence_graph.get_node(fid)
            target = cmap.cell_binding(key)
            view = project_cell_evidence(cmap, node, *target) if node and target else None
            if view and not any(b.evidence_id == fid for b in records):
                records.append(CellEvidenceBinding(evidence_id=fid, value=view.value or view.finding,
                                                   alignment=view.alignment or "loose"))
        if overwrite and key not in reset_keys:
            chosen = {item.evidence_id for target, item in bindings if target == key}
            for record in records:
                if record.evidence_id not in chosen:
                    record.status = EvidenceStatus.SUPERSEDED
            cell.supporting_evidence_ids = [fid for fid in cell.supporting_evidence_ids if fid in chosen]
            reset_keys.add(key)
        previous = next((b for b in records if b.evidence_id == binding.evidence_id), None)
        if previous is None:
            records.append(binding.model_copy(deep=True))
            added += 1
        elif previous != binding:
            records[records.index(previous)] = binding.model_copy(deep=True)
        if binding.evidence_id not in cell.supporting_evidence_ids:
            cell.supporting_evidence_ids.append(binding.evidence_id)
        touched.add(key)
    refresh_cells(state, touched)
    return added


@dataclass
class EvidenceCommit:
    """分开统计节点、挂载和覆盖率变化。"""

    nodes: list[EvidenceNode] = field(default_factory=list)
    added_nodes: list[EvidenceNode] = field(default_factory=list)
    associations_added: int = 0
    cells_filled: int = 0
    rejected: list[dict[str, str]] = field(default_factory=list)


def commit_table_facts(
    state: SearchState,
    candidates: list[EvidenceNode],
    *,
    validation_values: dict[str, Any] | None = None,
) -> EvidenceCommit:
    """自动表格抽取提交独立事实与投影；候选表字段只用于确定目标格。"""
    result = EvidenceCommit()
    cmap = state.coverage_map
    before = {key for key, cell in cmap.cells.items() if cell.status == CellStatus.FILLED}
    for candidate in candidates:
        tid = evidence_table_id(cmap, candidate)
        key = (
            cmap._resolve_cell_key(candidate.entity, candidate.attribute, table_id=tid)
            if tid
            else None
        )
        reason = ""
        if key is None:
            reason = "unresolved_cell"
        elif not evidence_source_allowed(state, candidate):
            reason = "source_out_of_scope"
        elif (
            not candidate.source.startswith(("https://", "http://", "local://", "skill://", "agent://"))
            or candidate.span is None
        ):
            reason = "unanchored_source"
        if reason:
            result.rejected.append(
                {"row": candidate.entity, "column": candidate.attribute, "reason": reason}
            )
            continue
        fact = candidate.model_copy(
            update={"table_id": "", "entity": "", "attribute": "", "value": ""}
        )
        legacy = state.evidence_graph.find_duplicate(candidate)
        durable, added = (
            (legacy, False) if legacy is not None else state.evidence_graph.get_or_add(fact)
        )
        binding = CellEvidenceBinding(
            evidence_id=durable.id, value=candidate.value, alignment=candidate.alignment
        )
        checked = (validation_values or {}).get(candidate.id, candidate.value)
        try:
            links = bind_cell_evidence(
                state, [(key, binding)], validation_values={(key, durable.id): checked}
            )
        except ValueError as exc:
            # Binding validation precedes its writes. Retract only this new
            # candidate; a pre-existing shared fact must survive rejection.
            if added:
                state.evidence_graph.nodes.remove(durable)
                state.evidence_graph.invalidate_index()
            result.rejected.append(
                {"row": candidate.entity, "column": candidate.attribute, "reason": str(exc)}
            )
            continue
        result.nodes.append(durable)
        if added:
            result.added_nodes.append(durable)
        result.associations_added += links
    result.cells_filled = sum(
        cell.status == CellStatus.FILLED and key not in before for key, cell in cmap.cells.items()
    )
    return result


def refresh_cells(state: SearchState, keys: set[str]) -> None:
    """只重建指定格的已有挂载，不扫描并补挂历史证据。"""
    cmap = state.coverage_map
    for key in keys:
        old = cmap.cells.get(key)
        if old is None:
            continue
        binding = cmap.cell_binding(key)
        if binding is None:
            continue
        tid, entity, attr = binding
        schema = cmap.tables[tid]
        cell = CoverageCell()
        if attr in schema.primary_key:
            values = entity.split("|")
            index = schema.primary_key.index(attr)
            cell.status = CellStatus.FILLED
            cell.best_alignment = "full"
            cell.display_hint = values[index] if index < len(values) else entity
        nodes = [
            projected
            for fid in dict.fromkeys(old.supporting_evidence_ids)
            if (node := state.evidence_graph.get_node(fid)) is not None
            and evidence_source_allowed(state, node)
            and (projected := project_cell_evidence(cmap, node, tid, entity, attr)) is not None
        ]
        if not nodes and old.status in {CellStatus.UNCERTAIN, CellStatus.HARD_CELL}:
            cell.status = old.status
        cmap.cells[key] = cell
        cmap.fill_from_evidence(nodes)
        cell.conflict_history_evidence_ids = list(dict.fromkeys([
            *old.conflict_history_evidence_ids, *old.conflict_evidence_ids,
        ]))
    from searchos.socm.coverage.conflicts import reconcile_conflicts

    reconcile_conflicts(state, keys)


def commit_evidence(
    state: SearchState,
    nodes: list[EvidenceNode],
    *,
    overwrite: bool = False,
    validation_values: dict[str, Any] | None = None,
) -> EvidenceCommit:
    """验证、去重、挂载一次完成；只有显式覆盖可重新启用旧证据。"""
    from searchos.socm.evidence.values import is_missing_value

    result = EvidenceCommit()
    cmap = state.coverage_map
    touched: set[str] = set()
    before_filled: set[str] = set()
    for candidate in nodes:
        tid = evidence_table_id(cmap, candidate)
        key = (
            cmap._resolve_cell_key(candidate.entity, candidate.attribute, table_id=tid)
            if tid
            else None
        )
        reason = ""
        if candidate.status != EvidenceStatus.ACTIVE:
            reason = "inactive_evidence"
        elif is_missing_value(candidate.value or candidate.finding):
            reason = "missing_value"
        elif not evidence_source_allowed(state, candidate):
            reason = "source_out_of_scope"
        elif key is None:
            reason = "unresolved_cell"
        else:
            entity = cmap.resolve_entity(candidate.entity, table_id=tid)
            attr = cmap.resolve_attribute(candidate.attribute, table_id=tid)
            desc = cmap.tables[tid].column_desc.get(attr)
            if desc and desc.check:
                value = (validation_values or {}).get(candidate.id, candidate.value)
                reason = desc.check.violation(value) or ""
        if reason:
            result.rejected.append(
                {"row": candidate.entity, "column": candidate.attribute, "reason": reason}
            )
            continue
        node, added = state.evidence_graph.get_or_add(
            candidate.model_copy(
                update={
                    "table_id": tid,
                    "entity": entity,
                    "attribute": attr,
                }
            )
        )
        if node.status != EvidenceStatus.ACTIVE and not overwrite:
            result.rejected.append({"row": entity, "column": attr, "reason": "inactive_duplicate"})
            continue
        existing_binding = next(
            (b for b in cmap.evidence_bindings.get(key, []) if b.evidence_id == node.id), None
        )
        if existing_binding is not None and existing_binding.status != EvidenceStatus.ACTIVE and not overwrite:
            result.rejected.append({"row": entity, "column": attr, "reason": "inactive_binding"})
            continue
        cell = cmap.cells[key]
        if key not in touched and cell.status == CellStatus.FILLED:
            before_filled.add(key)
        touched.add(key)
        if overwrite:
            prior_ids = set(cell.supporting_evidence_ids)
            for fid in prior_ids:
                previous = state.evidence_graph.get_node(fid)
                if previous is not None and previous.id != node.id:
                    if evidence_matches_cell(cmap, previous, tid, entity, attr):
                        records = [b for b in cmap.evidence_bindings.get(key, []) if b.evidence_id == fid]
                        if records:
                            for record in records:
                                record.status = EvidenceStatus.SUPERSEDED
                        else:
                            previous.status = EvidenceStatus.SUPERSEDED
            node.status = EvidenceStatus.ACTIVE
            if existing_binding is not None:
                existing_binding.status = EvidenceStatus.ACTIVE
                existing_binding.value = node.value or node.finding
                existing_binding.alignment = node.alignment or "loose"
            cell.supporting_evidence_ids = [
                fid for fid in cell.supporting_evidence_ids if fid == node.id
            ]
        if node.id not in cell.supporting_evidence_ids:
            cell.supporting_evidence_ids.append(node.id)
            result.associations_added += 1
        if added:
            result.added_nodes.append(node)
        result.nodes.append(node)
    refresh_cells(state, touched)
    result.cells_filled = sum(
        cmap.cells[key].status == CellStatus.FILLED for key in touched - before_filled
    )
    return result


def clear_cell_evidence(state: SearchState, table_id: str, entity: str, attribute: str) -> bool:
    cmap = state.coverage_map
    key = cmap._resolve_cell_key(entity, attribute, table_id=table_id)
    if key is None:
        return False
    cell = cmap.cells[key]
    if cell.status == CellStatus.MISSING and not cell.supporting_evidence_ids:
        return False
    ids = set(cell.supporting_evidence_ids)
    for fid in ids:
        node = state.evidence_graph.get_node(fid)
        if node is not None and evidence_matches_cell(cmap, node, table_id, entity, attribute):
            records = [b for b in cmap.evidence_bindings.get(key, []) if b.evidence_id == fid]
            if records:
                for record in records:
                    record.status = EvidenceStatus.REJECTED
            else:
                node.status = EvidenceStatus.REJECTED
    cmap.cells[key] = CoverageCell()
    return True
