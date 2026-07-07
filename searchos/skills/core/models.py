"""Skill data models: category/status enums + parsed Skill + metadata."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import AliasChoices, Field

from searchos.util.base_model import CamelModel


class SkillCategory(str, Enum):
    """The three skill kinds — values match the library subdirectory name."""
    STRATEGY = "strategy"          # 推理方法论（纯文字）
    ACCESS = "access"              # 数据获取方法（文字+可选代码）
    ORCHESTRATOR = "orchestrator"  # 编排方法论（任务拆分、广度收集、行级校验）


class SkillStatus(str, Enum):
    """Lifecycle: mined < seed < trial < active < optimized, with deprecated
    as the terminal off-ramp. ``mined`` is the access-skill baker's raw output
    — surfaced at lowest priority and excluded from promotion chains."""
    MINED = "mined"
    SEED = "seed"
    TRIAL = "trial"
    ACTIVE = "active"
    OPTIMIZED = "optimized"
    DEPRECATED = "deprecated"


class SkillMeta(CamelModel):
    """Metadata parsed from a skill's YAML frontmatter."""

    name: str = Field(validation_alias=AliasChoices("name", "skill_name"))
    description: str = ""
    category: SkillCategory = SkillCategory.STRATEGY
    trigger: str = ""  # flat retrieval hint
    status: SkillStatus = SkillStatus.SEED
    has_executor: bool = False


class Skill(CamelModel):
    """A loaded skill: metadata + body text.

    Anti-patterns live in a sibling ``anti_patterns.md`` that
    ``parse_skill_file`` loads into ``anti_patterns_index`` (one-line summaries
    for prompt injection) and ``anti_patterns_details`` (full entries, fetched
    on demand). Empty when the sibling file is missing."""

    meta: SkillMeta
    body: str
    file_path: str = ""
    anti_patterns_index: str = ""
    anti_patterns_details: list[dict[str, Any]] = Field(default_factory=list)
