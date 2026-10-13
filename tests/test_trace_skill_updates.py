"""轨迹驱动三类技能生成、显式更新与失败保护。"""
import json
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage

from searchos.skills import SkillRequest, SkillSignal, generate_from_trace, infer_requests, run_pipeline


def install(root, category='orchestrator', name='existing-method'):
    package = root / category / 'nested' / name
    package.mkdir(parents=True)
    host = '  host: example.com\n' if category == 'access' else ''
    text = f'---\nname: {name}\ndescription: 已有能力\nmetadata:\n  searchos-category: {category}\n{host}---\n保留原有能力'
    (package / 'SKILL.md').write_text(text)
    (package / 'references').mkdir()
    (package / 'references/notes.md').write_text('原有参考')
    return package


@pytest.mark.asyncio
async def test_trace_infers_create_and_update_without_dropping_existing_host(tmp_path):
    install(tmp_path, 'access')
    class Selector:
        async def ainvoke(self, prompt):
            assert '保留原有能力' in prompt
            return AIMessage(content=json.dumps([
                dict(action='update', category='access', name='existing-method', description='补充分页',
                     reason='轨迹显示第二页未获取', host='example.com', probe_urls=['https://example.com/']),
                dict(category='strategy', name='search-method', description='检索方法', subtask='查明收入'),
                dict(category='orchestrator', name='split-method', description='拆分方法'),
            ]))
    requests = await infer_requests(SkillSignal('trace', text='example.com 第二页缺失'),
                                    model=Selector(), library_path=tmp_path)
    assert [r.category.value for r in requests] == ['access', 'strategy', 'orchestrator']
    assert requests[0].action == 'update'


@pytest.mark.asyncio
async def test_post_run_uses_all_categories_and_independent_strategy_runner(tmp_path, monkeypatch):
    import searchos.skills as skills
    from searchos.skills.pipeline.strategy.standalone import run_standalone_subtask
    calls = []
    async def capture(signal, **kwargs):
        calls.append((signal, kwargs))
        return []
    monkeypatch.setattr(skills, 'generate_skills', capture)
    await generate_from_trace(tmp_path/'trajectory.jsonl', library_path=tmp_path, max_requests=3)
    signal, options = calls[0]
    assert signal.kind == 'trace' and signal.trace_path == tmp_path/'trajectory.jsonl'
    assert options['categories'] == ('access', 'strategy', 'orchestrator')
    assert options['subtask_runner'] is run_standalone_subtask
    assert options['max_requests'] == 3


@pytest.mark.asyncio
async def test_update_reads_old_body_preserves_resources_and_original_location(tmp_path):
    package = install(tmp_path)
    old = (package/'SKILL.md').read_text()
    class Builder:
        async def ainvoke(self, messages):
            assert old in json.loads(messages[1].content)['existing_skill']
            return AIMessage(content=old+'\n增加失败后的补派步骤')
    result = await run_pipeline(SkillRequest('orchestrator','existing-method','补派方法',
        reason='轨迹存在未派发缺口',action='update'), library_path=tmp_path, model=Builder())
    assert result.status == 'installed' and result.path == package
    assert result.to_report()['action'] == 'update'
    assert '补派步骤' in (package/'SKILL.md').read_text()
    assert (package/'references/notes.md').read_text() == '原有参考'
    assert not (tmp_path/'orchestrator/existing-method').exists()


@pytest.mark.asyncio
async def test_update_detects_changed_installed_version(tmp_path):
    package = install(tmp_path)
    old = (package/'SKILL.md').read_text()
    class Builder:
        async def ainvoke(self, messages):
            (package/'SKILL.md').write_text(old+'\n其他更新')
            return AIMessage(content=old+'\n候选更新')
    result = await run_pipeline(SkillRequest('orchestrator','existing-method','新能力',
        reason='缺口',action='update'), library_path=tmp_path, model=Builder())
    assert result.status == 'error' and 'changed during validation' in result.error
    assert (package/'SKILL.md').read_text().endswith('其他更新')


@pytest.mark.asyncio
async def test_access_update_seeds_existing_package_and_failure_keeps_it(tmp_path, monkeypatch):
    from searchos.skills.pipeline.access import run
    package = install(tmp_path, 'access')
    old = (package/'SKILL.md').read_text()
    async def failed(**kwargs):
        assert kwargs['existing_package'] == package
        return None
    monkeypatch.setattr(run, 'build_skill', failed)
    result = await run_pipeline(SkillRequest('access','existing-method','补充分页',reason='第二页缺失',
        action='update',host='example.com',probe_urls=('https://example.com/',)), library_path=tmp_path)
    assert result.status == 'build_failed'
    assert (package/'SKILL.md').read_text() == old


