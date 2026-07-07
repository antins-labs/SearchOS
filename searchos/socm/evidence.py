"""SOCM · Evidence Graph — structured repository of gathered findings
(paper §Evidence Graph). Nodes carry content + source + quality signals +
schema binding; typed edges (support / conflict / refine) feed arbitration.
"""

from __future__ import annotations

import time
from enum import Enum

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
    """A single finding — a natural-language note about the query.

    The extractor *records* relevant information from pages, it does not
    adjudicate it into cells. Alignment hints connect it softly to the
    schema so synthesis can later group and render.
    """

    id: str

    finding: str = ""         # NL sentence; structured paths use "{entity} {attr}: {value}"
    value: str = ""           # cell-level value alone (e.g. "$97,690 million"); empty for free-form
    source: str = ""          # URL or file path
    source_excerpt: str = ""  # verbatim supporting quote
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


class EvidenceGraph(CamelModel):
    """Evidence nodes (claims) + edges (support / conflict / refine)."""

    nodes: list[EvidenceNode] = Field(default_factory=list)
    edges: list[EvidenceEdge] = Field(default_factory=list)

    # Content-signature set for O(1) dedup. Rebuilt lazily from ``nodes`` (state
    # reloads per atomic update, so it can't persist); PrivateAttr keeps it out
    # of serialization.
    _sig_index: set[tuple[str, ...]] | None = PrivateAttr(default=None)

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
        """Append unless an identical finding exists. True = added."""
        if self._sig_index is None:
            self._sig_index = {self._dedup_sig(n) for n in self.nodes}
        sig = self._dedup_sig(node)
        if sig in self._sig_index:
            return False
        if node.created_at == 0.0:
            node.created_at = time.time()
        self.nodes.append(node)
        self._sig_index.add(sig)
        return True

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
                if a and b:
                    conflicts.append((a, b))
        return conflicts

    def get_claims_for(self, entity: str, attribute: str) -> list[EvidenceNode]:
        return [n for n in self.nodes if n.entity == entity and n.attribute == attribute]

    @property
    def node_count(self) -> int:
        return len(self.nodes)
