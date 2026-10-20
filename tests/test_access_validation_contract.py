"""Access 包元数据、逐能力 CLI 执行与输出契约。"""
import json

import pytest

from searchos.skills.pipeline.access.valid import validate_access_package, validate_examples


def example(capability='search', query='alpha'):
    return {'capability_id': capability, 'required_fields': ['title', 'source_url'],
            'argv': ['python', 'scripts/access.py', capability, '--input', json.dumps({'query': query})],
            'output': '', 'records_key': 'records'}


def response(payload, exit_code=0):
    return {'exit_code': exit_code, 'status': 'completed' if exit_code == 0 else 'failed',
            'started': True, 'stdout': json.dumps(payload), 'stderr': ''}


def runner(monkeypatch, record=None, *, records=None):
    calls = []
    async def command(package, argv, **kwargs):
        calls.append((argv, kwargs))
        if argv[-1] == '--help':
            return response({'usage': 'access CLI'})
        return response({'status': 'ok', 'records': records if records is not None else [
                            record or {'title': 'record', 'source_url': 'https://example.com/a'}],
                         'warnings': []})
    monkeypatch.setattr('searchos.skills.runtime.command_runtime.run_command', command)
    return calls


@pytest.mark.asyncio
@pytest.mark.parametrize('value', [None, '', ' ', '\n\t', [], {}])
async def test_required_fields_allow_source_empty_values(tmp_path, monkeypatch, value):
    runner(monkeypatch, {'title': value, 'source_url': 'https://example.com/a'})
    result = await validate_examples(tmp_path, [example()])
    assert result['valid']


@pytest.mark.asyncio
async def test_nullable_fields_keep_the_declared_record_shape(tmp_path, monkeypatch):
    record = {'title': 'Public item', 'text': None, 'points': None, 'parent_id': None,
              'source_url': 'https://example.com/a'}
    contract = {**example(), 'required_fields': list(record)}
    runner(monkeypatch, record)
    assert (await validate_examples(tmp_path, [contract]))['valid']

    del record['points']
    result = await validate_examples(tmp_path, [contract])
    assert not result['valid'] and 'points' in result['error']


@pytest.mark.asyncio
@pytest.mark.parametrize('source', [
    'https://publisher.example/articles/42',
    'https://aggregator.example/items/42',
    'https://aggregator.example/feed',
])
@pytest.mark.parametrize('include_retrieval_location', [False, True])
async def test_package_accepts_record_links_without_requiring_target_fetch_or_extra_fields(
        tmp_path, monkeypatch, source, include_retrieval_location):
    (tmp_path/'scripts').mkdir()
    (tmp_path/'SKILL.md').write_text(
        '---\nname: example-aggregator\ndescription: 获取聚合摘要与报道链接\nmetadata:\n'
        '  searchos-category: access\n  host: aggregator.example\n---\n'
        'python scripts/access.py search --input JSON\n')
    (tmp_path/'scripts/access.py').write_text('print("unit test command stub")\n')
    row = {'title': 'Aggregated item', 'summary': 'Summary supplied by the aggregator',
           'source_url': source}
    if include_retrieval_location:
        row['retrieved_from'] = 'https://aggregator.example/feed'
    calls = runner(monkeypatch, row)
    contract = {**example(), 'required_fields': ['title', 'summary', 'source_url']}
    result = await validate_access_package(tmp_path, 'example-aggregator', [contract])
    assert result['valid'], result
    assert all(argv[:2] == ['python', 'scripts/access.py'] for argv, _ in calls)
    assert all(source not in argv for argv, _ in calls)


@pytest.mark.asyncio
@pytest.mark.parametrize('source', [None, '', ' ', 'not-a-url', [], {}, 42, 'https://bad host/a'])
async def test_url_alias_cannot_mask_invalid_required_source_url(tmp_path, monkeypatch, source):
    runner(monkeypatch, {'title': 'record', 'source_url': source, 'url': 'https://example.com/a'})
    result = await validate_examples(tmp_path, [example()])
    assert not result['valid'] and 'source_url' in result['error']


@pytest.mark.asyncio
@pytest.mark.parametrize('value', [0, False])
async def test_required_fields_preserve_valid_falsy_scalars(tmp_path, monkeypatch, value):
    runner(monkeypatch, {'title': value, 'source_url': 'https://example.com/a'})
    assert (await validate_examples(tmp_path, [example()]))['valid']