@pytest.mark.asyncio
async def test_update_missing_target_is_rejected(tmp_path):
    request = SkillRequest('strategy','missing-method','方法',reason='缺口',action='update')
    result = await run_pipeline(request, library_path=tmp_path)
    assert result.status == 'error' and 'does not exist' in result.error


@pytest.mark.asyncio
async def test_trace_subtask_does_not_inherit_parent_task(tmp_path, monkeypatch):
    import searchos.skills as skills
    from searchos.tools.search_state import _current_task_var
    from searchos.skills.pipeline.run import PipelineResult
    async def infer(*args, **kwargs):
        return [SkillRequest('strategy','method','方法',subtask='轨迹中的子任务')]
    async def pipeline(request, **kwargs):
        assert kwargs['subtask'] == '轨迹中的子任务'
        return PipelineResult(request, 'installed')
    monkeypatch.setattr(skills, 'infer_requests', infer)
    monkeypatch.setattr(skills, 'run_pipeline', pipeline)
    token = _current_task_var.set('父任务')
    try:
        await skills.generate_skills(SkillSignal('trace',text='记录'), library_path=tmp_path)
    finally:
        _current_task_var.reset(token)

@pytest.mark.asyncio
async def test_long_trace_preserves_middle_execution_failure(tmp_path):
    lines = [json.dumps({'type':'task_start','query':'查论文'})]
    lines += [json.dumps({'type':'answer_stream_delta','text':'x'*2000})]*40
    lines.append(json.dumps({'type':'step','agent':'search_agent','action':{'name':'exec','args':{'argv':['python','scripts/run.py','--bad-option']}},'observation':json.dumps({'status':'failed','stderr':'unknown parameters: max_results'})}))
    lines += [json.dumps({'type':'answer_stream_delta','text':'y'*2000})]*40
    path=tmp_path/'trajectory.jsonl';path.write_text('\n'.join(lines))
    class Selector:
        async def ainvoke(self,prompt):
            assert 'unknown parameters: max_results' in prompt
            assert '--bad-option' in prompt
            assert len(prompt) < 70000
            return AIMessage(content='[]')
    await infer_requests(SkillSignal('trace',trace_path=path), model=Selector(), library_path=tmp_path/'library')

@pytest.mark.asyncio
async def test_multisource_access_update_accepts_existing_package_without_host(tmp_path, monkeypatch):
    from searchos.skills.pipeline.access import run
    package = install(tmp_path, 'access')
    (package/'SKILL.md').write_text((package/'SKILL.md').read_text().replace('  host: example.com\n',''))
    request = dict(action='update', category='access', name='existing-method', description='补齐参数', reason='重复参数错误')
    class Selector:
        async def ainvoke(self, prompt):
            return AIMessage(content=json.dumps([request]))
    requests = await infer_requests(SkillSignal('trace', text='existing-method 参数错误'),model=Selector(),library_path=tmp_path)
    assert requests[0].host == '' and requests[0].probe_urls == ()
    async def failed(**kwargs):
        assert kwargs['existing_package'] == package
        assert kwargs['host'] == '' and kwargs['probe_urls'] == []
        return None
    monkeypatch.setattr(run,'build_skill',failed)
    result = await run_pipeline(requests[0],library_path=tmp_path)
    assert result.status == 'build_failed'

@pytest.mark.asyncio
async def test_missing_host_only_allowed_for_multisource_update_validation(tmp_path, monkeypatch):
    from searchos.skills.pipeline.access import valid
    package = install(tmp_path, 'access')
    (package/'SKILL.md').write_text((package/'SKILL.md').read_text().replace('  host: example.com\n',''))
    (package/'scripts').mkdir()
    (package/'scripts/search.py').write_text('print("test")')
    async def validate_examples(*args):
        return {'valid': True, 'stage': 'complete'}
    monkeypatch.setattr(valid,'validate_examples',validate_examples)
    assert not (await valid.validate_access_package(package,'existing-method',[]))['valid']
    assert (await valid.validate_access_package(package,'existing-method',[],require_host=False))['valid']
