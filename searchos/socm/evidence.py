"""SOCM · Evidence Graph — structured repository of gathered findings
(paper §Evidence Graph). Nodes carry content + source + quality signals +
schema binding; typed edges (support / conflict / refine) feed arbitration.
"""

from __future__ import annotations

import time
from enum import Enum
from typing import Any, Literal

from pydantic import Field, PrivateAttr, computed_field

from searchos.util.base_model import CamelModel


class EvidenceRelation(str, Enum):
    SUPPORT = "support"
    CONFLICT = "conflict"
    REFINE = "refine"


class EvidenceStatus(str, Enum):
    ACTIVE = "active"          # eligible for citation / coverage aggregation
    REJECTED = "rejected"      # ruled wrong; kept for audit, not cited
    SUPERSEDED = "superseded"  # replaced by a better source; kept for provenance


class EvidenceNode(CamelModel):
    """一条带来源的事实；绑定证据通过统一提交逻辑写入并投影到单元格。"""

    id: str

    finding: str = ""         # NL sentence; structured paths use "{entity} {attr}: {value}"
    value: str = ""           # cell-level value alone (e.g. "$97,690 million"); empty for free-form
    source: str = ""          # URL or file path
    source_urls: list[str] = Field(default_factory=list)  # 内部观测所引用的原文地址。
    source_excerpt: str = ""  # verbatim supporting quote
    local_source_metadata: dict[str, Any] | None = None
    confidence: float = 0.5   # 0-1; from high/medium/low at extraction

    entity: str = ""
    attribute: str = ""
    alignment: str = "loose"  # full = whole-entity value | partial = subset | loose = tangential
    alignment_note: str = ""

    source_authority: str = ""  # official | industry_pr | aggregator | news | blog | unclear
    table_id: str = ""

    status: EvidenceStatus = EvidenceStatus.ACTIVE

    # ---- Infrastructure ----
    page_id: str = ""
    observation_id: str = ""
    span: tuple[int, int] | None = None
    text_hash: str = ""
    selector: str = ""
    created_at: float = 0.0

    @computed_field  # type: ignore[misc]
    @property
    def claim(self) -> str:
        return self.finding

    @computed_field  # type: ignore[misc]
    @property
    def scope_match(self) -> str:
        return self.alignment


class EvidenceEdge(CamelModel):
    from_id: str
    to_id: str
    relation: EvidenceRelation


class EvidenceComparison(CamelModel):
    """某个单元格中两份完整投影的判定；内容指纹隔离历史结果。"""

    left_id: str
    right_id: str
    verdict: Literal["compatible", "contradictory", "uncertain"]
    reason: str = ""
    left_quote: str = ""
    right_quote: str = ""
    scope: str = ""
    verified: bool = False
    retry_after: float = 0.0


class TaskEvidenceBinding(CamelModel):
    """事实与任务的用途关联；关联不改变事实身份或任务执行状态。"""

    task_id: str
    evidence_id: str
    relation: Literal["supports", "contradicts", "context"] = "supports"


class SourceObservation(CamelModel):
    """支撑事实的不可变阅读窗口；字符位置相对此处正文。"""

    id: str
    source: str
    text: str
    text_hash: str
    local_source_metadata: dict[str, Any] | None = None
    source_urls: list[str] = Field(default_factory=list)

    @classmethod
    def capture(
        cls, source: str, text: str, metadata: dict[str, Any] | None = None, *, source_urls=()
    ) -> "SourceObservation":
        import hashlib
        import json

        digest = hashlib.sha256(text.encode()).hexdigest()
        identity_parts = [source, digest, metadata]
        if source_urls:
            identity_parts.append(list(source_urls))
        identity = json.dumps(identity_parts, sort_keys=True, ensure_ascii=False)
        return cls(
            id="obs_" + hashlib.sha256(identity.encode()).hexdigest()[:24],
            source=source,
            text=text,
            text_hash="sha256:" + digest,
            local_source_metadata=metadata,
            source_urls=list(source_urls),
        )


