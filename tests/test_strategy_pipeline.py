"""只验证候选策略是否帮助当前 subtask 得到有来源支持的答案。"""
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage
from searchos.skills import SkillRequest, run_pipeline
from searchos.skills.pipeline.strategy.trial import validate_strategy, run_current_subtask
from searchos.tools.search_state import _current_task_var


SECRET = '候选秘密方法：直接检查官方年度报告的收入表。'
TASK = '查明 Example 公司 2025 年收入，并给出官方来源。'


@pytest.fixture(autouse=True)
def isolate_fixture_library(monkeypatch):
    # 本地测试库不继承 WebUI/环境对真实技能库的禁用与筛选配置。
    for name in ('SEARCHOS_SKILLS_DISABLED', 'SEARCHOS_SKILL_LAYERS_DISABLED',
                 'SEARCHOS_SKILL_ONLY', 'SEARCHOS_SKILL_EXCLUDE'):
        monkeypatch.delenv(name, raising=False)


class Builder:
    async def ainvoke(self, messages):
        return AIMessage(content='---\nname: official-revenue\ndescription: 从官方报告核对收入\nmetadata:\n  searchos-category: strategy\n---\n'+SECRET)


def outcome(**changes):
    data={'answer':'2025 年收入为 100，见官方报告。',
          'evidence':[{'claim':'2025 年收入为 100','source':'https://example.com/report','excerpt':'2025 revenue: 100'}],
          'sources':[{'source':'https://example.com/report','text':'2025 revenue: 100'}],
          'strategy_applied':True,'error':''}
    return {**data,**changes}

class Judge:
    def __init__(self, **changes):
        self.changes=changes
        self.calls=0
    async def ainvoke(self, messages):
        self.calls+=1
        content=messages[-1].content
        assert SECRET not in content and 'official-revenue' not in content
        payload=json.loads(content)
        assert set(payload)=={'subtask','answer','evidence','sources'}
        assert payload['subtask']==TASK
        return AIMessage(content=json.dumps({'answered':True,'grounded':True,'reason':'答案覆盖子任务，官方报告正文支持金额。',
                                            'issues':[],'confidence':.95,**self.changes}))

async def execute(tmp_path, runner, judge, **kwargs):
    action = kwargs.pop('action', 'create')
    return await run_pipeline(SkillRequest('strategy','official-revenue','核对收入',subtask=TASK,
                                         action=action, reason='补齐年份核验'),
                               library_path=tmp_path/'library', model=Builder(),subtask_runner=runner,
                               judge_model=judge,trial_root=tmp_path/'trials',**kwargs)


@pytest.mark.asyncio
async def test_success_runs_subtask_once_then_installs_and_saves_records(tmp_path):
    calls=[]
    async def runner(**kwargs):
        calls.append(kwargs)
        assert not (tmp_path/'library/strategy/official-revenue').exists()
        return outcome()
    judge=Judge()
    result=await execute(tmp_path,runner,judge)
    assert result.status=='installed'
    assert calls==[{'subtask':TASK,'strategy':SECRET}]
    assert judge.calls==1
    assert result.path.is_dir()
    record=result.trial_path.parent
    assert json.loads(result.trial_path.read_text())['accepted'] is True
    assert (record/'candidate/official-revenue/SKILL.md').is_file()
    assert (record/'outcome.json').is_file() and (record/'judge.json').is_file()
    assert not (record/'baseline.json').exists() and not (record/'library').exists()
    assert result.to_report()['trial_path']==str(result.trial_path)


@pytest.mark.asyncio
@pytest.mark.parametrize('changes',[{'answered':False,'reason':'缺少年份'}, {'grounded':False,'reason':'金额没有来源支持'},
                                   {'confidence':.2}, {'issues':['关键单位不明确']}])
async def test_rejection_preserves_old_skill_and_failure_reason(tmp_path,changes):
    previous=tmp_path/'library/strategy/official-revenue'
    previous.mkdir(parents=True)
    old = '---\nname: official-revenue\ndescription: 核对收入\nmetadata:\n  searchos-category: strategy\n---\nexisting version'
    (previous/'SKILL.md').write_text(old)
    async def runner(**kwargs):return outcome()
    result=await execute(tmp_path,runner,Judge(**changes),action='update')
    assert result.status=='validation_failed' and result.error
    assert (previous/'SKILL.md').read_text()==old
    saved=json.loads(result.trial_path.read_text())
    assert not saved['accepted'] and saved['reason']==result.error
    assert not list(previous.parent.glob('.pipeline*'))


@pytest.mark.asyncio
@pytest.mark.parametrize('changes',[{'error':'network failed'},{'strategy_applied':False}])
async def test_failed_or_unapplied_run_does_not_reach_judge(tmp_path,changes):
    async def runner(**kwargs):return outcome(**changes)
    judge=Judge()
    result=await execute(tmp_path,runner,judge)
    assert result.status=='validation_failed'
    assert judge.calls==0
    assert not (tmp_path/'library/strategy/official-revenue').exists()
    assert (result.trial_path.parent/'outcome.json').exists()


@pytest.mark.asyncio
async def test_no_evidence_cannot_pass_even_if_judge_says_success(tmp_path):
    async def runner(**kwargs):return outcome(evidence=[])
    result=await execute(tmp_path,runner,Judge())
    assert result.status=='validation_failed' and '没有来源证据' in result.error


@pytest.mark.asyncio
async def test_invalid_judge_response_fails_closed(tmp_path):
    async def runner(**kwargs):return outcome()
    result=await execute(tmp_path,runner,Judge(answered='true'))
    assert result.status=='validation_failed' and 'booleans' in result.error
    assert (result.trial_path.parent/'judge-response.json').is_file()


