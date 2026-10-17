"""Evidence 的单元格投影、可见性与只读挂载检查。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from searchos.socm.coverage.models import CoverageMap
from searchos.socm.evidence.graph import EvidenceNode, EvidenceStatus

if TYPE_CHECKING:
    from searchos.socm.state import SearchState


def evidence_rank(node: EvidenceNode) -> tuple[int, int, float]:
    """Coverage 与所有输出共用的证据优先级。"""
    return (
        CoverageMap._fill_tier(node),
        CoverageMap._ALIGNMENT_RANK.get(CoverageMap._fill_alignment(node), 0),
        CoverageMap._effective_confidence(node),
    )


def evidence_table_id(cmap: CoverageMap, node: EvidenceNode) -> str:
    # 多表旧证据必须有明确归属，不能默认为第一张表。
    return node.table_id or (cmap.primary_table_id if len(cmap.tables) == 1 else "")


def evidence_scope(state: SearchState, node: EvidenceNode) -> dict[str, Any]:
    cmap = state.coverage_map
    tid = evidence_table_id(cmap, node)
    scope = {"table_id": tid, "row_status": "unbound", "exclusion_reason": ""}
    if not node.entity and not node.attribute:
        scope["table_id"] = node.table_id
        return scope
    entity, status = cmap.resolve_row(node.entity, table_id=tid) if tid else (None, "missing")
    scope["row_status"] = status
    if status == "excluded":
        scope["exclusion_reason"] = cmap.tables[tid].removed_entities[entity]
    elif status == "missing":
        scope["exclusion_reason"] = "unresolved_entity_or_table"
    elif node.attribute and cmap.resolve_attribute(node.attribute, table_id=tid) is None:
        scope.update(row_status="missing", exclusion_reason="unresolved_attribute")
    return scope


def answer_evidence(state: SearchState) -> list[EvidenceNode]:
    visible_bindings = {
        binding.evidence_id for key, bindings in state.coverage_map.evidence_bindings.items()
        if key in state.coverage_map.cells
        for binding in bindings if binding.status == EvidenceStatus.ACTIVE
    }
    return [
        node
        for node in state.evidence_graph.nodes
        if node.status == EvidenceStatus.ACTIVE
        and (evidence_scope(state, node)["row_status"] in {"active", "unbound"} or node.id in visible_bindings)
        and evidence_source_allowed(state, node)
    ]


def evidence_source_allowed(state: SearchState, node: EvidenceNode) -> bool:
    scope = state.source_scope
    if scope is None or node.source.startswith("agent://"):
        return True
    is_local = node.source.startswith("local://") or bool(node.local_source_metadata)
    if not is_local:
        return scope.get("mode") != "local"
    if scope.get("mode") == "web":
        return False
    from searchos.local.reader.references import parse_ref_id

    try:
        ref = parse_ref_id(node.source)
    except ValueError:
        return False
    return any(
        record.get("document_id") == ref.document_id
        and str(record.get("source_revision", "")).startswith(ref.source_revision)
        and (not ref.library_id or record.get("library_id") == ref.library_id)
        for record in scope.get("documents", [])
    )


def evidence_matches_cell(
    cmap: CoverageMap,
    node: EvidenceNode,
    table_id: str,
    entity: str,
    attribute: str,
) -> bool:
    return project_cell_evidence(cmap, node, table_id, entity, attribute) is not None


def project_cell_evidence(cmap: CoverageMap, node: EvidenceNode, table_id: str,
                          entity: str, attribute: str) -> EvidenceNode | None:
    """按指定格生成只读投影视图；原始事实不携带新的表格归属。"""
    key = cmap._resolve_cell_key(entity, attribute, table_id=table_id)
    if node.status != EvidenceStatus.ACTIVE or key is None:
        return None
    bindings = [b for b in cmap.evidence_bindings.get(key, []) if b.evidence_id == node.id]
    if bindings:
        binding = next((b for b in bindings if b.status == EvidenceStatus.ACTIVE), None)
        if binding is None:
            return None
        return node.model_copy(update={"table_id": table_id, "entity": entity, "attribute": attribute,
                                       "value": binding.value, "alignment": binding.alignment})
    tid = evidence_table_id(cmap, node)
    if node.status != EvidenceStatus.ACTIVE or not tid or tid != table_id:
        return None
    original_key = cmap._resolve_cell_key(node.entity, node.attribute, table_id=tid)
    return node if original_key == key else None


def audit_evidence_links(state: SearchState) -> list[dict[str, str]]:
    """历史数据只读检查；不推断或修改挂载。"""
    issues = []
    by_id = {node.id: node for node in state.evidence_graph.nodes}
    attached: set[str] = set()
    for key, cell in state.coverage_map.cells.items():
        binding = state.coverage_map.cell_binding(key)
        for fid in cell.supporting_evidence_ids:
            if fid not in by_id:
                issues.append({"cell": key, "evidence_id": fid, "reason": "dangling_id"})
            elif binding is None or not evidence_matches_cell(
                state.coverage_map, by_id[fid], *binding
            ):
                issues.append({"cell": key, "evidence_id": fid, "reason": "invalid_binding"})
            else:
                attached.add(fid)
    for node in answer_evidence(state):
        if node.entity and node.attribute and node.id not in attached:
            issues.append({"cell": "", "evidence_id": node.id, "reason": "unattached_evidence"})
    return issues
