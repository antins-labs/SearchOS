"""单元格冲突的纯状态投影；只采纳当前内容对应的已复核判断。"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from dataclasses import dataclass
from itertools import combinations
from typing import Any

from searchos.socm.evidence.graph import EvidenceNode
from searchos.socm.evidence.values import is_missing_value

COMPARISON_VERSION = "cell-semantics-v1"


def normalize_text(text: str) -> str:
    """只规范 Unicode 和空白，保留否定、大小写、数值与版本。"""
    return " ".join(unicodedata.normalize("NFC", text).split())


@dataclass(frozen=True)
class EvidencePair:
    cell_key: str
    fingerprint: str
    left: EvidenceNode
    right: EvidenceNode
    context: dict[str, Any]

    def payload(self) -> dict[str, Any]:
        return {
            "id": self.fingerprint,
            **self.context,
            "a": _claim(self.left),
            "b": _claim(self.right),
        }


def _claim(node: EvidenceNode) -> dict[str, Any]:
    return {
        "value": node.value or node.finding,
        "excerpt": node.source_excerpt,
        "source": node.source,
        "alignment": node.alignment,
        "alignment_note": node.alignment_note,
    }


def cell_pairs(state: Any, key: str) -> list[EvidencePair]:
    """比较完整投影；只归并内容和上下文完全相同的重复证据。"""
    from searchos.socm.coverage.projection import evidence_source_allowed, project_cell_evidence

    cmap = state.coverage_map
    target = cmap.cell_binding(key)
    cell = cmap.cells.get(key)
    if target is None or cell is None:
        return []
    tid, entity, attribute = target
    schema = cmap.tables[tid]
    column = schema.column_desc.get(attribute)
    context = {
        "entity": entity,
        "attribute": attribute,
        "column": column.model_dump() if column is not None else {},
        "table": schema.table_label,
    }
    nodes = []
    seen = set()
    for fid in sorted(set(cell.supporting_evidence_ids)):
        node = state.evidence_graph.get_node(fid)
        if node is None or not evidence_source_allowed(state, node):
            continue
        node = project_cell_evidence(cmap, node, *target)
        if node is None or is_missing_value(node.value or node.finding):
            continue
        identity = json.dumps(_claim(node), sort_keys=True, ensure_ascii=False)
        if identity not in seen:
            nodes.append(node)
            seen.add(identity)
    pairs = []
    for left, right in combinations(nodes, 2):
        if normalize_text(left.value or left.finding) == normalize_text(
            right.value or right.finding
        ):
            continue
        content = [
            COMPARISON_VERSION,
            key,
            state.source_scope,
            context,
            left.id,
            _claim(left),
            right.id,
            _claim(right),
        ]
        fingerprint = hashlib.sha256(
            json.dumps(content, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()
        pairs.append(EvidencePair(key, fingerprint, left, right, context))
    return pairs


def reconcile_conflicts(state: Any, keys: set[str]) -> None:
    """刷新当前标记，历史记录不参与计数；本函数不调用模型。"""
    from searchos.socm.coverage.projection import evidence_source_allowed, project_cell_evidence

    cmap = state.coverage_map
    explicit = state.evidence_graph.get_conflicts()
    for key in keys:
        cell = cmap.cells.get(key)
        target = cmap.cell_binding(key)
        if cell is None or target is None:
            continue
        active_ids: set[str] = set()
        uncertain = pending = False
        assessments = cmap.evidence_comparisons.get(key, {})
        for pair in cell_pairs(state, key):
            result = assessments.get(pair.fingerprint)
            if result is None:
                pending = True
            elif result.verdict == "uncertain":
                uncertain = True
            elif result.verdict == "contradictory" and result.verified:
                active_ids.update((pair.left.id, pair.right.id))
            elif result.verdict == "contradictory":
                uncertain = True
        # 显式关系保留兼容，但失效、撤销或移出本单元格的证据不再算冲突。
        for left, right in explicit:
            if all(
                node.id in cell.supporting_evidence_ids
                and evidence_source_allowed(state, node)
                and project_cell_evidence(cmap, node, *target) is not None
                for node in (left, right)
            ):
                active_ids.update((left.id, right.id))
        cell.conflict_history_evidence_ids = sorted(
            set(cell.conflict_history_evidence_ids + cell.conflict_evidence_ids) | active_ids
        )
        cell.conflict_evidence_ids = sorted(active_ids)
        cell.has_conflict = bool(active_ids)
        cell.conflict_status = (
            "confirmed"
            if active_ids
            else "pending"
            if pending
            else "uncertain"
            if uncertain
            else "clear"
        )
