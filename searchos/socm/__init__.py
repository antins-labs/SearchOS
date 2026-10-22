"""SOCM — Search-Oriented Context Management (paper §SOCM).

The four-tuple search state (Frontier / Evidence / Coverage / Failure) plus
the aggregated SearchState, workspace persistence, role-specific views, and
the provenance trace.
"""

from searchos.socm.coverage import (
    CellEvidenceBinding,
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
from searchos.socm.evidence import (
    EvidenceEdge,
    EvidenceGraph,
    EvidenceNode,
    EvidenceRelation,
    EvidenceStatus,
)
from searchos.socm.failure_memory import (
    FailureKind,
    FailureMemory,
    FailureScope,
    FailureStore,
    record_failure,
)
from searchos.socm.planning.frontier import (
    MAX_TASK_ATTEMPTS,
    FrontierMemory,
    FrontierTask,
    FrontierTaskStatus,
)
from searchos.socm.state import (
    BudgetState,
    ExploredPath,
    ExploreReport,
    Outline,
    OutlineSection,
    SearchReport,
    SearchState,
    WriterReport,
)
from searchos.socm.storage.workspace import WorkspaceManager
from searchos.socm.views import (
    FrontierSnapshot,
    RowStatus,
    SearchStateSnapshot,
    TableSnapshot,
)
from searchos.socm.views.trace import resolve_cell_provenance

__all__ = [
    # Frontier
    "FrontierTask", "FrontierTaskStatus",
    "MAX_TASK_ATTEMPTS", "FrontierMemory",
    # Evidence
    "EvidenceNode", "EvidenceEdge", "EvidenceGraph",
    "EvidenceRelation", "EvidenceStatus",
    # Coverage
    "CoverageMap", "CoverageCell", "CellEvidenceBinding", "CellStatus", "ColumnCheck", "ColumnDesc",
    "TableSchema", "SchemaMode", "ForeignKey", "Relation", "RelationKind",
    # Failure memory
    "FailureKind", "FailureMemory", "FailureScope", "FailureStore", "record_failure",
    # State container + outline / budget / reports
    "SearchState", "Outline", "OutlineSection", "BudgetState", "ExploredPath",
    "SearchReport", "WriterReport", "ExploreReport",
    # Snapshot / views input
    "SearchStateSnapshot", "TableSnapshot", "RowStatus", "FrontierSnapshot",
    # Persistence + trace
    "WorkspaceManager", "resolve_cell_provenance",
]
