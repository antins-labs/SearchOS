"""生成预算、收尾阶段与失败诊断回归。"""
import json
import pytest
from langchain_core.messages import AIMessage
from searchos.skills.pipeline.access.run import build_skill, MAX_TURNS


def test_default_budget():
    assert MAX_TURNS == 45


@pytest.mark.asyncio
async def test_model_failure_retains_cause_and_attempt_count(tmp_path):
    class Model:
        def bind_tools(self, tools): return self
        async def ainvoke(self, messages): raise RuntimeError('provider unavailable')
    diagnostics = {}
    assert await build_skill('example.com', [], output_dir=tmp_path/'skill', builder_model=Model(),
                             record_dir=tmp_path/'record', diagnostics=diagnostics) is None
    assert diagnostics['exit_reason'] == 'model_error'
    assert diagnostics['turns_attempted'] == 1 and diagnostics['turns_completed'] == 0
    assert diagnostics['model_error_type'] == 'RuntimeError'
    saved = json.loads((tmp_path/'record/builder.json').read_text())
    assert saved['exit_reason'] == 'model_error'
    assert (tmp_path/'record/events.jsonl').exists()


@pytest.mark.asyncio
async def test_reserve_phase_rejects_new_research_and_records_exhaustion(tmp_path):
    class Model:
        def __init__(self): self.prompts = []
        def bind_tools(self, tools): return self
        async def ainvoke(self, messages):
            self.prompts.append(messages[-1].content)
            return AIMessage(content='', tool_calls=[dict(id=str(len(self.prompts)), name='web_search', args={'query':'extra features'})])
    from searchos.skills.pipeline.access import run
    calls = []
    async def tool(workspace, call):
        calls.append(call['name'])
        from langchain_core.messages import ToolMessage
        return ToolMessage(content='research', tool_call_id=call['id'])
    # 两轮：一轮探索，一轮只允许补齐验证。
    from unittest.mock import patch
    model = Model(); diagnostics = {}
    with patch.object(run, 'run_tool', tool):
        assert await build_skill('example.com', [], output_dir=tmp_path/'skill', builder_model=model,
            max_turns=2, record_dir=tmp_path/'record', diagnostics=diagnostics) is None
    assert calls == ['web_search']
    assert any('收尾' in str(prompt) for prompt in model.prompts)
    assert diagnostics['exit_reason'] == 'max_turns'
    assert diagnostics['turns_completed'] == 2
    events = [json.loads(line) for line in (tmp_path/'record/events.jsonl').read_text().splitlines()]
    assert any(event['event'] == 'repair_phase' for event in events)
    assert any(event['event'] == 'tool_result' and event.get('blocked') for event in events)


def test_record_redacts_env_credentials_and_private_fields(tmp_path, monkeypatch):
    from searchos.skills.pipeline.access.records import BuildRecord
    monkeypatch.setenv('TEST_API_KEY', 'private-test-key-123')
    record = BuildRecord(tmp_path/'record')
    record.event('tool_result', content='token private-test-key-123', args={'authorization': 'secret'})
    value = (tmp_path/'record/events.jsonl').read_text()
    assert 'private-test-key-123' not in value and '"secret"' not in value
    assert '[REDACTED]' in value


@pytest.mark.asyncio
async def test_pipeline_failure_points_to_persistent_builder_record(tmp_path, monkeypatch):
    from searchos.skills import SkillRequest, run_pipeline
    from searchos.skills.pipeline.access import run
    class Model:
        def bind_tools(self, tools): return self
        async def ainvoke(self, messages): raise RuntimeError('provider unavailable')
    result = await run_pipeline(SkillRequest('access', 'example-com', 'query', host='example.com',
        probe_urls=('https://example.com',)), library_path=tmp_path/'library', model=Model(), trial_root=tmp_path/'trials')
    assert result.status == 'build_failed'
    saved = json.loads(result.trial_path.read_text())
    assert saved['diagnostics']['exit_reason'] == 'model_error'
    assert (result.trial_path.parent/'builder.json').exists()
    assert (result.trial_path.parent/'events.jsonl').exists()
    assert not list((tmp_path/'library/access').glob('.pipeline*'))


@pytest.mark.asyncio
async def test_repair_phase_registers_missing_commands_and_passes(tmp_path, monkeypatch):
    from searchos.skills.runtime import command_runtime
    class Model:
        def __init__(self): self.turn = 0
        def bind_tools(self, tools): return self
        async def ainvoke(self, messages):
            self.turn += 1
            if self.turn == 1:
                files = {'SKILL.md': '---\nname: example-com\ndescription: 查询股价\nmetadata:\n  searchos-category: access\n  host: example.com\n---\npython scripts/history.py\npython scripts/quote.py\n',
                         'scripts/history.py': 'print(1)', 'scripts/quote.py': 'print(1)'}
                return AIMessage(content='', tool_calls=[dict(id=str(i), name='write_file', args=dict(path=p, content=c)) for i, (p, c) in enumerate(files.items())])
            assert '收尾' in messages[-1].content and 'missing_entries' in messages[-1].content
            return AIMessage(content='', tool_calls=[dict(id='register-'+name, name='register_example', args=dict(argv=['python', 'scripts/'+name+'.py'], output='', records_key='records')) for name in ['history', 'quote']])
    async def command(*args, **kwargs):
        return {'exit_code': 0, 'stdout': json.dumps({'records': [{'url':'https://example.com/record', 'price': 10}]})}
    monkeypatch.setattr(command_runtime, 'run_command', command)
    target = tmp_path/'example-com'; diagnostics = {}
    result = await build_skill('example.com', [], output_dir=target, builder_model=Model(), max_turns=2,
                               diagnostics=diagnostics, record_dir=tmp_path/'records')
    assert result == target and diagnostics['valid'] is True
    assert diagnostics['turns_completed'] == 2
