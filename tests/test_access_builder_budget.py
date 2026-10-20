"""常规调用、一次额外收尾与验证反馈回归。"""
import json
import pytest
from langchain_core.messages import AIMessage
from searchos.skills.pipeline.access.run import build_skill, MAX_TURNS


def test_default_budget():
    assert MAX_TURNS == 45


def site_plan():
    return {'capabilities': [{'id': 'latest', 'purpose': '获取最新记录', 'inputs': {},
        'required_fields': ['title', 'source_url'], 'examples': [{}], 'evidence_ids': ['obs-1']}],
        'limitations': []}


@pytest.mark.asyncio
async def test_site_extra_closing_call_submits_final_json(tmp_path):
    from types import SimpleNamespace
    from searchos.skills.intent.site import SiteIntentSession, validate_plan
    from searchos.skills.pipeline.access.records import BuildRecord
    class Model:
        calls = 0
        def bind_tools(self, definitions): return self
        async def ainvoke(self, messages):
            self.calls += 1
            if self.calls == 4:
                assert '额外收尾' in messages[-1].content
                assert '不再调用工具' in messages[-1].content
                return AIMessage(content=json.dumps(site_plan()))
            else:
                proposal = {'capabilities': []}
            return AIMessage(content='', tool_calls=[{'name':'submit_site_plan', 'args':proposal, 'id':str(self.calls)}])
    model = Model()
    session = SiteIntentSession(model, SimpleNamespace(), BuildRecord(tmp_path/'record'))
    session.state['observations'] = [{'id':'obs-1', 'tool':'web_open', 'usable':True,
                                    'result':{'content':'public page', 'live_evidence':True}}]
    result = await session.converse([], 3, validator=lambda v: validate_plan(v, session.state['observations']))
    assert result['capabilities'][0]['id'] == 'latest' and model.calls == 4


@pytest.mark.asyncio
async def test_site_without_page_evidence_fails_after_closing_submission(tmp_path):
    from types import SimpleNamespace
    from searchos.skills.intent.site import SiteIntentSession, validate_plan
    from searchos.skills.pipeline.access.records import BuildRecord
    class Browser:
        async def dispatch(self, name, args):
            return {'content':'cached search result', 'content_source':'search_results', 'live_evidence':False}
    class Model:
        calls = 0
        def bind_tools(self, definitions): return self
        async def ainvoke(self, messages):
            self.calls += 1
            if self.calls == 6:
                return AIMessage(content=json.dumps(site_plan()))
            return AIMessage(content='', tool_calls=[{'name':'web_search', 'args':{'query':'site docs'}, 'id':str(self.calls)}])
    model = Model()
    session = SiteIntentSession(model, SimpleNamespace(browser=Browser()), BuildRecord(tmp_path/'record'))
    session.observe('web_open', {'id_or_url':'https://example.com'}, {'content':'[FETCH_ERROR] network_failure'}, 'intent')
    with pytest.raises(ValueError, match='site_page_evidence_unavailable'):
        await session.converse([], 5, validator=lambda v: validate_plan(v, session.state['observations']))
    assert model.calls == 6
    saved = json.loads(session.path.read_text())
    assert saved['failure']['code'] == 'site_page_evidence_unavailable'


