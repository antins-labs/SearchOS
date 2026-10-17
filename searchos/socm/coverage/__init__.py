"""Coverage Map：表结构、证据投影与提交的统一入口。"""

from searchos.socm.coverage.models import (
    CellStatus,
    ColumnCheck,
    ColumnDesc,
    CoverageCell,
    CellEvidenceBinding,
    SchemaMode,
    TableSchema,
    RelationKind,
    ForeignKey,
    Relation,
    CoverageMap,
    validate_row,
)

from searchos.socm.coverage.projection import (
    evidence_rank,
    evidence_table_id,
    evidence_scope,
    answer_evidence,
    evidence_source_allowed,
    evidence_matches_cell,
    project_cell_evidence,
    audit_evidence_links,
)

from searchos.socm.coverage.commit import (
    bind_cell_evidence,
    EvidenceCommit,
    commit_table_facts,
    refresh_cells,
    commit_evidence,
    clear_cell_evidence,
)

__all__ = [
    "CellStatus",
    "ColumnCheck",
    "ColumnDesc",
    "CoverageCell",
    "CellEvidenceBinding",
    "SchemaMode",
    "TableSchema",
    "RelationKind",
    "ForeignKey",
    "Relation",
    "CoverageMap",
    "validate_row",
    "evidence_rank",
    "evidence_table_id",
    "evidence_scope",
    "answer_evidence",
    "evidence_source_allowed",
    "evidence_matches_cell",
    "project_cell_evidence",
    "audit_evidence_links",
    "bind_cell_evidence",
    "EvidenceCommit",
    "commit_table_facts",
    "refresh_cells",
    "commit_evidence",
    "clear_cell_evidence",
]
