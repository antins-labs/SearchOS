"""外部信号 → 请求 → 分类生成 → 校验入库。"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage

from searchos.skills import SkillSignal, SkillRequest, infer_requests, run_pipeline, generate_skills
from searchos.skills.intent.trace import _existing_skill_dir
from searchos.skills.packaging import validate_package


def trace(tmp_path):
    path = tmp_path / 'trajectory.jsonl'
    path.write_text('\n'.join(json.dumps({'type':'step','action':{'name':'open','args':'1'},
       'observation':f'URL: https://example.com/{suffix}\nstructured data',
       'state_delta':{'new_evidence_count':0}}) for suffix in ['a','b']))
    return path


def markdown(request, body='具体方法：先检索原始来源，再核验关键字段。'):
    host = f'  host: {request.host}\n' if request.host else ''
    return f'---\nname: {request.name}\ndescription: {request.description}\nmetadata:\n  searchos-category: {request.category.value}\n{host}---\n{body}\n'


@pytest.mark.asyncio
async def test_search_trace_returns_normalized_access_requests(tmp_path):
    class Selector:
        async def ainvoke(self, prompt):
            return SimpleNamespace(content=json.dumps([
                {'host':'EXAMPLE.COM','probe_urls':[],'reason':'repeatable records'},
                {'host':'not-opened.example','probe_urls':['https://not-opened.example/a'],'reason':'hallucinated'}]))
    requests = await infer_requests(SkillSignal('trace', trace_path=trace(tmp_path)), model=Selector(),
                                    library_path=tmp_path/'library', categories=('access',))
    assert requests == [SkillRequest('access','example-com','从 example.com 获取结构化记录',
                                     reason='repeatable records',host='example.com',
                                     probe_urls=('https://example.com/a','https://example.com/b'))]


@pytest.mark.asyncio
@pytest.mark.parametrize('kind',['task','trace'])
async def test_signal_can_produce_multiple_categories_and_deduplicates(kind, tmp_path):
    class Selector:
        async def ainvoke(self, prompt):
            assert '外部信号' in prompt
            requests = [{'category':'strategy','name':'verify-records','description':'核验记录'},
                        {'category':'orchestrator','name':'split-source-tasks','description':'按来源拆分任务'}]
            return AIMessage(content=json.dumps(requests+[requests[0]]))
    requests = await infer_requests(SkillSignal(kind,text='反复检索无效，需要来源任务拆分与关键字段核验'),
                                    model=Selector(), library_path=tmp_path, max_requests=3)
    assert [r.category.value for r in requests] == ['strategy','orchestrator']
    assert not list(tmp_path.iterdir())  # Intent never writes skill assets.


@pytest.mark.asyncio
async def test_existing_host_and_name_are_filtered(tmp_path):
    request=SkillRequest('access','example-com','来源检索',host='example.com',probe_urls=('https://example.com/a',))
    package=tmp_path/'access/example-com';package.mkdir(parents=True)
    (package/'SKILL.md').write_text(markdown(request))
    assert _existing_skill_dir(tmp_path/'access','example.com') == package
    assert not await infer_requests(SkillSignal('trace',trace_path=trace(tmp_path)),
                                     library_path=tmp_path,categories=('access',))


@pytest.mark.asyncio
@pytest.mark.parametrize('category',['orchestrator'])
async def test_text_pipeline_validates_then_installs(category,tmp_path):
    request=SkillRequest(category,'reusable-method','可复用方法')
    class Model:
        calls=0
        async def ainvoke(self,messages):
            self.calls+=1
            if self.calls==1:return AIMessage(content='invalid markdown')
            assert '校验失败' in messages[-1].content
            return AIMessage(content=markdown(request))
    result=await run_pipeline(request,library_path=tmp_path,model=Model())
    assert result.status=='installed'
    assert result.path==tmp_path/category/request.name
    assert validate_package(result.path).meta.category.value==category
    assert not list((tmp_path/category).glob('.pipeline*'))


@pytest.mark.asyncio
async def test_access_pipeline_receives_request_and_checks_host(tmp_path,monkeypatch):
    from searchos.skills.pipeline.access import run as access
    request=SkillRequest('access','example-com','来源检索',reason='多次访问失败',host='example.com',probe_urls=('https://example.com/a',))
    calls=[]
    async def builder(**kwargs):
        calls.append(kwargs)
        package=kwargs['output_dir'];package.mkdir(parents=True)
        (package/'SKILL.md').write_text(markdown(request))
        (package/'scripts').mkdir();(package/'scripts/search.py').write_text('print(1)')
        return package
    monkeypatch.setattr(access,'build_skill',builder)
    result=await run_pipeline(request,library_path=tmp_path,model=object())
    assert result.status=='installed'
    assert calls[0]['host']=='example.com'
    assert calls[0]['probe_urls']==['https://example.com/a']
    assert '来源检索' in calls[0]['notes'] and '多次访问失败' in calls[0]['notes']


@pytest.mark.asyncio
async def test_invalid_build_does_not_replace_installed_skill(tmp_path,monkeypatch):
    from searchos.skills.pipeline.access import run as access
    request=SkillRequest('access','example-com','来源检索',host='example.com',probe_urls=('https://example.com/a',))
    previous=tmp_path/'access/example-com';previous.mkdir(parents=True)
    (previous/'SKILL.md').write_text(markdown(request,'已安装的方法'))
    async def invalid(**kwargs):
        package=kwargs['output_dir'];package.mkdir(parents=True)
        (package/'SKILL.md').write_text('broken')
        return package
    monkeypatch.setattr(access,'build_skill',invalid)
    result=await run_pipeline(request,library_path=tmp_path)
    assert result.status=='error'
    assert '已安装的方法' in (previous/'SKILL.md').read_text()


@pytest.mark.asyncio
async def test_generate_routes_batch_and_continues_after_one_failure(tmp_path,monkeypatch):
    from searchos.skills.pipeline.access import run as access
    async def failed(**kwargs):return None
    monkeypatch.setattr(access,'build_skill',failed)
    requests=[{'category':'access','name':'example-com','description':'来源获取','host':'example.com','probe_urls':['https://example.com/a']},
              {'category':'orchestrator','name':'verify-results','description':'核验结果'}]
    class Selector:
        async def ainvoke(self,prompt):return AIMessage(content=json.dumps(requests))
    class Builder:
        async def ainvoke(self,messages):return AIMessage(content=markdown(SkillRequest('orchestrator','verify-results','核验结果')))
    results=await generate_skills(SkillSignal('task',text='检索并核验记录'),library_path=tmp_path,
                                  intent_model=Selector(),builder_model=Builder())
    assert [r.status for r in results]==['build_failed','installed']
    assert results[1].to_report()['category']=='orchestrator'


@pytest.mark.parametrize('kwargs',[
    {'category':'access','name':'bad-name','description':'x'},
    {'category':'access','name':'bad-name','description':'x','host':'example.com','probe_urls':('../file',)},
    {'category':'strategy','name':'../escape','description':'x'},
])
def test_invalid_requests_are_rejected(kwargs):
    with pytest.raises(ValueError):SkillRequest(**kwargs)


@pytest.mark.asyncio
async def test_site_intent_creates_access_request_without_selection_model(tmp_path):
    requests = await infer_requests(SkillSignal('site',host='EXAMPLE.COM',text='查询站点记录'), library_path=tmp_path)
    assert requests == [SkillRequest('access','example-com','从 example.com 获取结构化记录',
                                     reason='查询站点记录',host='example.com',probe_urls=('https://example.com/',))]
    assert not await infer_requests(SkillSignal('site',host='example.com'), categories=('strategy',))


@pytest.mark.asyncio
@pytest.mark.parametrize('planning_fails', [False, True])
async def test_site_progress_tracks_planning_before_builder_starts(tmp_path, monkeypatch, planning_fails):
    from searchos.skills.pipeline.access import run as access
    events = []
    class Model:
        def bind_tools(self, definitions): return self
    class Session:
        def __init__(self, *args): self.state = {'calls': 0, 'dialogues': []}
        async def prepare(self, *args, **kwargs):
            assert events[-1] == 'site_intent'
            events.append('prepare')
            if planning_fails:
                raise ValueError('invalid capability plan')
            return {'capabilities': [{'id': 'latest', 'inputs': {}, 'examples': [{}],
                                      'required_fields': ['title', 'source_url']}], 'limitations': []}
        def builder_notes(self): return ''
    async def build(*args, **kwargs):
        assert events[-1] == 'pipeline'
        events.append('build')
        return None
    async def progress(event): events.append(event['stage'])
    monkeypatch.setattr('searchos.skills.intent.site.SiteIntentSession', Session)
    monkeypatch.setattr(access, '_build_episode', build)
    results = await generate_skills(SkillSignal('site', host='example.com'), library_path=tmp_path/'library',
                                   builder_model=Model(), on_progress=progress)
    assert events[:2] == ['intent', 'planned']
    assert events[-1] == 'result'
    if planning_fails:
        assert 'pipeline' not in events and 'build' not in events
        assert results[0].failure_stage == 'site_intent'
    else:
        assert events.index('prepare') < events.index('pipeline') < events.index('build')


@pytest.mark.asyncio
async def test_task_intent_covers_all_needed_requests_by_default_and_reuses_existing(tmp_path):
    existing=SkillRequest('strategy','existing-method','已有的记录核验能力')
    package=tmp_path/'strategy/existing-method';package.mkdir(parents=True)
    (package/'SKILL.md').write_text(markdown(existing))
    class Selector:
        async def ainvoke(self,prompt):
            assert '已有的记录核验能力' in prompt and '不设固定数量上限' in prompt
            requests=[{'category':'strategy','name':'existing-method','description':'已有的记录核验能力'}]
            requests += [{'category':'strategy','name':f'method-{i}','description':f'需要的方法 {i}'} for i in range(4)]
            return AIMessage(content=json.dumps(requests))
    requests=await infer_requests(SkillSignal('task',text='解决任务需要多个方法'),model=Selector(),library_path=tmp_path)
    assert len(requests)==4
    assert [r.name for r in requests]==['method-0','method-1','method-2','method-3']