@pytest.mark.asyncio
async def test_current_subtask_takes_precedence_over_generated_task(tmp_path):
    token=_current_task_var.set(TASK)
    try:
        async def runner(**kwargs):
            assert kwargs['subtask']==TASK
            return outcome()
        request=SkillRequest('strategy','official-revenue','核对收入',subtask='模型建议的其他任务')
        result=await run_pipeline(request,library_path=tmp_path/'library',model=Builder(),subtask_runner=runner,
                                   judge_model=Judge(),trial_root=tmp_path/'trials')
        assert result.status=='installed'
    finally:_current_task_var.reset(token)


@pytest.mark.asyncio
async def test_missing_subtask_is_recorded_and_never_installed(tmp_path):
    result=await run_pipeline(SkillRequest('strategy','official-revenue','核对收入'),library_path=tmp_path/'library',
                               model=Builder(),trial_root=tmp_path/'trials')
    assert result.status=='validation_failed' and 'no subtask' in result.error
    assert result.trial_path.is_file()


@pytest.mark.asyncio
async def test_timeout_cancels_runner_and_records_failure(tmp_path):
    cancelled=[]
    async def runner(**kwargs):
        try:await asyncio.sleep(100)
        finally:cancelled.append(True)
    result=await execute(tmp_path,runner,Judge(),trial_timeout_s=.01)
    assert result.status=='validation_failed' and 'TimeoutError' in result.error
    assert cancelled==[True]


@pytest.mark.asyncio
async def test_default_runner_reuses_active_subagent_execution(tmp_path,monkeypatch):
    from searchos.agents import runtime
    from searchos.agents.orchestrator import lifecycle
    from searchos.tools.search_state import _current_agent_var
    ctx=SimpleNamespace(workspace=SimpleNamespace(path=tmp_path,load_state=lambda:SimpleNamespace(
            evidence_graph=SimpleNamespace(nodes=[],observations=[],task_bindings=[]))),
            model=object(), agent_graphs={'old':{'agent_type':'local_search_agent','skill_names':['existing'], 'target_table':'table'}},
            task_pool={})
    monkeypatch.setattr(runtime,'_ctx',ctx)
    calls=[]
    async def spawn(agent_type,task,skills,**kwargs):
        calls.append((agent_type,task,skills,kwargs))
        ctx.agent_graphs['validation']={'strategy_guidance_applied':True}
        async def finish():return SimpleNamespace(status='completed',last_message='answer',task_ids=[],duration_s=1)
        ctx.task_pool['validation']=asyncio.create_task(finish())
        return 'validation'
    monkeypatch.setattr(lifecycle,'_spawn_sub_agent',spawn)
    token=_current_agent_var.set('old')
    try:result=await run_current_subtask(subtask=TASK,strategy=SECRET)
    finally:_current_agent_var.reset(token)
    assert calls==[('local_search_agent',TASK,['existing'],{'target_table':'table','strategy_guidance':SECRET})]
    assert result['answer']=='answer' and result['strategy_applied'] is True


@pytest.mark.asyncio
async def test_cancelled_validation_keeps_failure_record_and_stops_runner(tmp_path):
    started=asyncio.Event()
    cancelled=[]
    async def runner(**kwargs):
        started.set()
        try:await asyncio.sleep(100)
        finally:cancelled.append(True)
    task=asyncio.create_task(execute(tmp_path,runner,Judge()))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):await task
    records=list((tmp_path/'trials').rglob('result.json'))
    assert len(records)==1 and json.loads(records[0].read_text())['status']=='cancelled'
    assert cancelled==[True]
    assert not (tmp_path/'library/strategy/official-revenue').exists()


@pytest.mark.asyncio
async def test_candidate_changed_during_trial_cannot_be_published(tmp_path):
    async def runner(**kwargs):
        candidate=next((tmp_path/'library/strategy').glob('.pipeline*/official-revenue/SKILL.md'))
        candidate.write_text(candidate.read_text()+'\n未经试验的新方法')
        return outcome()
    result=await execute(tmp_path,runner,Judge())
    assert result.status=='validation_failed' and 'changed during validation' in result.error
    assert not (tmp_path/'library/strategy/official-revenue').exists()


@pytest.mark.asyncio
async def test_strategy_resume_receives_failed_trial_and_revalidates(tmp_path):
    from searchos.skills.pipeline.drafts import load_draft
    async def incomplete(**kwargs): return outcome(evidence=[])
    first = await execute(tmp_path, incomplete, Judge())
    assert first.status == 'validation_failed'
    package, saved = load_draft(first.draft_path)
    assert saved['validation']['stage'] == 'strategy_trial'
    original = (package / 'SKILL.md').read_text()
    class Repair:
        async def ainvoke(self, messages):
            assert json.loads(messages[1].content)['existing_skill'] == original
            assert first.error in messages[-1].content
            return AIMessage(content=original + '\n必须核对来源原文，返回引文及链接。')
    calls = []
    async def successful(**kwargs):
        calls.append(kwargs)
        return outcome()
    second = await run_pipeline(first.request, library_path=tmp_path / 'library', model=Repair(),
        resume_draft=first.draft_path, subtask_runner=successful, judge_model=Judge(), trial_root=tmp_path / 'repair')
    assert second.status == 'installed' and len(calls) == 1
    assert '核对来源原文' in calls[0]['strategy']
    assert (package / 'SKILL.md').read_text() == original
