"""SOCM · aggregated SearchState — the single source of truth, persisted as
workspace/search_state.json. Holds the four memories plus the writer outline,
budget, and per-agent runtime flags.

Also defines the writer Outline and the agent-run report classes (search /
writer / explore) consumed by the orchestrator's report collector.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from searchos.socm.coverage.models import CoverageMap
from searchos.socm.evidence.graph import EvidenceGraph
from searchos.socm.planning.frontier import FrontierMemory
from searchos.socm.planning.research_plan import ResearchPlan
from searchos.socm.planning.strategy import StrategyMemory
from searchos.util.base_model import CamelModel


class ExploredPath(CamelModel):
    """A search query that has been executed."""

    query: str
    result_summary: str = ""
    useful: bool = False
    timestamp: str = ""
    source: str = ""  # which tool/worker executed this


# ---------------------------------------------------------------------------
# Writer outline (paper §Writer Tools)
# ---------------------------------------------------------------------------

class OutlineSection(CamelModel):
    """One outline section. write_section / edit_section must attach
    ``cited_evidence_ids`` (guarded in the tool layer)."""
    id: str
    title: str = ""
    content: str = ""
    cited_evidence_ids: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)  # annotate_section appends
    order: float = 0.0  # ascending = earlier in render


class Outline(CamelModel):
    """Writer outline — ordered list of sections."""
    sections: list[OutlineSection] = Field(default_factory=list)

    def find(self, section_id: str) -> OutlineSection | None:
        for s in self.sections:
            if s.id == section_id:
                return s
        return None

    def upsert(self, section: OutlineSection) -> OutlineSection:
        existing = self.find(section.id)
        if existing is None:
            if section.order == 0.0:
                section.order = float(len(self.sections) + 1)
            self.sections.append(section)
            return section
        # Merge — fields left empty on the incoming section preserve existing.
        if section.title:
            existing.title = section.title
        if section.content:
            existing.content = section.content
        if section.cited_evidence_ids:
            existing.cited_evidence_ids = section.cited_evidence_ids
        if section.order:
            existing.order = section.order
        return existing

    def remove(self, section_id: str) -> bool:
        for i, s in enumerate(self.sections):
            if s.id == section_id:
                self.sections.pop(i)
                return True
        return False

    def rendered(self) -> str:
        """Render sections in order. Notes surface only for sections with NO
        content yet (they explain the gap); once content is written notes are
        stale planning markers, kept in the persisted Outline but hidden."""
        ordered = sorted(self.sections, key=lambda s: (s.order, s.id))
        parts: list[str] = []
        for s in ordered:
            if s.title:
                parts.append(f"## {s.title}")
            content = (s.content or "").strip()
            if content:
                parts.append(content)
            else:
                for note in s.notes:
                    parts.append(f"> TODO: {note}")
        return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Budget
# ---------------------------------------------------------------------------

class BudgetState(CamelModel):
    """Multi-dimensional budget — persisted as part of SearchState."""

    max_queries: int = 100
    consumed_queries: int = 0
    max_time_s: int = 0  # 0 = no enforcement (elapsed still tracked)
    elapsed_s: float = 0.0
    max_iterations: int = 0  # 0 = disabled
    current_iteration: int = 0

    @property
    def consumption_ratio(self) -> float:
        ratios = []
        if self.max_queries > 0:
            ratios.append(self.consumed_queries / self.max_queries)
        if self.max_iterations > 0:
            ratios.append(self.current_iteration / self.max_iterations)
        return max(ratios) if ratios else 0.0

    @property
    def exhausted(self) -> bool:
        return self.consumption_ratio >= 1.0


# ---------------------------------------------------------------------------
# Agent-run reports (consumed by the orchestrator report collector)
# ---------------------------------------------------------------------------

class SearchReport(CamelModel):
    """Report from a completed web or local search-agent run. All fields except
    identity/status/result/duration are populated via state-diff at task
    completion — sub-agents do NOT fill these by hand."""

    kind: str = "search"
    agent_id: str
    task_ids: list[str] = Field(default_factory=list)
    status: str  # completed | looped | error | cancelled
    result: str = ""  # 1-2 sentence summary
    cells_filled: list[str] = Field(default_factory=list)  # entity.attribute
    dead_ends: list[str] = Field(default_factory=list)
    discovered_entities: list[str] = Field(default_factory=list)
    # Distinguish "found data but scope mismatched" from "found nothing".
    evidence_nodes_added: int = 0
    partial_scope_count: int = 0
    duration_s: float = 0.0
    last_message: str = ""  # verbatim last no-tool AIMessage (orchestrator brief)


class WriterReport(CamelModel):
    """Report from one writer_agent continuation (writer is long-lived —
    each turn produces a fresh report, not a lifetime summary)."""

    kind: str = "writer"
    agent_id: str
    status: str  # drafting | completed | blocked | error
    result: str = ""
    draft_length: int = 0
    draft_delta: int = 0
    missing_evidence_count: int = 0
    continue_turn_count: int = 1  # 1 = first turn after spawn
    duration_s: float = 0.0
    last_message: str = ""


class ExploreReport(CamelModel):
    """首次或后续 Explore 的结果；简报记录已解决的不确定性、来源与剩余缺口。"""

    kind: str = "explore"
    agent_id: str
    status: str  # completed | failed | error
    result: str = ""
    duration_s: float = 0.0
    last_message: str = ""


# ---------------------------------------------------------------------------
# Aggregated state
# ---------------------------------------------------------------------------

class SearchState(CamelModel):
    """Top-level search state — single source of truth, persisted as
    workspace/search_state.json."""

    def model_post_init(self, __context: Any) -> None:
        """旧快照从已选证据恢复完整值；保留排序、状态与单元格投影。"""
        from searchos.socm.coverage.models import CellStatus
        from searchos.socm.coverage.projection import (
            evidence_source_allowed,
            project_cell_evidence,
        )

        cmap = self.coverage_map
        for key, cell in cmap.cells.items():
            if cell.full_value is not None or cell.status != CellStatus.FILLED:
                continue
            target = cmap.cell_binding(key)
            if target is None or target[2] in cmap.tables[target[0]].primary_key:
                continue
            node = self.evidence_graph.get_node(cell.primary_evidence_id)
            if node is None or not evidence_source_allowed(self, node):
                continue
            projected = project_cell_evidence(cmap, node, *target)
            if projected is not None:
                cell.full_value = projected.value or projected.finding

    intent: str = ""
    research_plan: ResearchPlan | None = None
    # None retains CLI compatibility; WebUI always supplies an explicit scope.
    source_scope: dict[str, Any] | None = None
    research_mode: Literal["table", "findings"] = "table"
    frontier: FrontierMemory = Field(default_factory=FrontierMemory)
    explored_paths: list[ExploredPath] = Field(default_factory=list)
    evidence_graph: EvidenceGraph = Field(default_factory=EvidenceGraph)
    coverage_map: CoverageMap = Field(default_factory=CoverageMap)
    strategy_log: StrategyMemory = Field(default_factory=StrategyMemory)
    budget: BudgetState = Field(default_factory=BudgetState)

    # Per-sub-agent runtime flags written by sensors (LoopSensor) so the report
    # collector can tag a run "looped" instead of force-stopping. Keyed by
    # thread_id (== agent_id).
    agent_status: dict[str, str] = Field(default_factory=dict)
    agent_dead_ends: dict[str, list[str]] = Field(default_factory=dict)

    # Writer draft lives in the structured outline; search tasks live in the
    # unified Frontier (no separate pending/conflict queues).
    outline: Outline = Field(default_factory=Outline)

    # Sub-agent summaries that arrived BEFORE create_schema (explore is the
    # canonical case). Without a schema, extraction drops them; stash here so
    # create_schema can replay extraction once the schema exists.
    # Each item: {"agent_id", "source_url", "content"}.
    pending_agent_summaries: list[dict[str, str]] = Field(default_factory=list)

    required_attributes: list[str] = Field(default_factory=list)

    # Optional row-identity hint: the column set that uniquely identifies a
    # row. When set, create_schema warns if the committed primary_key doesn't
    # cover it. Seeded (eval only) from the benchmark's unique_columns via
    # --seed-primary-key; empty in normal runs.
    primary_key_hint: list[str] = Field(default_factory=list)

    @property
    def effective_coverage(self) -> float:
        """Completion score for both tabular and multi-hop queries. Tabular →
        cell fill-rate; multi-hop → frontier resolved-rate (coverage_map is
        degenerate there). Max of the two reflects actual progress either way."""
        cell_rate = self.coverage_map.coverage_score
        total_q = len(self.frontier.questions)
        frontier_rate = self.frontier.resolved_count / total_q if total_q else 0.0
        return max(cell_rate, frontier_rate)
