"""Skill data models: category, availability, parsed Skill, and metadata."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import AliasChoices, Field, field_validator

from searchos.util.base_model import CamelModel


class SkillCategory(StrEnum):
    """The three skill kinds — values match the library subdirectory name."""
    STRATEGY = "strategy"          # 推理方法论（纯文字）
    ACCESS = "access"              # 数据获取方法（文字+可选代码）
    ORCHESTRATOR = "orchestrator"  # 编排方法论（任务拆分、广度收集、行级校验）


class SkillAvailability(StrEnum):
    """Whether a Skill may participate in runtime selection and execution."""

    ENABLED = "enabled"
    DISABLED = "disabled"


_LEGACY_AVAILABILITY = {
    "mined": SkillAvailability.ENABLED,
    "seed": SkillAvailability.ENABLED,
    "trial": SkillAvailability.ENABLED,
    "active": SkillAvailability.ENABLED,
    "optimized": SkillAvailability.ENABLED,
    "deprecated": SkillAvailability.DISABLED,
}


class SkillMeta(CamelModel):
    """Metadata parsed from a skill's YAML frontmatter."""

    name: str = Field(validation_alias=AliasChoices("name", "skill_name"))
    description: str = ""
    category: SkillCategory = SkillCategory.STRATEGY
    trigger: str = ""  # flat retrieval hint
    availability: SkillAvailability = Field(
        default=SkillAvailability.ENABLED,
        validation_alias=AliasChoices("availability", "status"),
    )
    has_executor: bool = False
    compatibility: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("availability", mode="before")
    @classmethod
    def _normalize_availability(cls, value: Any) -> Any:
        """Read legacy lifecycle values without exposing them at runtime."""
        if isinstance(value, SkillAvailability):
            return value
        normalized = str(value).strip().lower()
        if normalized in SkillAvailability._value2member_map_:
            return SkillAvailability(normalized)
        if normalized in _LEGACY_AVAILABILITY:
            return _LEGACY_AVAILABILITY[normalized]
        raise ValueError(f"unsupported skill availability: {value!r}")


class Skill(CamelModel):
    """A loaded skill: metadata + body text.

    Anti-patterns live in a sibling ``anti_patterns.md`` that
    ``parse_skill_file`` loads into ``anti_patterns_index`` (one-line summaries
    for prompt injection) and ``anti_patterns_details`` (full entries, fetched
    on demand). Empty when the sibling file is missing."""

    meta: SkillMeta
    body: str
    file_path: str = ""
    package_format: str = "legacy"
    package_hash: str = ""
    resources: list[str] = Field(default_factory=list)
    anti_patterns_index: str = ""
    anti_patterns_details: list[dict[str, Any]] = Field(default_factory=list)