def bind_task_evidence(state: Any, task_id: str, evidence_ids: list[str], *,
                       relation: str = "supports") -> int:
    from searchos.socm.coverage import answer_evidence

    if not any(task.id == task_id for task in state.frontier.questions):
        raise ValueError(f"Unknown task: {task_id}")
    allowed = {node.id for node in answer_evidence(state)}
    if any(eid not in allowed for eid in evidence_ids):
        raise ValueError("Task evidence must exist and be active in the current source scope")
    bindings = [TaskEvidenceBinding(task_id=task_id, evidence_id=eid, relation=relation)
                for eid in dict.fromkeys(evidence_ids)]
    added = 0
    for binding in bindings:
        if binding not in state.evidence_graph.task_bindings:
            state.evidence_graph.task_bindings.append(binding)
            added += 1
    return added


class EvidenceGraph(CamelModel):
    """Evidence nodes (claims) + edges (support / conflict / refine)."""

    nodes: list[EvidenceNode] = Field(default_factory=list)
    edges: list[EvidenceEdge] = Field(default_factory=list)
    task_bindings: list[TaskEvidenceBinding] = Field(default_factory=list)
    observations: list[SourceObservation] = Field(default_factory=list)

    # 每次加载后惰性重建；同一批提交复用索引。
    _sig_index: dict[tuple[str, ...], EvidenceNode] | None = PrivateAttr(default=None)
    _id_index: dict[str, EvidenceNode] = PrivateAttr(default_factory=dict)

    @staticmethod
    def _dedup_sig(node: EvidenceNode) -> tuple[str, ...]:
        # Same fact + same source = duplicate. ``source`` stays in the key so
        # corroborating evidence from different pages is kept distinct.
        body = (node.value or node.finding or "").strip().lower()
        return (
            node.table_id,
            node.entity.strip().lower(),
            node.attribute.strip().lower(),
            body,
            node.source,
        )

    def add_node(self, node: EvidenceNode) -> bool:
        """兼容只关心新增数量的调用方。"""
        _, added = self.get_or_add(node)
        return added

    def invalidate_index(self) -> None:
        """证据归属被显式修改后重建去重索引。"""
        self._sig_index = None
        self._id_index = {}

    def _ensure_index(self) -> None:
        if self._sig_index is None:
            self._sig_index = {self._dedup_sig(n): n for n in reversed(self.nodes)}
            self._id_index = {n.id: n for n in self.nodes}

    def get_node(self, evidence_id: str) -> EvidenceNode | None:
        self._ensure_index()
        return self._id_index.get(evidence_id)

    def find_duplicate(self, candidate: EvidenceNode) -> EvidenceNode | None:
        """只查询同一来源事实，供旧绑定数据迁移时保留原 ID。"""
        self._ensure_index()
        return self._sig_index.get(self._dedup_sig(candidate))

    def get_or_add(self, node: EvidenceNode) -> tuple[EvidenceNode, bool]:
        """返回实际持久化节点；重复提交不改变其状态。"""
        self._ensure_index()
        sig = self._dedup_sig(node)
        if sig in self._sig_index:
            return self._sig_index[sig], False
        if node.id in self._id_index:
            raise ValueError(f"Evidence ID already exists with different content: {node.id}")
        if node.created_at == 0.0:
            node.created_at = time.time()
        self.nodes.append(node)
        self._sig_index[sig] = node
        self._id_index[node.id] = node
        return node, True

    def nodes_since(self, since_ts: float) -> list[EvidenceNode]:
        return [n for n in self.nodes if n.created_at > since_ts]

    def add_edge(self, edge: EvidenceEdge) -> None:
        self.edges.append(edge)

    def get_conflicts(self) -> list[tuple[EvidenceNode, EvidenceNode]]:
        node_map = {n.id: n for n in self.nodes}
        conflicts = []
        for edge in self.edges:
            if edge.relation == EvidenceRelation.CONFLICT:
                a = node_map.get(edge.from_id)
                b = node_map.get(edge.to_id)
                if a and b and a.status == b.status == EvidenceStatus.ACTIVE:
                    conflicts.append((a, b))
        return conflicts

    def get_claims_for(self, entity: str, attribute: str) -> list[EvidenceNode]:
        return [n for n in self.nodes if n.entity == entity and n.attribute == attribute]

    @property
    def node_count(self) -> int:
        return len(self.nodes)