@pytest.mark.asyncio
async def test_validation_executes_only_registered_commands_and_help_once(tmp_path, monkeypatch):
    cases = [example('search'), example('search', 'beta'), example('detail')]
    calls = runner(monkeypatch)
    assert (await validate_examples(tmp_path, cases))['valid']
    assert [argv for argv, _ in calls] == [['python', 'scripts/access.py', '--help'],
                                          *[case['argv'] for case in cases]]
    assert all(options['network'] for _, options in calls[1:])
    assert len({str(options['work_dir']) for _, options in calls[1:]}) == len(cases)


@pytest.mark.asyncio
async def test_legacy_examples_keep_url_alias(tmp_path, monkeypatch):
    calls = runner(monkeypatch, {'title': 'legacy', 'url': 'https://example.com/a'})
    legacy = example()
    legacy.pop('capability_id'); legacy.pop('required_fields')
    assert (await validate_examples(tmp_path, [legacy]))['valid']
    assert len(calls) == 2


@pytest.mark.parametrize('expected', ['error', None, [], ''])
def test_host_examples_reject_unknown_expected_status(tmp_path, expected):
    from searchos.skills.pipeline.access.tools import BuilderWorkspace
    workspace = BuilderWorkspace(tmp_path/'example-com')
    try:
        with pytest.raises(ValueError, match='expected_status'):
            workspace.set_validation_examples([dict(example(), expected_status=expected, check_kind='boundary')])
    finally:
        workspace.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('expected,exit_code', [('empty', 0), ('invalid_input', 1), ('ok', 0)])
async def test_boundary_expectations_use_full_stdout_and_run_only_declared_inputs(tmp_path, monkeypatch, expected, exit_code):
    calls = []
    row = {'title': 'record', 'source_url': 'https://example.com/a'}
    async def command(package, argv, **kwargs):
        calls.append((argv, kwargs))
        if argv[-1] == '--help': return response({'usage': 'access'})
        inputs = json.loads(argv[-1])
        if inputs['query'] == 'boundary':
            payload = {'status': expected, 'records': [row] if expected == 'ok' else [], 'warnings': ['x' * 3000]}
            saved = kwargs['execution_dir']/'boundary'
            saved.mkdir(parents=True); (saved/'stdout.log').write_text(json.dumps(payload))
            return {**response(payload, exit_code), 'stdout': '{"status":', 'execution_id': 'boundary'}
        return response({'status': 'ok', 'records': [row], 'warnings': []})
    monkeypatch.setattr('searchos.skills.runtime.command_runtime.run_command', command)
    boundary = dict(example(query='boundary'), expected_status=expected, check_kind='boundary')
    report = await validate_examples(tmp_path, [boundary, example()])
    assert report['valid']
    executions = [(argv, options) for argv, options in calls if argv[-1] != '--help']
    assert [json.loads(argv[-1]) for argv, _ in executions] == [{'query': 'boundary'}, {'query': 'alpha'}]
    assert all(options['network'] for _, options in executions)


@pytest.mark.asyncio
@pytest.mark.parametrize('expected,bad', [
    ('empty', response({'status': 'ok', 'records': [], 'warnings': []})),
    ('empty', response({'status': 'empty', 'records': [], 'warnings': []}, 1)),
    ('empty', response({'status': 'empty', 'records': [{'title': 'record'}], 'warnings': []})),
    ('invalid_input', response({'status': 'invalid_input', 'records': [], 'warnings': []})),
    ('invalid_input', response({'status': 'error', 'records': [], 'warnings': ['not invalid']}, 1)),
    ('invalid_input', {'exit_code': 71, 'status': 'blocked', 'started': False,
                       'stdout': json.dumps({'status': 'invalid_input', 'records': [], 'warnings': []})}),
])
async def test_boundary_expectation_rejects_mismatched_protocol(tmp_path, monkeypatch, expected, bad):
    async def command(package, argv, **kwargs):
        if argv[-1] == '--help': return response({'usage': 'access'})
        if json.loads(argv[-1]) == {'query': 'alpha'}:
            return response({'status': 'ok', 'records': [{'title': 'record', 'source_url': 'https://example.com/a'}]})
        return bad
    monkeypatch.setattr('searchos.skills.runtime.command_runtime.run_command', command)
    result = await validate_examples(tmp_path, [example(), dict(example(query='boundary'), expected_status=expected, check_kind='boundary')])
    assert not result['valid'] and result['check_kind'] == 'boundary'
    assert result['expected_status'] == expected and result['execution']['stdout'] == bad['stdout']


