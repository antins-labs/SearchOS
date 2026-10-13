"""Skill Availability compatibility and registry behavior."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from searchos.skills.catalog.registry import SkillRegistry
from searchos.skills.core.models import (
    Skill,
    SkillAvailability,
    SkillMeta,
)


@pytest.mark.parametrize(
    "legacy_status",
    ["mined", "seed", "trial", "active", "optimized"],
)
def test_legacy_lifecycle_statuses_load_as_enabled(legacy_status: str) -> None:
    meta = SkillMeta.model_validate(
        {"name": "legacy", "status": legacy_status},
    )

    assert meta.availability is SkillAvailability.ENABLED


def test_deprecated_status_loads_as_disabled() -> None:
    meta = SkillMeta.model_validate(
        {"name": "legacy", "status": "deprecated"},
    )

    assert meta.availability is SkillAvailability.DISABLED


def test_new_availability_values_are_explicit() -> None:
    assert (
        SkillMeta(name="enabled", availability="enabled").availability
        is SkillAvailability.ENABLED
    )
    assert (
        SkillMeta(name="disabled", availability="disabled").availability
        is SkillAvailability.DISABLED
    )
    with pytest.raises(ValidationError):
        SkillMeta.model_validate({"name": "broken", "status": "unknown"})


def _write_skill(directory: Path, name: str, status_line: str) -> None:
    skill_dir = directory / "strategy" / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "skill.md").write_text(
        f"""---
name: {name}
category: strategy
{status_line}
---
# {name}
""",
        encoding="utf-8",
    )


def test_registry_contains_only_enabled_skills(tmp_path: Path) -> None:
    _write_skill(tmp_path, "legacy_seed", "status: seed")
    _write_skill(tmp_path, "legacy_deprecated", "status: deprecated")
    _write_skill(tmp_path, "explicit_disabled", "availability: disabled")

    # 本测试只验证单个 Skill 的 availability，隔离本机按层停用配置。
    registry = SkillRegistry(all_disabled=False, disabled_layers=[])

    assert registry.load_directory(tmp_path) == 1
    assert [skill.meta.name for skill in registry.list_all()] == ["legacy_seed"]
    assert registry.get("legacy_deprecated") is None
    assert registry.get("explicit_disabled") is None
    assert "legacy_seed" in registry.generate_catalog()
    assert "legacy_deprecated" not in registry.generate_catalog()


def test_registry_rejects_disabled_registration() -> None:
    registry = SkillRegistry()
    disabled = Skill(
        meta=SkillMeta(name="disabled", availability="disabled"),
        body="disabled",
    )

    registry.register(disabled)

    assert registry.get("disabled") is None
