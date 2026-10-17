"""研究请求与响应契约，供 HTTP 路由和 Assistant 调度共用。"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class SkillOverrides(BaseModel):
    """Per-run skill selection; each field overrides the stored setting when given."""
    access_only: list[str] | None = None
    access_deny: list[str] | None = None
    strategy_deny: list[str] | None = None
    orchestrator_deny: list[str] | None = None

class HistoryTurn(BaseModel):
    """One prior conversation turn, echoed back by the client for follow-ups."""
    query: str
    answer: str = ""

class LocalSourceRequest(BaseModel):
    library_id: str = Field(min_length=1, max_length=160)
    selection: Literal["library", "documents"] = "documents"
    document_ids: list[str] = Field(default_factory=list, max_length=100)
    model_access: Literal[True]

    @model_validator(mode="after")
    def validate_selection(self):
        if self.selection == "documents" and not self.document_ids:
            raise ValueError("文档范围至少包含一份文档")
        if self.selection == "library" and self.document_ids:
            raise ValueError("资料库范围不能同时指定文档")
        return self

class SourcesRequest(BaseModel):
    mode: Literal["web", "local", "hybrid"] = "web"
    local: LocalSourceRequest | None = None

class SchemaTableRequest(BaseModel):
    table_id: str
    table_label: str | None = None
    entities: list[str] | None = None
    attrs: list[str]
    primary_key: list[str] | None = None
    row_label: str | None = None

class SchemaRelationRequest(BaseModel):
    from_table: str
    to_table: str
    foreign_key: list[str]
    target_columns: list[str] | None = None
    kind: Literal["one_to_many", "many_to_many"] = "one_to_many"
    label: str | None = None

class SearchRequest(BaseModel):
    query: str
    entities: list[str] | None = None
    attrs: list[str] | None = None
    table_label: str | None = None
    primary_key: list[str] | None = None
    row_label: str | None = None
    tables: list[SchemaTableRequest] | None = None
    relations: list[SchemaRelationRequest] | None = None
    max_time: int | None = None       # None → stored default → settings.default_max_time_s
    effort: Literal["low", "medium", "high", "max"] | None = None  # this run only
    skills: SkillOverrides | None = None
    trusted_domains: list[str] = Field(default_factory=list, max_length=20)
    excluded_domains: list[str] = Field(default_factory=list, max_length=50)
    sources: SourcesRequest | None = None
    # Follow-up reuses the prior session workspace and conversation identity.
    # Web carries SearchState forward; Local resets SearchState per turn so
    # evidence remains constrained to that turn's selected documents.
    follow_up_to: str | None = None
    history: list[HistoryTurn] | None = None

class SearchResponse(BaseModel):
    session_id: str
    status: str

class RepairCellRequest(BaseModel):
    table_id: str
    entity: str
    attribute: str

class RepairRequest(BaseModel):
    # The selected cells are validated against the persisted CoverageMap below,
    # so the real scope bound is the session itself. Repair-all must not fail at
    # an arbitrary request-size threshold before that validation runs.
    cells: list[RepairCellRequest] = Field(min_length=1)
    max_time: int | None = None
    effort: Literal["low", "medium", "high", "max"] | None = None
    skills: SkillOverrides | None = None
    trusted_domains: list[str] = Field(default_factory=list, max_length=20)
    excluded_domains: list[str] = Field(default_factory=list, max_length=50)
    history: list[HistoryTurn] | None = None

class RepairResponse(SearchResponse):
    task_ids: list[str]
    cells: list[RepairCellRequest]
    planner: Literal["orchestrator", "llm", "deterministic"] = "orchestrator"
    planning_latency_ms: int = 0
    planning_warning: str | None = None

class ResolveEvidenceRequest(RepairCellRequest):
    evidence_id: str

class ResolveEvidenceResponse(BaseModel):
    status: str
    selected_evidence_id: str
    superseded_evidence_ids: list[str]
    search_state: dict[str, Any]

class SteerRequest(BaseModel):
    message: str
    mode: Literal["immediate", "after_tool"] = "immediate"