@pytest.mark.asyncio
async def test_boundary_execution_does_not_swallow_cancellation(tmp_path, monkeypatch):
    import asyncio
    async def command(package, argv, **kwargs):
        if argv[-1] == '--help': return response({'usage': 'access'})
        raise asyncio.CancelledError()
    monkeypatch.setattr('searchos.skills.runtime.command_runtime.run_command', command)
    with pytest.raises(asyncio.CancelledError):
        await validate_examples(tmp_path, [dict(example(query='boundary'), expected_status='empty', check_kind='boundary'), example()])


@pytest.mark.asyncio
@pytest.mark.parametrize('expected', ['ok', 'empty', 'invalid_input'])
async def test_boundary_only_cases_cannot_replace_positive_capability_examples(tmp_path, monkeypatch, expected):
    calls = runner(monkeypatch)
    result = await validate_examples(tmp_path, [dict(example(), expected_status=expected, check_kind='boundary')])
    assert not result['valid'] and result['check_kind'] == 'contract'
    assert 'positive' in result['error'] and not calls


@pytest.mark.asyncio
async def test_each_capability_still_requires_its_own_positive_example(tmp_path, monkeypatch):
    calls = runner(monkeypatch)
    result = await validate_examples(tmp_path, [example('search'),
        dict(example('detail'), expected_status='empty', check_kind='boundary')])
    assert not result['valid'] and result['capability_id'] == 'detail' and not calls


@pytest.mark.asyncio
async def test_invalid_boundary_preserves_structured_error_details(tmp_path, monkeypatch):
    async def command(package, argv, **kwargs):
        if argv[-1] == '--help': return response({'usage': 'access'})
        inputs = json.loads(argv[-1])
        if inputs.get('query') == 'boundary':
            return response({'status': 'invalid_input', 'records': [], 'warnings': [], 'error': 'query is invalid'}, 1)
        return response({'status': 'ok', 'records': [{'title': 'record', 'source_url': 'https://example.com/a'}]})
    monkeypatch.setattr('searchos.skills.runtime.command_runtime.run_command', command)
    result = await validate_examples(tmp_path, [example(),
        dict(example(query='boundary'), expected_status='invalid_input', check_kind='boundary')])
    assert result['valid']


@pytest.mark.asyncio
async def test_compiled_boundary_expectations_are_copied_and_locked(tmp_path):
    from searchos.skills.pipeline.access.tools import BuilderWorkspace
    workspace = BuilderWorkspace(tmp_path/'example-com')
    cases = [example(), dict(example(query='boundary'), expected_status='empty', check_kind='boundary')]
    try:
        workspace.set_validation_examples(cases)
        cases[1]['expected_status'] = 'ok'
        result = await workspace.dispatch('register_example', {'argv': example()['argv'], 'replace_index': 1})
        assert result['error'] == 'host_validation_examples_locked'
        assert workspace.examples[1]['expected_status'] == 'empty'
    finally:
        workspace.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('metadata_category,host,body,error', [
    ('access', 'other.example', '使用此 CLI 查询公开记录。', 'expected example.com'),
    ('access', 'example.com', '', 'nonempty SKILL.md body'),
    ('access', 'example.com', ' \n\t ', 'nonempty SKILL.md body'),
    (None, 'example.com', '使用此 CLI 查询公开记录。', 'metadata.searchos-category'),
    ('strategy', 'example.com', '使用此 CLI 查询公开记录。', 'metadata.searchos-category'),
])
async def test_request_metadata_checks_fail_before_cli_execution(
        tmp_path, monkeypatch, metadata_category, host, body, error):
    (tmp_path/'scripts').mkdir()
    (tmp_path/'scripts/access.py').write_text('print("unit test command stub")\n')
    category_line = f'  searchos-category: {metadata_category}\n' if metadata_category else ''
    # 顶层 category 不能遮蔽缺失或错误的 metadata 分类。
    (tmp_path/'SKILL.md').write_text(
        '---\nname: example-com\ndescription: 查询记录\ncategory: access\nmetadata:\n'
        f'{category_line}  host: {host}\n---\n{body}')
    calls = runner(monkeypatch)
    report = await validate_access_package(
        tmp_path, 'example-com', [example()], expected_host='example.com')
    assert not report['valid'] and report['stage'] == 'package'
    assert error in report['error']
    assert calls == []


