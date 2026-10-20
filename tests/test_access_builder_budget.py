"""生成预算、收尾阶段与失败诊断回归。"""
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
async def test_site_final_call_still_uses_structured_submission(tmp_path):
    from types import SimpleNamespace
    from searchos.skills.intent.site import SiteIntentSession, validate_plan
    from searchos.skills.pipeline.access.records import BuildRecord
    class Model:
        calls = 0
        def bind_tools(self, definitions): return self
        async def ainvoke(self, messages):
            self.calls += 1
            if self.calls == 3:
                assert 'submit_site_plan' in messages[-1].content
                assert '不再调用工具' not in messages[-1].content
                proposal = site_plan()
            else:
                proposal = {'capabilities': []}
            return AIMessage(content='', tool_calls=[{'name':'submit_site_plan', 'args':proposal, 'id':str(self.calls)}])
    model = Model()
    session = SiteIntentSession(model, SimpleNamespace(), BuildRecord(tmp_path/'record'))
    session.state['observations'] = [{'id':'obs-1', 'tool':'web_open', 'usable':True,
                                    'result':{'content':'public page', 'live_evidence':True}}]
    result = await session.converse([], 3, validator=lambda v: validate_plan(v, session.state['observations']), research_turns=0)
    assert result['capabilities'][0]['id'] == 'latest' and model.calls == 3


@pytest.mark.asyncio
async def test_site_without_page_evidence_stops_before_format_repair_calls(tmp_path):
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
            return AIMessage(content='', tool_calls=[{'name':'web_search', 'args':{'query':'site docs'}, 'id':str(self.calls)}])
    model = Model()
    session = SiteIntentSession(model, SimpleNamespace(browser=Browser()), BuildRecord(tmp_path/'record'))
    session.observe('web_open', {'id_or_url':'https://example.com'}, {'content':'[FETCH_ERROR] network_failure'}, 'intent')
    with pytest.raises(ValueError, match='site_page_evidence_unavailable'):
        await session.converse([], 5, validator=lambda v: validate_plan(v, session.state['observations']), research_turns=2)
    assert model.calls == 2
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
        await session.converse([], 3, validator=lambda v: validate_plan(v, session.state['observations']), research_turns=0)
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
async def test_reserve_phase_allows_focused_research_and_records_exhaustion(tmp_path):
    class Model:
        def __init__(self): self.prompts = []
        def bind_tools(self, tools): return self
        async def ainvoke(self, messages):
            self.prompts.append(messages[-1].content)
            return AIMessage(content='', tool_calls=[dict(id=str(len(self.prompts)), name='web_search', args={'query':'example.com code 37 proxy'})])
    from searchos.skills.pipeline.access import run
    calls = []
    async def tool(workspace, call):
        calls.append(call['name'])
        from langchain_core.messages import ToolMessage
        return ToolMessage(content='research', tool_call_id=call['id'])
    # 两轮均可查证具体错误，收尾阶段仍受总轮数限制。
    from unittest.mock import patch
    model = Model(); diagnostics = {}
    with patch.object(run, 'run_tool', tool):
        assert await build_skill('example.com', [], output_dir=tmp_path/'skill', builder_model=model,
            max_turns=2, record_dir=tmp_path/'record', diagnostics=diagnostics) is None
    assert calls == ['web_search', 'web_search']
    assert any('收尾' in str(prompt) for prompt in model.prompts)
    assert diagnostics['exit_reason'] == 'max_turns'
    assert diagnostics['turns_completed'] == 2
    events = [json.loads(line) for line in (tmp_path/'record/events.jsonl').read_text().splitlines()]
    assert any(event['event'] == 'repair_phase' for event in events)
    assert not any(event.get('blocked') for event in events)


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


@pytest.fixture
def staged_builder(tmp_path, monkeypatch):
    """只执行真实文件工具，外部探测与验收由本地替身记录。"""
    from langchain_core.messages import ToolMessage
    from searchos.skills.pipeline.access import run
    from searchos.skills.pipeline.access.tools import BuilderWorkspace
    from searchos.skills.pipeline.drafts import save_draft
    files = {'SKILL.md': '---\nname: example-com\ndescription: 查询记录\nmetadata:\n'
                        '  searchos-category: access\n  host: example.com\n---\npython scripts/access.py\n',
             'scripts/access.py': 'print(1)\n'}
    actual = []
    original_tool = run.run_tool
    async def tool(workspace, call):
        actual.append(call['id'])
        if call['name'] in {'write_file', 'edit_file', 'read_file'}:
            return await original_tool(workspace, call)
        return ToolMessage(content='{"observed":"local test"}', tool_call_id=call['id'])
    async def invalid(*args, **kwargs):
        return {'valid': False, 'stage': 'examples', 'error': 'controlled validation failure'}
    monkeypatch.setattr(run, 'run_tool', tool)
    monkeypatch.setattr(run, 'validate_access_package', invalid)
    monkeypatch.setattr(BuilderWorkspace, 'validate', invalid)
    async def execute(steps, *, source='new', discovery_turns=0):
        options = {}
        if source != 'new':
            seed = tmp_path/'seed'
            for name, content in files.items():
                target = seed/name; target.parent.mkdir(parents=True, exist_ok=True); target.write_text(content)
            if source == 'update':
                options['existing_package'] = seed
            else:
                options['resume_draft'] = save_draft(tmp_path/'previous', seed, files,
                    name='example-com', examples=[], require_host=True, validation=await invalid())
        class Model:
            turn = 0
            def bind_tools(self, definitions): return self
            async def ainvoke(self, messages):
                calls = steps[self.turn]; self.turn += 1
                return AIMessage(content='', tool_calls=calls)
        await build_skill('example.com', [], output_dir=tmp_path/'library/example-com', builder_model=Model(),
            max_turns=len(steps), discovery_turns=discovery_turns, record_dir=tmp_path/'record', **options)
        events = [json.loads(line) for line in (tmp_path/'record/events.jsonl').read_text().splitlines()]
        return actual, events
    execute.files = files
    return execute


