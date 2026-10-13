"""Web 创建意图到真实 pipeline 的合同测试，不依赖网络或用户技能库。"""
import asyncio
import json
import os
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from langchain_core.messages import AIMessage


@pytest.fixture
def modules(monkeypatch, tmp_path):
    monkeypatch.setattr(os, "environ", os.environ.copy())
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / 'web'))
    from api import skill_creation_jobs as module
    from api.routes import skills
    from searchos.config.settings import settings
    instance = module.CreationJobs(tmp_path / 'jobs')
    monkeypatch.setattr(skills, 'jobs', instance)
    monkeypatch.setattr(settings, 'skill_library_path', str(tmp_path / 'library'))
    return module, instance, skills


@pytest.mark.asyncio
async def test_api_intent_pipeline_publication_and_duplicate(modules, monkeypatch, tmp_path):
    module, jobs, routes = modules
    from fastapi import FastAPI
    from searchos.config import models
    class Model:
        async def ainvoke(self, messages):
            if isinstance(messages, str):
                return AIMessage(content=json.dumps([dict(category='orchestrator', name='split-sources',
                    description='按来源拆分检索任务')]))
            return AIMessage(content='---\nname: split-sources\ndescription: 按来源拆分检索任务\nmetadata:\n  searchos-category: orchestrator\n---\n先按来源派发独立任务，等待来源证据后合并；缺少关键字段则继续检索。')
    monkeypatch.setattr(models, 'get_model_for', lambda *a, **k: Model())
    app = FastAPI(); app.include_router(routes.router)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        payload = dict(kind='task', text='比较三个公司的年报，按来源拆解', categories=['orchestrator'])
        response = await client.post('/api/skills/creations', json=payload)
        assert response.status_code == 202
        job_id = response.json()['id']
        assert (await client.post('/api/skills/creations', json=payload)).json()['id'] == job_id
        await jobs.tasks[job_id]
        job = (await client.get('/api/skills/creations/' + job_id)).json()
        assert job['status'] == 'completed'
        assert job['requests'][0]['category'] == 'orchestrator'
        assert job['results'][0]['status'] == 'installed'
        assert (tmp_path / 'library/orchestrator/split-sources/SKILL.md').exists()
        assert len((await client.get('/api/skills/creations')).json()) == 1
        assert (await client.get('/api/skills/creations/bad')).status_code == 404
        again = (await client.post('/api/skills/creations', json=payload)).json()
        await jobs.tasks[again['id']]
        assert jobs.read(again['id'])['requests'] == []
        for invalid in [dict(kind='task', text=' '), dict(kind='site', site='file:///etc/passwd'),
                        dict(kind='site', site='https://user:pass@example.com'),
                        dict(kind='trace', text='trace', trace_path='/etc/passwd')]:
            assert (await client.post('/api/skills/creations', json=invalid)).status_code == 422


@pytest.mark.asyncio
async def test_partial_failure_and_recovery(modules, monkeypatch):
    module, jobs, _ = modules
    async def generate(*args, on_progress, **kwargs):
        await on_progress({'stage': 'planned', 'requests': [{'name': 'a'}, {'name': 'b'}]})
        await on_progress({'stage': 'result', 'index': 0, 'result': {'status': 'installed', 'name': 'a'}})
        await on_progress({'stage': 'result', 'index': 1, 'result': {'status': 'validation_failed', 'name': 'b', 'error': '证据不足'}})
        return [SimpleNamespace(status='installed'), SimpleNamespace(status='validation_failed')]
    monkeypatch.setattr(module, 'generate_skills', generate)
    job = jobs.create(module.CreationInput(kind='site', site='example.com'))
    await jobs.tasks[job['id']]
    assert jobs.read(job['id'])['status'] == 'partial'
    assert jobs.read(job['id'])['results'][1]['error'] == '证据不足'
    job['status'] = 'running'; jobs.write(job)
    jobs.recover()
    assert jobs.read(job['id'])['status'] == 'interrupted'


@pytest.mark.asyncio
async def test_shutdown_marks_queued_and_running_interrupted(modules, monkeypatch):
    module, jobs, _ = modules
    started = asyncio.Event()
    async def pending(*args, **kwargs):
        started.set()
        await asyncio.Event().wait()
    monkeypatch.setattr(module, 'generate_skills', pending)
    first = jobs.create(module.CreationInput(kind='site', site='example.com'))
    second = jobs.create(module.CreationInput(kind='site', site='example.org'))
    await started.wait()
    await jobs.stop()
    assert all(jobs.read(j['id'])['status'] == 'interrupted' for j in [first, second])


@pytest.mark.asyncio
async def test_standalone_requires_real_source_quotes(monkeypatch):
    from searchos.skills.pipeline.strategy import standalone
    class Browser:
        def __init__(self):
            self.state = SimpleNamespace(pages={})
        async def dispatch(self, name, args):
            self.state.pages['x'] = SimpleNamespace(url='https://example.com/report', text='Revenue 100')
            return {'content': 'Revenue 100'}
    monkeypatch.setattr(standalone, 'ResearchBrowser', Browser)
    class Model:
        def __init__(self, quote): self.turn = 0; self.quote = quote
        def bind_tools(self, tools): return self
        async def ainvoke(self, messages):
            self.turn += 1
            if self.turn == 1:
                assert '读取官方报告' in messages[0].content
                return AIMessage(content='', tool_calls=[dict(name='web_open', args={'id_or_url': 'https://example.com/report'}, id='one')])
            return AIMessage(content=json.dumps(dict(answer='100', evidence=[dict(claim='收入100', source='https://example.com/report', excerpt=self.quote)])))
    result = await standalone.run_standalone_subtask(subtask='收入多少', strategy='读取官方报告', model=Model('Revenue 100'))
    assert result['strategy_applied'] and result['sources'][0]['text'] == 'Revenue 100'
    with pytest.raises(ValueError, match='实际打开'):
        await standalone.run_standalone_subtask(subtask='收入多少', strategy='读取官方报告', model=Model('Revenue 999'))

@pytest.mark.asyncio
async def test_access_failure_keeps_diagnostics_without_publication(tmp_path, monkeypatch):
    from searchos.skills import SkillRequest, run_pipeline
    from searchos.skills.pipeline.access import run
    async def blocked(**kwargs):
        kwargs['diagnostics'].update(valid=False, stage='authentication', auth_required=True,
                                     error='需要手动登录')
        return None
    monkeypatch.setattr(run, 'build_skill', blocked)
    result = await run_pipeline(SkillRequest('access', 'example-com', '读取数据', host='example.com',
        probe_urls=('https://example.com',)), library_path=tmp_path / 'library', trial_root=tmp_path / 'trials')
    assert result.status == 'build_failed' and '需要手动登录' in result.error
    assert json.loads(result.trial_path.read_text())['diagnostics']['auth_required']
    assert not (tmp_path / 'library/access/example-com').exists()