@pytest.mark.asyncio
async def test_site_final_format_error_does_not_erase_contract_error(tmp_path):
    from types import SimpleNamespace
    from searchos.skills.intent.site import SiteIntentSession, validate_plan
    from searchos.skills.pipeline.access.records import BuildRecord
    class Model:
        calls = 0
        def bind_tools(self, definitions): return self
        async def ainvoke(self, messages):
            self.calls += 1
            if self.calls > 1:
                return AIMessage(content='无法提交')
            proposal = site_plan(); proposal['capabilities'][0]['inputs'] = ['date']
            return AIMessage(content='', tool_calls=[{'name':'submit_site_plan', 'args':proposal, 'id':'first'}])
    session = SiteIntentSession(Model(), SimpleNamespace(), BuildRecord(tmp_path/'record'))
    session.state['observations'] = [{'id':'obs-1','usable':True}]
    with pytest.raises(ValueError, match=r'latest.inputs'):
        await session.converse([], 3, validator=lambda v: validate_plan(v, session.state['observations']))
    assert session.state['failure']['code'] == 'site_plan_invalid'
    assert 'latest.inputs' in session.state['failure']['message']


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
async def test_regular_budget_gets_exactly_one_extra_closing_call(tmp_path):
    class Model:
        def __init__(self): self.prompts = []
        def bind_tools(self, tools): return self
        async def ainvoke(self, messages):
            self.prompts.append(messages[-1].content)
            if len(self.prompts) == 3:
                assert '额外的一次收尾' in messages[-1].content and '停止新探索' in messages[-1].content
                return AIMessage(content='无法完成，保留失败。')
            return AIMessage(content='', tool_calls=[dict(id=str(len(self.prompts)), name='web_search', args={'query':'example.com code 37 proxy'})])
    from searchos.skills.pipeline.access import run
    calls = []
    async def tool(workspace, call):
        calls.append(call['name'])
        from langchain_core.messages import ToolMessage
        return ToolMessage(content='research', tool_call_id=call['id'])
    # 常规两轮可研究；尚未交付时仅额外一次收尾。
    from unittest.mock import patch
    model = Model(); diagnostics = {}
    with patch.object(run, 'run_tool', tool):
        assert await build_skill('example.com', [], output_dir=tmp_path/'skill', builder_model=model,
            max_turns=2, record_dir=tmp_path/'record', diagnostics=diagnostics) is None
    assert calls == ['web_search', 'web_search']
    assert any('收尾' in str(prompt) for prompt in model.prompts)
    assert diagnostics['exit_reason'] == 'max_turns'
    assert diagnostics['turns_completed'] == 3
    events = [json.loads(line) for line in (tmp_path/'record/events.jsonl').read_text().splitlines()]
    assert [event['closing'] for event in events if event['event'] == 'model_started'] == [False, False, True]
    assert not any(event['event'] in {'repair_phase', 'implementation_phase'} for event in events)


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
async def test_validation_failure_registers_missing_commands_and_passes(tmp_path, monkeypatch):
    from searchos.skills.runtime import command_runtime
    class Model:
        def __init__(self): self.turn = 0
        def bind_tools(self, tools): return self
        async def ainvoke(self, messages):
            self.turn += 1
            if self.turn == 1:
                files = {'SKILL.md': '---\nname: example-com\ndescription: 查询股价\nmetadata:\n  searchos-category: access\n  host: example.com\n---\npython scripts/history.py\npython scripts/quote.py\n',
                         'scripts/history.py': 'print(1)', 'scripts/quote.py': 'print(1)'}
                return AIMessage(content='', tool_calls=[*[dict(id=str(i), name='write_file', args=dict(path=p, content=c)) for i, (p, c) in enumerate(files.items())], dict(id='validate', name='validate_skill', args={})])
            assert any('missing_entries' in str(message.content) for message in messages)
            return AIMessage(content='', tool_calls=[dict(id='register-'+name, name='register_example', args=dict(argv=['python', 'scripts/'+name+'.py'], output='', records_key='records')) for name in ['history', 'quote']])
    async def command(*args, **kwargs):
        return {'exit_code': 0, 'stdout': json.dumps({'records': [{'url':'https://example.com/record', 'price': 10}]})}
    monkeypatch.setattr(command_runtime, 'run_command', command)
    target = tmp_path/'example-com'; diagnostics = {}
    result = await build_skill('example.com', [], output_dir=target, builder_model=Model(), max_turns=2,
                               diagnostics=diagnostics, record_dir=tmp_path/'records')
    assert result == target and diagnostics['valid'] is True
    assert diagnostics['turns_completed'] == 2


def builder_call(name, call_id, **args):
    return {'name': name, 'id': call_id, 'args': args}