def builder_call(name, call_id, **args):
    return {'name': name, 'id': call_id, 'args': args}


@pytest.mark.asyncio
@pytest.mark.parametrize('source', ['update', 'resume'])
async def test_seeded_package_requires_current_episode_progress_before_more_python(staged_builder, source):
    call = builder_call
    actual, events = await staged_builder([
        [call('run_python', 'old-core', code='print(1)')],
        [call('write_file', 'same-write', path='scripts/access.py', content='print(1)\n')],
        [call('run_python', 'unchanged-core', code='print(1)')],
        [call('write_file', 'diagnosis', path='references/diagnosis.md',
              content='观察来源 https://example.com/：列表结构已变化，下一步用 exec 复验解析器。'),
         call('run_python', 'after-progress', code='print(1)')],
    ], source=source)
    assert 'old-core' not in actual and 'unchanged-core' not in actual
    assert 'after-progress' in actual
    assert sum(event['event'] == 'discovery_call_deferred' for event in events) == 2


@pytest.mark.asyncio
async def test_new_package_needs_core_and_same_batch_writes_take_effect(staged_builder):
    call = builder_call
    actual, events = await staged_builder([
        [call('write_file', 'diagnosis', path='references/diagnosis.md', content='已观察公开入口。'),
         call('run_python', 'without-core', code='print(1)')],
        [*[call('write_file', path, path=path, content=content) for path, content in staged_builder.files.items()],
         call('run_python', 'with-core', code='print(1)')],
    ])
    assert 'without-core' not in actual and 'with-core' in actual


@pytest.mark.asyncio
async def test_explicit_none_keeps_unrestricted_python_probes(staged_builder):
    actual, events = await staged_builder([
        [builder_call('run_python', str(index), code='print(1)')] for index in range(3)
    ], source='update', discovery_turns=None)
    assert actual == ['0', '1', '2']
    assert not any(event['event'] == 'discovery_call_deferred' for event in events)


@pytest.mark.asyncio
async def test_progress_gate_does_not_block_debugging_research_or_intent_tools(staged_builder):
    calls = [builder_call(name, name, **args) for name, args in [
        ('exec', {'argv': ['python', 'scripts/access.py']}), ('validate_skill', {}),
        ('read_file', {'path': 'SKILL.md'}), ('web_search', {'query': 'source docs'}),
        ('web_open', {'id_or_url': 'https://example.com/docs'}), ('web_find', {'pattern': 'API'}),
        ('ask_intent_agent', {'capability_id': 'search', 'question': '入口变化如何处理？', 'evidence_ids': ['obs-1']}),
    ]]
    actual, events = await staged_builder([calls])
    assert actual == [call['id'] for call in calls]
    assert not any(event['event'] == 'discovery_call_deferred' for event in events)


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
async def test_two_call_local_builder_can_read_long_file_then_edit_with_final_budget(tmp_path, monkeypatch, locked):
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
    monkeypatch.setattr(run, 'validate_access_package', local_validation)
    monkeypatch.setattr(tools, 'validate_access_package', local_validation)
    class LocalModel:
        calls = 0
        def bind_tools(self, definitions): return self
        async def ainvoke(self, messages):
            self.calls += 1
            assert f'剩余 {3-self.calls} 次模型调用（含本轮）' in messages[-1].content
            if self.calls == 1:
                return AIMessage(content='', tool_calls=[builder_call('read_file', 'read-long', path='scripts/access.py')])
            assert '最后一次模型调用' in messages[-1].content
            if locked: assert '固定验收样例' in messages[-1].content
            read = next(message for message in messages if isinstance(message, ToolMessage) and message.tool_call_id == 'read-long')
            observed = json.loads(read.content)
            assert observed['content'] == original and observed['total_chars'] == 14307
            assert not observed['truncated'] and observed['next_offset'] is None
            return AIMessage(content='', tool_calls=[builder_call('edit_file', 'edit-tail', path='scripts/access.py',
                old_text="value = 'before'", new_text="value = 'after'")])
    model = LocalModel(); diagnostics = {}; target = tmp_path/'library/example-com'
    examples = [{'argv': ['python', 'scripts/access.py'], 'output': '', 'records_key': 'records'}] if locked else None
    result = await build_skill('example.com', [], output_dir=target, existing_package=seed,
        validation_examples=examples, builder_model=model, max_turns=2, diagnostics=diagnostics,
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