@pytest.mark.asyncio
async def test_workspace_expected_host_changes_invalidate_successful_validation(tmp_path, monkeypatch):
    from searchos.skills.pipeline.access.tools import BuilderWorkspace
    from searchos.skills.pipeline.valid import validate_request_package
    from searchos.skills.intent.models import SkillRequest

    workspace = BuilderWorkspace(tmp_path/'example-com')
    try:
        assert workspace.expected_host is None
        await workspace.write_file('SKILL.md',
            '---\nname: example-com\ndescription: 查询记录\nmetadata:\n'
            '  searchos-category: access\n  host: EXAMPLE.COM\n---\npython scripts/access.py\n')
        await workspace.write_file('scripts/access.py', 'print("unit test command stub")\n')
        workspace.set_validation_examples([example()])
        workspace.expected_host = 'example.com'
        runner(monkeypatch)
        assert (await workspace.validate())['valid']
        accepted = workspace.checked_state
        assert accepted == workspace.validation_state()
        validate_request_package(workspace.output_dir,
            SkillRequest('access', 'example-com', '查询记录', host='example.com',
                         probe_urls=('https://example.com',)))
        workspace.expected_host = 'other.example'
        assert workspace.validation_state() != accepted
        report = await workspace.validate()
        assert not report['valid'] and 'expected other.example' in report['error']
        assert not workspace.last_validation['valid']
    finally:
        workspace.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('defect,error', [
    ('host', 'expected example.com'),
    ('body', 'nonempty SKILL.md body'),
    ('category', 'metadata.searchos-category'),
])
async def test_builder_repairs_request_metadata_within_its_call_budget(tmp_path, monkeypatch, defect, error):
    from langchain_core.messages import AIMessage, ToolMessage
    from searchos.skills.pipeline.access.run import build_skill
    from searchos.skills.pipeline.valid import validate_request_package
    from searchos.skills.intent.models import SkillRequest

    correct = ('---\nname: example-com\ndescription: 查询记录\ncategory: access\nmetadata:\n'
               '  searchos-category: access\n  host: example.com\n---\npython scripts/access.py\n')
    malformed = {
        'host': correct.replace('host: example.com', 'host: other.example'),
        'body': correct.rsplit('---\n', 1)[0] + '---\n',
        'category': correct.replace('  searchos-category: access\n', ''),
    }[defect]
    class Builder:
        calls = 0
        def bind_tools(self, definitions): return self
        async def ainvoke(self, messages):
            self.calls += 1
            if self.calls == 1:
                operations = [
                    ('write_file', {'path': 'SKILL.md', 'content': malformed}),
                    ('write_file', {'path': 'scripts/access.py', 'content': 'print("stub")\n'}),
                    ('validate_skill', {}),
                ]
            else:
                assert self.calls == 2
                feedback = json.loads(next(message.content for message in messages
                    if isinstance(message, ToolMessage) and message.tool_call_id == '1-2'))
                assert feedback['stage'] == 'package' and error in feedback['error']
                operations = [
                    ('write_file', {'path': 'SKILL.md', 'content': correct}),
                    ('validate_skill', {}),
                ]
            return AIMessage(content='', tool_calls=[
                {'id': f'{self.calls}-{index}', 'name': name, 'args': args}
                for index, (name, args) in enumerate(operations)])
    runner(monkeypatch)
    builder = Builder(); target = tmp_path/'library/example-com'
    result = await build_skill('example.com', [], output_dir=target, builder_model=builder,
        validation_examples=[example()], max_turns=3, record_dir=tmp_path/'records')
    assert result == target and builder.calls == 2
    validate_request_package(target,
        SkillRequest('access', 'example-com', '查询记录', host='example.com',
                     probe_urls=('https://example.com',)))
