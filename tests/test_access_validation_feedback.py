"""验收拒绝候选时，保留可定位错误的有界执行输出。"""
import json

import pytest

from searchos.skills.pipeline.access.valid import validate_examples


@pytest.mark.asyncio
@pytest.mark.parametrize('execution',[
    {'exit_code':1,'status':'failed','stdout':json.dumps({'status':'blocked','records':[],
        'warnings':['未到达有效的汉典页面']},ensure_ascii=False),'stderr':''},
    {'exit_code':0,'status':'completed','stdout':json.dumps({'status':'empty','records':[],
        'warnings':['页面没有可解析的结果']}),'stderr':''},
    {'exit_code':1,'status':'failed','stdout':'x'*10000,'stderr':'y'*10000},
])
async def test_rejected_example_keeps_bounded_execution_evidence(tmp_path,monkeypatch,execution):
    from searchos.skills.runtime import command_runtime
    async def command(package,argv,**kwargs):
        if argv[-1]=='--help':
            return {'exit_code':0,'status':'completed','stdout':'usage'}
        return execution
    monkeypatch.setattr(command_runtime,'run_command',command)
    result=await validate_examples(tmp_path,[{'argv':['python','scripts/access.py','--input','{}'],
        'output':'','records_key':'records'}])
    assert result['valid'] is False
    assert result['execution']['exit_code']==execution['exit_code']
    assert result['execution']['status']==execution['status']
    assert result['execution']['stdout']==execution['stdout'][:2000]
    assert result['execution']['stderr']==execution['stderr'][:2000]
    assert len(result['execution']['stdout'])<=2000
    assert len(result['execution']['stderr'])<=2000


@pytest.mark.asyncio
@pytest.mark.parametrize('help_failure,auth_required', [(False,False),(True,False),(False,True)])
async def test_failure_summary_preserves_stdout_cause(tmp_path,monkeypatch,help_failure,auth_required):
    from searchos.skills.runtime import command_runtime
    cause='未到达有效的汉典页面'
    failure={'exit_code':1,'status':'failed','stdout':json.dumps(
        {'status':'blocked','records':[],'warnings':[cause]},ensure_ascii=False),'stderr':'  \n'}
    if auth_required:
        failure.update(auth_required=True,error='auth_required')
    async def command(package,argv,**kwargs):
        if argv[-1]=='--help' and not help_failure:
            return {'exit_code':0,'status':'completed','stdout':'usage'}
        return failure
    monkeypatch.setattr(command_runtime,'run_command',command)
    result=await validate_examples(tmp_path,[{'argv':['python','scripts/access.py'],'records_key':'records'}])
    assert not result['valid']
    assert cause in result['error'] and 'blocked' in result['error']
    assert cause in result['execution']['stdout']
    if auth_required:
        assert result['auth_required'] and result['stage']=='authentication'


@pytest.mark.asyncio
async def test_builder_receives_real_cli_failure_and_repairs_it(tmp_path):
    from langchain_core.messages import AIMessage,ToolMessage
    from searchos.skills.intent.models import SkillRequest
    from searchos.skills.pipeline.run import run_pipeline
    cause='未到达有效的汉典页面'
    header='import argparse,json,sys\np=argparse.ArgumentParser()\np.add_argument("--input")\np.parse_args()\n'
    broken=header+f'print(json.dumps({{"status":"blocked","records":[],"warnings":["{cause}"]}},ensure_ascii=False))\nsys.exit(1)\n'
    repaired=header+'print(json.dumps({"records":[{"title":"test response","source_url":"https://example.com/item"}]}))\n'
    class Model:
        turn=0
        received=None
        def bind_tools(self,definitions):return self
        async def ainvoke(self,messages):
            self.turn+=1
            if self.turn==1:
                files={'SKILL.md':'---\nname: example-com\ndescription: 测试验收反馈\nmetadata:\n  searchos-category: access\n  host: example.com\n---\npython scripts/access.py --input JSON\n',
                       'scripts/access.py':broken}
                return AIMessage(content='',tool_calls=[{'id':str(i),'name':'write_file','args':{'path':p,'content':c}} for i,(p,c) in enumerate(files.items())])
            if self.turn==2:
                return AIMessage(content='',tool_calls=[{'id':'validate','name':'validate_skill','args':{}}])
            if self.turn==3:
                self.received=json.loads(next(m.content for m in reversed(messages) if isinstance(m,ToolMessage) and m.tool_call_id=='validate'))
                assert cause in self.received['error']
                assert cause in self.received['execution']['stdout']
                assert self.received['execution']['exit_code']==1
                return AIMessage(content='',tool_calls=[{'id':'repair','name':'write_file','args':{'path':'scripts/access.py','content':repaired}}])
            return AIMessage(content='完成')
    model=Model()
    result=await run_pipeline(SkillRequest('access','example-com','验证错误反馈与修复',host='example.com',probe_urls=('https://example.com/',)),
        library_path=tmp_path/'library',trial_root=tmp_path/'trials',model=model,access_max_turns=5,
        access_validation_examples=[{'argv':['python','scripts/access.py','--input','{}'],'output':'','records_key':'records'}])
    assert result.status=='installed' and model.received is not None
    events=[json.loads(line) for line in (result.trial_path.parent/'events.jsonl').read_text().splitlines()]
    feedback=json.loads(next(e['content'] for e in events if e['event']=='tool_result' and e.get('name')=='validate_skill'))
    assert cause in feedback['error']
