"""SOCM — Search-Oriented Context Management (paper §SOCM).

The four-tuple search state (Frontier / Evidence / Coverage / Strategy) plus
the aggregated SearchState, workspace persistence, role-specific views, and
the provenance trace.
"""

from searchos.socm.coverage import (
    CellStatus,
    ColumnCheck,
    ColumnDesc,
    CoverageCell,
    CoverageMap,
    ForeignKey,
    Relation,
    RelationKind,
    SchemaMode,
    TableSchema,
)
from searchos.socm.views import (
    FrontierSnapshot,
    RowStatus,
    SearchStateSnapshot,
    TableSnapshot,
)
from searchos.socm.evidence import (
    EvidenceEdge,
    EvidenceGraph,
    EvidenceNode,
    EvidenceRelation,
    EvidenceStatus,
)
from searchos.socm.frontier import (
    MAX_TASK_ATTEMPTS,
    FrontierMemory,
    FrontierTask,
    FrontierTaskStatus,
)
from searchos.socm.state import (
    BudgetState,
    ExploreReport,
    ExploredPath,
    Outline,
    OutlineSection,
    SearchReport,
    SearchState,
    WriterReport,
)
from searchos.socm.strategy import (
    AntiPatternKind,
    AntiPatternScope,
    FailureMemory,
    StrategyMemory,
    StrategyPattern,
)
from searchos.socm.views.trace import resolve_cell_provenance
from searchos.socm.workspace import WorkspaceManager

__all__ = [
    # Frontier
    "FrontierTask", "FrontierTaskStatus",
    "MAX_TASK_ATTEMPTS", "FrontierMemory",
    # Evidence
    "EvidenceNode", "EvidenceEdge", "EvidenceGraph",
    "EvidenceRelation", "EvidenceStatus",
    # Coverage
    "CoverageMap", "CoverageCell", "CellStatus", "ColumnCheck", "ColumnDesc",
    "TableSchema", "SchemaMode", "ForeignKey", "Relation", "RelationKind",
    # Strategy / failure
    "StrategyMemory", "StrategyPattern", "FailureMemory",
    "AntiPatternKind", "AntiPatternScope",
    # State container + outline / budget / reports
    "SearchState", "Outline", "OutlineSection", "BudgetState", "ExploredPath",
    "SearchReport", "WriterReport", "ExploreReport",
    # Snapshot / views input
    "SearchStateSnapshot", "TableSnapshot", "RowStatus", "FrontierSnapshot",
    # Persistence + trace
    "WorkspaceManager", "resolve_cell_provenance",
]
