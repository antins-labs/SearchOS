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
    from api.skills import creation as module
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


def seed_record(module, jobs, identifier, *, status='failed', **fields):
    job = dict(id=identifier, input=module.CreationInput(kind='site', site='example.com').model_dump(),
               status=status, stage='done', requests=[], results=[], current_index=None,
               error='', created_at=module.now(), **fields)
    jobs.write(job)
    return job


@pytest.mark.asyncio
async def test_delete_records_cleans_owned_trials_but_keeps_library_and_other_runs(modules, tmp_path):
    from fastapi import FastAPI
    module, jobs, routes = modules
    installed = tmp_path/'library/access/example-com/SKILL.md'
    installed.parent.mkdir(parents=True); installed.write_text('installed skill')
    first, second = 'a'*32, 'b'*32
    seed_record(module, jobs, first, status='completed')
    seed_record(module, jobs, second)
    for identifier in [first, second]:
        trial = jobs.root/'trials'/identifier
        trial.mkdir(parents=True); (trial/'draft.json').write_text('draft')
    # 即使记录中的结果指向库或其他目录，删除范围仍只由作业 ID 决定。
    record = jobs.read(first)
    record['results'] = [{'status':'installed', 'path':str(installed.parent), 'trial_path':str(tmp_path)}]
    jobs.write(record)
    app = FastAPI(); app.include_router(routes.router)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        response = await client.delete('/api/skills/creations/'+first)
        assert response.status_code == 200 and response.json()['deleted'] == [first]
        assert not jobs.path(first).exists() and not (jobs.root/'trials'/first).exists()
        assert installed.read_text() == 'installed skill'
        assert jobs.read(second)['id'] == second and (jobs.root/'trials'/second/'draft.json').exists()
        assert (await client.get('/api/skills/creations/'+first)).status_code == 404
        assert (await client.delete('/api/skills/creations/'+first)).status_code == 404
        assert (await client.post('/api/skills/creations/delete', json={'ids':[]})).status_code == 422
        assert (await client.post('/api/skills/creations/delete', json={'ids':['../outside']})).status_code == 409
        response = await client.post('/api/skills/creations/delete', json={'ids':[second, second]})
        assert response.json()['deleted'] == [second]
        jobs.recover()
        assert jobs.list() == []


@pytest.mark.asyncio
async def test_bulk_delete_preflights_active_jobs_and_resume_dependencies(modules):
    module, jobs, _ = modules
    parent, child, other = 'a'*32, 'b'*32, 'c'*32
    seed_record(module, jobs, parent)
    seed_record(module, jobs, child, status='running', resume_of={'job_id':parent,'index':0})
    seed_record(module, jobs, other)
    for ids in ([other, child], [other, parent]):
        with pytest.raises(ValueError, match='停止'):
            jobs.delete(ids)
        assert all(jobs.path(i).exists() for i in [parent, child, other])
    current = jobs.read(child); current['status'] = 'failed'; jobs.write(current)
    assert jobs.delete([parent, child]) == [parent, child]
    assert jobs.read(other)['id'] == other


def test_delete_rejects_symlink_trial_directory(modules, tmp_path):
    module, jobs, _ = modules
    identifier = 'a'*32
    seed_record(module, jobs, identifier)
    outside = tmp_path/'outside'; outside.mkdir(); (outside/'keep').write_text('keep')
    (jobs.root/'trials').mkdir()
    (jobs.root/'trials'/identifier).symlink_to(outside)
    with pytest.raises(ValueError, match='目录异常'): jobs.delete([identifier])
    assert jobs.path(identifier).exists() and (outside/'keep').read_text() == 'keep'


@pytest.mark.asyncio
async def test_cancel_queued_and_running_jobs_before_deleting(modules, monkeypatch):
    from fastapi import FastAPI
    module, jobs, routes = modules
    started = asyncio.Event()
    async def pending(*args, **kwargs):
        started.set()
        await asyncio.Event().wait()
    monkeypatch.setattr(module, 'generate_skills', pending)
    first = jobs.create(module.CreationInput(kind='site', site='example.com'))
    second = jobs.create(module.CreationInput(kind='site', site='example.org'))
    await started.wait()
    app = FastAPI(); app.include_router(routes.router)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        for job in [second, first]:
            identifier = job['id']
            assert (await client.delete('/api/skills/creations/'+identifier)).status_code == 409
            stopped = await client.post(f'/api/skills/creations/{identifier}/cancel')
            assert stopped.status_code == 200
            assert stopped.json()['status'] == 'interrupted'
            assert '用户已停止' in stopped.json()['error']
            assert (await client.post(f'/api/skills/creations/{identifier}/cancel')).status_code == 200
            assert (await client.delete('/api/skills/creations/'+identifier)).status_code == 200
        await asyncio.sleep(0)
        assert not jobs.tasks and jobs.list() == []


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


