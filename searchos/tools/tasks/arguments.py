"""派发工具的参数契约与校验错误。"""

from __future__ import annotations

import json
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    field_validator,
)

NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
CellKey = Annotated[
    str, StringConstraints(strip_whitespace=True, pattern=r"^.+\..+$"),
]


class EnqueueTask(BaseModel):
    """一个任务只使用当前工具声明的字段，正文不做类型转换或转义修复。"""

    model_config = ConfigDict(extra="forbid", strict=True)

    agent_type: Literal[
        "search_agent", "local_search_agent", "explore_agent", "writer_agent",
    ] = Field(
        description="Role from the available agent catalog. Determines the task kind.",
    )
    task: str = Field(
        min_length=1, description="Full, self-contained task brief; preserved verbatim.",
    )
    agent_id: NonEmptyString | None = Field(
        default=None,
        description=(
            "Optional idle Search Agent ID returned by check_agents. Reuse its history, "
            "browser and loaded skills for this new task. agent_type and source scope "
            "must match. Omit to create a new agent."
        ),
    )
    result_mode: Literal["findings", "table"] | None = Field(
        default=None,
        description=(
            "findings: sourced facts or explanations without requiring a schema. "
            "table: schema-bound collection. If omitted, table targets select table; "
            "otherwise use findings when the research plan needs no table or has no schema, "
            "then fall back to the session mode."
        ),
    )
    target_table: NonEmptyString | None = Field(
        default=None,
        description="Existing table ID; required for table tasks when multiple tables exist.",
    )
    target_cells: list[CellKey] = Field(
        default_factory=list,
        description=(
            "Cell keys such as Apple.CEO within target_table. Restricts extraction and "
            "deduplicates overlapping tasks. Leave empty for open enumeration."
        ),
    )
    priority: float = Field(
        default=0.5, ge=0, le=1, allow_inf_nan=False,
        description="Scheduling priority from 0 to 1; higher dispatches first.",
    )
    blocked_by: list[NonEmptyString] = Field(
        default_factory=list, description="Predecessor task IDs that must finish first.",
    )
    skills: list[NonEmptyString] = Field(
        default_factory=list, max_length=5,
        description=(
            "Up to five skill recommendations; unknown or blacklisted names are ignored. "
            "Omit for agent-led discovery."
        ),
    )
    max_searches: int | None = Field(
        default=None, ge=1,
        description="Positive retrieval budget; capped by runtime settings. Omit for the default.",
    )
    id: NonEmptyString | None = Field(
        default=None, description="Optional unique task ID; generated when omitted.",
    )
    parent_id: NonEmptyString | None = Field(default=None, description="Optional parent task ID.")
    depth: int = Field(
        default=0, ge=0, description="Task depth; bounded by the Frontier depth limit.",
    )

    @field_validator("task")
    @classmethod
    def require_nonblank_task(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("task must contain non-whitespace text")
        return value


class EnqueueTasksInput(BaseModel):
    """一次工具调用的完整参数；先校验整批，再进入入队逻辑。"""

    model_config = ConfigDict(extra="forbid", strict=True)

    items: list[EnqueueTask] = Field(
        min_length=1,
        description="Non-empty array of task objects; pass it directly, not a serialized string.",
    )


def task_argument_error(error: ValidationError) -> str:
    """返回字段位置，供模型修正参数；不回显完整任务正文。"""
    return json.dumps({
        "error": "invalid task arguments",
        "queued": [],
        "errors": [
            {"path": ".".join(map(str, issue["loc"])), "message": issue["msg"]}
            for issue in error.errors(include_input=False, include_url=False, include_context=False)
        ],
    }, ensure_ascii=False)