@pytest.mark.asyncio
@pytest.mark.parametrize('size,limit,expected_length,next_offset', [
    (14307, None, 14307, None),
    (16000, None, 16000, None),
    (16001, None, 16000, 16000),
    (24000, 24000, 24000, None),
    (24001, 50000, 24000, 24000),
])
async def test_read_file_character_windows_and_exact_boundaries(tmp_path, size, limit, expected_length, next_offset):
    from searchos.skills.pipeline.access.tools import BuilderWorkspace
    workspace = BuilderWorkspace(tmp_path/'example-com')
    try:
        content = '汉' * size
        await workspace.write_file('scripts/long.py', content)
        args = {'path': 'scripts/long.py'}
        if limit is not None: args['limit'] = limit
        result = await workspace.dispatch('read_file', args)
        assert result['content'] == content[:expected_length]
        assert result['total_chars'] == size
        assert result['next_offset'] == next_offset
        assert result['truncated'] is (next_offset is not None)
    finally:
        workspace.close()


@pytest.mark.asyncio
async def test_read_file_large_file_paginates_without_gaps(tmp_path):
    from searchos.skills.pipeline.access.tools import BuilderWorkspace
    workspace = BuilderWorkspace(tmp_path/'example-com')
    try:
        content = ''.join(str(i % 10) for i in range(50003))
        await workspace.write_file('scripts/long.py', content)
        offset, chunks, offsets = 0, [], []
        while offset is not None:
            result = await workspace.read_file('scripts/long.py', offset=offset, limit=24000)
            assert result['total_chars'] == len(content)
            chunks.append(result['content']); offsets.append(result['next_offset'])
            offset = result['next_offset']
        assert [len(chunk) for chunk in chunks] == [24000, 24000, 2003]
        assert offsets == [24000, 48000, None] and ''.join(chunks) == content
        end = await workspace.read_file('scripts/long.py', offset=len(content))
        assert end == {'content': '', 'total_chars': len(content), 'truncated': False, 'next_offset': None}
    finally:
        workspace.close()


def test_read_file_schema_advertises_default_maximum_and_pagination():
    from searchos.skills.pipeline.access.tools import BuilderWorkspace
    tool = next(tool['function'] for tool in BuilderWorkspace.TOOL_DEFINITIONS if tool['function']['name'] == 'read_file')
    limit = tool['parameters']['properties']['limit']
    assert limit['default'] == 16000 and limit['maximum'] == 24000
    assert all(field in tool['description'] for field in ('total_chars', 'truncated', 'next_offset'))


@pytest.mark.asyncio
@pytest.mark.parametrize('locked', [False, True])
async def test_extra_closing_call_can_repair_after_reading_a_long_file(tmp_path, monkeypatch, locked):
    """本地模型替身验证工具与提示链路；不代表真实模型已完成修复。"""
    from langchain_core.messages import ToolMessage
    from searchos.skills.pipeline.access import run, tools
    seed = tmp_path/'seed'; (seed/'scripts').mkdir(parents=True)
    (seed/'SKILL.md').write_text('---\nname: example-com\ndescription: 本地预算回归\nmetadata:\n'
        '  searchos-category: access\n  host: example.com\n---\npython scripts/access.py\n')
    suffix = "\nvalue = 'before'\n"
    original = '#' + 'x' * (14307 - len(suffix) - 1) + suffix
    (seed/'scripts/access.py').write_text(original)
    async def local_validation(package, *args, **kwargs):
        changed = "value = 'after'" in (package/'scripts/access.py').read_text()
        return {'valid': changed, 'stage': 'local_test', 'error': '' if changed else 'unrepaired'}
    monkeypatch.setattr(tools, 'validate_access_package', local_validation)
    class LocalModel:
        calls = 0
        def bind_tools(self, definitions): return self
        async def ainvoke(self, messages):
            self.calls += 1
            if self.calls == 1:
                return AIMessage(content='', tool_calls=[builder_call('read_file', 'read-long', path='scripts/access.py')])
            assert '额外的一次收尾' in messages[-1].content
            if locked: assert any('固定样例' in str(message.content) for message in messages)
            read = next(message for message in messages if isinstance(message, ToolMessage) and message.tool_call_id == 'read-long')
            observed = json.loads(read.content)
            assert observed['content'] == original and observed['total_chars'] == 14307
            assert not observed['truncated'] and observed['next_offset'] is None
            return AIMessage(content='', tool_calls=[builder_call('edit_file', 'edit-tail', path='scripts/access.py',
                old_text="value = 'before'", new_text="value = 'after'")])
    model = LocalModel(); diagnostics = {}; target = tmp_path/'library/example-com'
    examples = [{'argv': ['python', 'scripts/access.py'], 'output': '', 'records_key': 'records'}] if locked else None
    result = await build_skill('example.com', [], output_dir=target, existing_package=seed,
        validation_examples=examples, builder_model=model, max_turns=1, diagnostics=diagnostics,
        record_dir=tmp_path/'record')
    assert result == target and model.calls == 2 and diagnostics['turns_completed'] == 2
    assert (target/'scripts/access.py').read_text() == original.replace("value = 'before'", "value = 'after'")