@pytest.mark.asyncio
async def test_draft_editor_and_resume_skip_intent(modules, monkeypatch, tmp_path):
    from dataclasses import asdict
    from fastapi import FastAPI
    from searchos.skills import SkillRequest
    from searchos.skills.pipeline.drafts import save_draft, load_draft
    from searchos.skills.pipeline.run import PipelineResult
    module, jobs, routes = modules
    job_id = 'a' * 32
    request = SkillRequest('access', 'example-com', '获取真实数据', host='example.com', probe_urls=('https://example.com/',))
    source = tmp_path / 'source'; source.mkdir()
    (source / 'SKILL.md').write_text('original draft')
    record = jobs.root / 'trials' / job_id / request.name / 'first'
    pointer = save_draft(record, source, ['SKILL.md'], name=request.name, examples=[], require_host=True,
                         validation={'valid': False, 'stage': 'package', 'error': 'missing metadata'})
    (record / 'request.json').write_text(json.dumps(dict(request=asdict(request), base_hash=None)))
    parent = dict(id=job_id, input=module.CreationInput(kind='site', site='example.com').model_dump(),
                  requests=[asdict(request)], results=[], status='failed', stage='done', error='',
                  created_at=module.now(), drafts={'0': str(pointer)})
    jobs.write(parent)
    async def forbidden(*args, **kwargs): raise AssertionError('resume must not rerun intent')
    monkeypatch.setattr(module, 'generate_skills', forbidden)
    started, finish = asyncio.Event(), asyncio.Event()
    async def pipeline(selected, *, resume_draft, trial_root, on_draft, **kwargs):
        assert selected == request
        package, data = load_draft(resume_draft)
        assert (package / 'SKILL.md').read_text() == 'edited draft'
        new_pointer = save_draft(trial_root / selected.name / 'next', package, data['files'],
            name=selected.name, examples=[], require_host=True, validation={'valid': False, 'stage': 'examples'})
        await on_draft(new_pointer)
        started.set(); await finish.wait()
        return PipelineResult(selected, 'build_failed', error='authentication needed', draft_path=new_pointer)
    monkeypatch.setattr(module, 'run_pipeline', pipeline)
    app = FastAPI(); app.include_router(routes.router)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        url = f'/api/skills/creations/{job_id}/requests/0'
        assert jobs.read(job_id)['requests'][0]['has_draft']
        draft = (await client.get(url + '/draft')).json()
        assert draft['validation']['error'] == 'missing metadata'
        original = (await client.get(url + '/draft/file', params={'path': 'SKILL.md'})).json()
        edit = dict(path='SKILL.md', content='edited draft', revision=original['revision'])
        response = await client.put(url + '/draft/file', json=edit)
        assert response.status_code == 200
        assert response.json()['revision'] != original['revision']
        assert response.json()['validation']['stage'] == 'edited'
        assert (record / original['revision'] / 'SKILL.md').read_text() == 'original draft'
        assert (await client.put(url + '/draft/file', json=edit)).status_code == 409
        assert (await client.get(url + '/draft/file', params={'path': '../../outside'})).status_code == 400
        child = (await client.post(url + '/resume')).json()
        await started.wait()
        assert child['resume_of'] == {'job_id': job_id, 'index': 0}
        assert (await client.post(url + '/resume')).json()['id'] == child['id']
        assert (await client.put(url + '/draft/file', json=edit)).status_code == 409
        active_url = f"/api/skills/creations/{child['id']}/requests/0"
        assert (await client.get(active_url + '/draft')).status_code == 200
        assert (await client.put(active_url + '/draft/file', json=edit)).status_code == 409
        finish.set(); await jobs.tasks[child['id']]
        saved = jobs.read(child['id'])
        assert saved['status'] == 'failed' and saved['requests'][0]['has_draft']
        jobs.recover()
        assert (await client.get(active_url + '/draft')).json()['validation']['stage'] == 'examples'


def seed_site_session(module, jobs, identifier='a' * 32):
    from dataclasses import asdict
    from searchos.skills import SkillRequest
    request = SkillRequest('access', 'example-com', '读取站点新闻', host='example.com',
                           probe_urls=('https://example.com/news',))
    record = jobs.root / 'trials' / identifier / request.name / 'first'
    record.mkdir(parents=True)
    (record / 'request.json').write_text(json.dumps(dict(request=asdict(request), base_hash=None,
                                                       access_site_intent=True)))
    session = dict(version=1, host=request.host, calls=8, plan=None, dialogues=[],
                   observations=[dict(id='obs-1', usable=True, result={'content': '已有站点研究'})],
                   last_proposal={'capabilities': [{'id': 'news', 'inputs': {}}]})
    (record / 'site-session.json').write_text(json.dumps(session))
    job = dict(id=identifier, input=module.CreationInput(kind='site', site='example.com/news').model_dump(),
               requests=[asdict(request)], results=[dict(name=request.name, category='access', status='error',
                    error='site intent call budget exhausted', failure_stage='site_intent',
                    trial_path=str(record / 'result.json'))], status='failed', stage='done', error='',
               current_index=None, created_at=module.now(), drafts={'0': str(record / 'draft.json')})
    jobs.write(job)
    return job, request, record, session


