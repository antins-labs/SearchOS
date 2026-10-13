import json
from types import SimpleNamespace

import pytest

from searchos.skills.core.models import Skill, SkillMeta
from searchos.tools import skill_catalog as catalog


def test_fixed_surface_does_not_depend_on_dispatched_skill_names():
    names = {tool.name for tool in catalog.get_skill_tools(["nonexistent"])}
    assert names == {"list_skills", "load_skill", "load_anti_patterns", "exec", "read_skill_file"}
    assert "tool_call_id" not in next(tool for tool in catalog.get_skill_tools() if tool.name == "exec").tool_call_schema.model_fields


@pytest.mark.asyncio
async def test_discovery_is_bounded_and_obeys_explicit_access_scope(monkeypatch):
    from searchos.config.settings import settings
    monkeypatch.setattr(settings, "enable_skills", True)
    skills = [Skill(meta=SkillMeta(name=f"source-{i}", description="test", category="access"), body="instructions") for i in range(60)]
    monkeypatch.setattr(catalog, "_registry", lambda: SimpleNamespace(list_all=lambda: skills))
    monkeypatch.setattr(catalog, "_banned_skills_from_state", lambda: set())
    token = catalog._skill_access_policy_var.set({})
    try:
        result = json.loads(await catalog.list_skills.ainvoke({"limit": 1000}))
        assert len(result["skills"]) == 50
        assert result["next_offset"] == 50
        catalog._skill_access_policy_var.set({"access_only": {"source-1", "source-2"}, "access_deny": {"source-2"}})
        result = json.loads(await catalog.list_skills.ainvoke({}))
        assert [skill["name"] for skill in result["skills"]] == ["source-1"]
    finally:
        catalog._skill_access_policy_var.reset(token)