@pytest.mark.asyncio
async def test_read_file_tool_message_preserves_full_bounded_page(tmp_path):
    from searchos.skills.pipeline.access.tools import BuilderWorkspace, run_tool
    workspace = BuilderWorkspace(tmp_path/'example-com')
    try:
        content = '汉"\\\n' * 7000
        await workspace.write_file('scripts/long.py', content)
        message = await run_tool(workspace, builder_call('read_file', 'read-page',
            path='scripts/long.py', limit=24000))
        result = json.loads(message.content)
        assert result['content'] == content[:24000]
        assert result['total_chars'] == len(content)
        assert result['truncated'] is True and result['next_offset'] == 24000
    finally:
        workspace.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('apply_change', [False, True])
async def test_resumed_update_keeps_revision_requirement_even_when_old_examples_pass(tmp_path, monkeypatch, apply_change):
    from searchos.skills.pipeline.access import run, tools
    from searchos.skills.pipeline.drafts import save_draft
    seed = tmp_path/'seed'; (seed/'scripts').mkdir(parents=True)
    (seed/'SKILL.md').write_text('---\nname: example-com\ndescription: 查询记录\nmetadata:\n'
        '  searchos-category: access\n  host: example.com\n---\npython scripts/access.py\n')
    (seed/'scripts/access.py').write_text("value = 'before'\n")
    pointer = save_draft(tmp_path/'previous', seed, ['SKILL.md', 'scripts/access.py'],
        name='example-com', examples=[{'argv': ['python', 'scripts/access.py'], 'output': '', 'records_key': 'records'}],
        require_host=True, validation={'valid': False, 'stage': 'examples', 'error': 'known previous failure'})
    original = pointer.read_bytes()
    async def old_examples_pass(*args, **kwargs): return {'valid': True}
    monkeypatch.setattr(tools, 'validate_access_package', old_examples_pass)
    class Model:
        calls = 0
        def bind_tools(self, definitions): return self
        async def ainvoke(self, messages):
            self.calls += 1
            if self.calls == 1:
                assert any('known previous failure' in str(message.content) for message in messages)
            else:
                assert any('update_has_no_changes' in str(message.content) for message in messages)
            return AIMessage(content='', tool_calls=[builder_call('edit_file', 'repair',
                path='scripts/access.py', old_text="'before'", new_text="'after'")] if apply_change else [])
    model = Model(); target = tmp_path/'result/example-com'
    result = await build_skill('example.com', [], output_dir=target, existing_package=seed,
        resume_draft=pointer, notes='修复现有取数逻辑', builder_model=model, max_turns=1,
        record_dir=tmp_path/'record')
    assert model.calls == (1 if apply_change else 2)
    assert (result == target) if apply_change else result is None
    assert (seed/'scripts/access.py').read_text() == "value = 'before'\n"
    assert pointer.read_bytes() == original
    if apply_change:
        assert (target/'scripts/access.py').read_text() == "value = 'after'\n"