@pytest.mark.asyncio
async def test_site_session_resume_preserves_research_without_draft(modules, monkeypatch):
    from fastapi import FastAPI
    from searchos.skills.pipeline.run import PipelineResult
    module, jobs, routes = modules
    parent, request, record, session = seed_site_session(module, jobs)
    original = jobs.path(parent['id']).read_bytes()
    async def forbidden(*args, **kwargs):
        raise AssertionError('恢复研究不能重新分析原始创建信号')
    monkeypatch.setattr(module, 'generate_skills', forbidden)
    started, finish = asyncio.Event(), asyncio.Event()
    async def pipeline(selected, *, access_site_intent, access_site_session, trial_root, on_draft, on_stage, **kwargs):
        assert selected == request and access_site_intent is True
        assert 'resume_draft' not in kwargs
        assert access_site_session.is_relative_to(trial_root)
        assert json.loads(access_site_session.read_text()) == session
        current = trial_root / selected.name / 'next'
        current.mkdir(parents=True)
        (current / 'request.json').write_bytes((record / 'request.json').read_bytes())
        (current / 'site-session.json').write_text(json.dumps({**session, 'calls': 10}))
        await on_draft(current / 'draft.json')
        await on_stage('site_intent')
        started.set()
        await finish.wait()
        await on_stage('pipeline')
        assert jobs.read(trial_root.name)['stage'] == 'pipeline'
        return PipelineResult(selected, 'error', error='仍需补充计划', trial_path=current / 'result.json')
    monkeypatch.setattr(module, 'run_pipeline', pipeline)
    app = FastAPI(); app.include_router(routes.router)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        url = f"/api/skills/creations/{parent['id']}/requests/0"
        state = jobs.read(parent['id'])['requests'][0]
        assert state['has_site_session'] and state['can_resume'] and not state['has_draft']
        assert (await client.get(url + '/draft')).status_code == 404
        response = await client.post(url + '/resume')
        assert response.status_code == 202
        child = response.json()
        assert child['resume_kind'] == 'site_session'
        await started.wait()
        assert jobs.read(child['id'])['stage'] == 'site_intent'
        assert (await client.post(url + '/resume')).json()['id'] == child['id']
        finish.set(); await jobs.tasks[child['id']]
        resumed = jobs.read(child['id'])
        assert resumed['requests'][0]['can_resume'] and not resumed['requests'][0]['has_draft']
        assert json.loads(jobs.site_session_pointer(resumed, 0).read_text())['calls'] == 10
        assert jobs.path(parent['id']).read_bytes() == original
        assert json.loads((record / 'site-session.json').read_text()) == session


@pytest.mark.asyncio
async def test_site_session_queued_resume_survives_cancellation_and_parent_deletion(modules, monkeypatch):
    module, jobs, _ = modules
    parent, _, _, session = seed_site_session(module, jobs)
    async def forbidden(*args, **kwargs):
        raise AssertionError('排队时不得开始模型调用')
    monkeypatch.setattr(module, 'run_pipeline', forbidden)
    await jobs.lock.acquire()
    try:
        child = jobs.resume(parent['id'], 0)
        await jobs.cancel(child['id'])
    finally:
        jobs.lock.release()
    jobs.delete([parent['id']])
    jobs.recover()
    saved = jobs.read(child['id'])
    assert saved['status'] == 'interrupted' and saved['requests'][0]['can_resume']
    assert json.loads(jobs.site_session_pointer(saved, 0).read_text()) == session


@pytest.mark.parametrize('invalid', ['other_job', 'symlink', 'request', 'host', 'version', 'mode', 'malformed'])
def test_site_session_resume_rejects_unbound_or_invalid_record(modules, tmp_path, invalid):
    module, jobs, _ = modules
    job, _, record, _ = seed_site_session(module, jobs)
    if invalid == 'other_job':
        _, _, other, _ = seed_site_session(module, jobs, 'b' * 32)
        job['drafts']['0'] = str(other / 'draft.json')
        jobs.write(job)
    elif invalid == 'symlink':
        original = record / 'site-session.json'
        outside = tmp_path / 'outside.json'
        outside.write_bytes(original.read_bytes()); original.unlink(); original.symlink_to(outside)
    elif invalid in {'request', 'mode'}:
        path = record / 'request.json'; data = json.loads(path.read_text())
        if invalid == 'request': data['request']['description'] = '另一项需求'
        else: data['access_site_intent'] = False
        path.write_text(json.dumps(data))
    else:
        path = record / 'site-session.json'; data = json.loads(path.read_text())
        if invalid == 'malformed': path.write_text('not json')
        else:
            data[invalid] = 'other.example' if invalid == 'host' else 999
            path.write_text(json.dumps(data))
    assert not jobs.read(job['id'])['requests'][0]['can_resume']
    with pytest.raises(ValueError):
        jobs.resume(job['id'], 0)
