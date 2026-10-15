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


def source(name, description='test', **kwargs):
    return Skill(meta=SkillMeta(name=name, description=description, category='access', **kwargs), body='instructions')


@pytest.mark.asyncio
async def test_semantic_discovery_filters_before_model_and_preserves_ranking(monkeypatch):
    from searchos.config import models
    from searchos.config.settings import settings
    from searchos.skills.catalog.registry import SkillRegistry
    reg = SkillRegistry()
    for skill in [source('alpha', 'Historical prices'), source('beta', 'Daily candles'),
                  source('denied', 'private denied source'), source('banned', 'failed source'),
                  source('out-of-scope', 'private excluded source')]:
        reg.register(skill)
    calls = []
    class Model:
        async def ainvoke(self, messages):
            calls.append(messages)
            text = messages[-1].content
            assert '最近一个月股价' in text and 'Historical prices' in text
            assert all(name not in text for name in ['denied', 'banned', 'out-of-scope'])
            return SimpleNamespace(content=json.dumps({'skills': [
                {'name':'beta','reason':'Daily records fit the need'},
                {'name':'denied','reason':'invented'}, {'name':'beta'}, {'name':'alpha','reason':'History'}]}))
    monkeypatch.setattr(models, 'get_model_for', lambda role: Model())
    monkeypatch.setattr(settings, 'enable_skills', True)
    monkeypatch.setattr(settings, 'enable_skill_router', True)
    monkeypatch.setattr(catalog, '_registry', lambda: reg)
    monkeypatch.setattr(catalog, '_banned_skills_from_state', lambda: {'banned'})
    token = catalog._skill_access_policy_var.set({'access_only': {'alpha','beta','denied','banned'}, 'access_deny': {'denied'}})
    try:
        page = json.loads(await catalog.list_skills.ainvoke({'query':'最近一个月股价','limit':1}))
        assert [s['name'] for s in page['skills']] == ['beta']
        assert page['skills'][0]['match_reason'] == 'Daily records fit the need'
        assert page['next_offset'] == 1
        second = json.loads(await catalog.list_skills.ainvoke({'query':'最近一个月股价','offset':1,'limit':1}))
        assert second['skills'][0]['name'] == 'alpha'
        assert len(calls) == 1
        catalog._skill_access_policy_var.set({'access_only': {'alpha'}})
        narrowed = json.loads(await catalog.list_skills.ainvoke({'query':'最近一个月股价'}))
        assert [s['name'] for s in narrowed['skills']] == ['alpha']
        assert len(calls) == 2
    finally:
        catalog._skill_access_policy_var.reset(token)


@pytest.mark.asyncio
async def test_discovery_cache_changes_with_catalog_and_returns_copies():
    from searchos.skills.catalog.router import discover_skills
    skill = source('history', 'Historical prices')
    calls = []
    class Model:
        async def ainvoke(self, messages):
            calls.append(messages)
            return SimpleNamespace(content='{"skills":[{"name":"history","reason":"dates supported"}]}')
    cache = {}
    first = await discover_skills('prices', [skill], model=Model(), cache=cache)
    first[0]['name'] = 'tampered'
    second = await discover_skills('prices', [skill], model=Model(), cache=cache)
    assert second[0]['name'] == 'history' and len(calls) == 1
    skill.meta.description = 'Only current quotes; history removed'
    await discover_skills('prices', [skill], model=Model(), cache=cache)
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_exact_source_and_browse_do_not_call_model(monkeypatch):
    from searchos.config import models
    from searchos.skills.catalog.router import discover_skills
    def forbidden(*args, **kwargs): raise AssertionError('no model needed')
    monkeypatch.setattr(models, 'get_model_for', forbidden)
    skills = [source('history', metadata={'host':'example.com'})]
    for query in ['history', 'example.com', 'https://example.com/data']:
        assert (await discover_skills(query, skills))[0]['name'] == 'history'
    monkeypatch.setattr(catalog, '_registry', lambda: SimpleNamespace(list_all=lambda: skills))
    monkeypatch.setattr(catalog, '_banned_skills_from_state', lambda: set())
    assert json.loads(await catalog.list_skills.ainvoke({}))['skills'][0]['name'] == 'history'


@pytest.mark.asyncio
@pytest.mark.parametrize('content', ['unparseable', '{"skills":[{"name":"invented"}]}'])
async def test_discovery_failure_is_not_an_arbitrary_fallback(monkeypatch, content):
    from searchos.config import models
    from searchos.config.settings import settings
    class Model:
        async def ainvoke(self, messages): return SimpleNamespace(content=content)
    monkeypatch.setattr(models, 'get_model_for', lambda role: Model())
    monkeypatch.setattr(settings, 'enable_skill_router', True)
    monkeypatch.setattr(catalog, '_registry', lambda: SimpleNamespace(list_all=lambda: [source('alpha')]))
    monkeypatch.setattr(catalog, '_banned_skills_from_state', lambda: set())
    result = json.loads(await catalog.list_skills.ainvoke({'query':'some data need'}))
    assert result['skills'] == [] and result['error'] == 'skill_discovery_failed'