@pytest.mark.asyncio
@pytest.mark.parametrize('repair', [False, True])
async def test_cli_failure_is_returned_to_builder_and_closing_call_can_repair(tmp_path, monkeypatch, repair):
    from langchain_core.messages import ToolMessage
    from searchos.skills.intent.site import SiteIntentSession
    from searchos.skills.runtime import command_runtime

    executions = []
    async def prepare(self, *args, **kwargs):
        self.state['plan'] = site_plan()
        return self.state['plan']
    async def execute(package, argv, **kwargs):
        if argv[-1] == '--help':
            return {'exit_code': 0, 'stdout': 'usage'}
        code = (package/'scripts/access.py').read_text()
        executions.append(code)
        if 'broken' in code:
            return {'exit_code': 1, 'status': 'failed', 'stdout': json.dumps({
                'status': 'parse_error', 'records': [], 'warnings': ['missing response records']})}
        return {'exit_code': 0, 'stdout': json.dumps({'status': 'ok', 'records': [
            {'title': None, 'source_url': 'https://example.com/item'}], 'warnings': []})}
    monkeypatch.setattr(SiteIntentSession, 'prepare', prepare)
    monkeypatch.setattr(command_runtime, 'run_command', execute)
    class Builder:
        calls = 0
        def bind_tools(self, definitions): return self
        async def ainvoke(self, messages):
            self.calls += 1
            if self.calls == 1:
                return AIMessage(content='', tool_calls=[
                    builder_call('write_file', 'doc', path='SKILL.md',
                        content='---\nname: example-com\ndescription: 获取公开记录\nmetadata:\n'
                                '  searchos-category: access\n  host: example.com\n---\npython scripts/access.py\n'),
                    builder_call('write_file', 'script', path='scripts/access.py', content="value = 'broken'\n"),
                    builder_call('validate_skill', 'first-check')])
            assert self.calls == 2 and '额外的一次收尾' in messages[-1].content
            feedback = next(m for m in messages if isinstance(m, ToolMessage) and m.tool_call_id == 'first-check')
            failure = json.loads(feedback.content)
            assert failure['stage'] == 'examples' and 'missing response records' in failure['error']
            if not repair:
                return AIMessage(content='解析失败，无法修复。')
            return AIMessage(content='', tool_calls=[
                builder_call('edit_file', 'repair', path='scripts/access.py',
                             old_text="value = 'broken'", new_text='value = None'),
                builder_call('validate_skill', 'second-check')])
    builder = Builder(); diagnostics = {}; target = tmp_path/'library/example-com'
    result = await build_skill('example.com', [], output_dir=target, builder_model=builder,
        site_intent=True, max_turns=1, diagnostics=diagnostics, record_dir=tmp_path/'records')
    assert builder.calls == 2
    if not repair:
        assert result is None and not target.exists()
        assert diagnostics['stage'] == 'examples'
        assert (tmp_path/'records/draft.json').exists()
        assert executions == ["value = 'broken'\n"]
    else:
        assert result == target and (target/'scripts/access.py').read_text() == 'value = None\n'
        assert executions == ["value = 'broken'\n", 'value = None\n']


@pytest.mark.asyncio
async def test_closing_call_edit_after_success_requires_revalidation_before_publish(tmp_path, monkeypatch):
    from searchos.skills.pipeline.access import tools

    executions = []
    async def validate(package, name, examples, **kwargs):
        script = package/'scripts/access.py'
        if not script.exists():
            return {'valid': False, 'stage': 'package', 'error': 'missing CLI'}
        code = script.read_text(); executions.append(code)
        return {'valid': 'broken' not in code, 'stage': 'examples', 'error': 'invalid output' if 'broken' in code else ''}
    monkeypatch.setattr(tools, 'validate_access_package', validate)
    class Builder:
        calls = 0
        def bind_tools(self, definitions): return self
        async def ainvoke(self, messages):
            self.calls += 1
            if self.calls == 1:
                return AIMessage(content='尚未完成')
            return AIMessage(content='', tool_calls=[
                builder_call('write_file', 'doc', path='SKILL.md', content='document'),
                builder_call('write_file', 'script', path='scripts/access.py', content='value = None\n'),
                builder_call('validate_skill', 'successful-check'),
                builder_call('edit_file', 'subsequent-edit', path='scripts/access.py',
                             old_text='value = None', new_text="value = 'broken'")])
    builder = Builder(); diagnostics = {}; target = tmp_path/'library/example-com'
    result = await build_skill('example.com', [], output_dir=target, builder_model=builder,
        max_turns=1, diagnostics=diagnostics, record_dir=tmp_path/'records')
    assert builder.calls == 2 and result is None and not target.exists()
    assert diagnostics['stage'] == 'examples'
    assert executions == ['value = None\n', "value = 'broken'\n"]
