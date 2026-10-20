"""站点能力的字段、失败语义与显式 TLS 降级验收。"""
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


def runner(monkeypatch, record=None, *, invalid=None, offline=None):
    calls = []
    async def command(package, argv, **kwargs):
        calls.append((argv, kwargs))
        if argv[-1] == '--help':
            return response({'usage': 'access CLI'})
        inputs = json.loads(argv[-1])
        if not isinstance(inputs, dict):
            return invalid if invalid is not None else response(
                {'status': 'invalid_input', 'records': [], 'warnings': ['input must be an object']}, 1)
        if not kwargs['network']:
            return offline if offline is not None else response(
                {'status': 'network_error', 'records': [], 'warnings': ['network denied']}, 1)
        return response({'status': 'ok', 'records': [record or {'title': 'record', 'source_url': 'https://example.com/a'}],
                         'warnings': []})
    monkeypatch.setattr('searchos.skills.runtime.command_runtime.run_command', command)
    return calls


@pytest.mark.asyncio
@pytest.mark.parametrize('value', [' ', '\n\t', [], {}])
async def test_required_fields_reject_empty_values(tmp_path, monkeypatch, value):
    runner(monkeypatch, {'title': value, 'source_url': 'https://example.com/a'})
    result = await validate_examples(tmp_path, [example()])
    assert not result['valid']
    assert result['capability_id'] == 'search' and 'title' in result['error']


@pytest.mark.asyncio
@pytest.mark.parametrize('source', ['not-a-url', [], {}, 42, 'https://bad host/a'])
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
async def test_failure_probes_run_once_per_capability_with_bounded_network_denial(tmp_path, monkeypatch):
    calls = runner(monkeypatch)
    result = await validate_examples(tmp_path, [example('search'), example('search', 'beta'), example('detail')])
    assert result['valid']
    probes = [(argv, options) for argv, options in calls if argv[-1] != '--help' and not options['network']]
    assert len(probes) == 6
    for capability in ('search', 'detail'):
        inputs = [json.loads(argv[-1]) for argv, options in probes if argv[2] == capability]
        assert inputs == [None, [], {'query': 'alpha'}]
    assert all(options['timeout_s'] <= 15 for argv, options in probes)


@pytest.mark.asyncio
@pytest.mark.parametrize('bad', [
    response({'status': 'ok', 'records': [], 'warnings': []}),
    response({'status': 'invalid_input', 'records': [{'title': 'fake'}], 'warnings': []}, 1),
    response({'status': 'invalid_input', 'records': []}, 1),
    response({'status': 'error', 'records': [], 'warnings': ['uncaught input']}, 1),
    response({'status': 'invalid_input', 'records': [], 'warnings': [], 'fixture': True}, 1),
])
async def test_invalid_input_probe_requires_the_declared_failure_contract(tmp_path, monkeypatch, bad):
    runner(monkeypatch, invalid=bad)
    result = await validate_examples(tmp_path, [example()])
    assert not result['valid'] and result['check_kind'] == 'invalid_input'
    assert result['capability_id'] == 'search' and json.loads(result['argv'][-1]) is None
    assert result['execution']['stdout'] == bad['stdout']


@pytest.mark.asyncio
@pytest.mark.parametrize('bad', [
    response({'status': 'ok', 'records': [{'title': 'cached'}], 'warnings': []}),
    response({'status': 'empty', 'records': [], 'warnings': []}, 1),
    response({'status': 'invalid_input', 'records': [], 'warnings': ['query rejected']}, 1),
    response({'status': 'network_error', 'records': [], 'warnings': []}),
    response({'status': 'network_error', 'records': [], 'warnings': [], 'input_mode': 'fixture'}, 1),
    {'exit_code': -9, 'status': 'timed_out', 'timed_out': True, 'stdout': '', 'stderr': ''},
])
async def test_offline_probe_rejects_success_empty_bad_input_and_timeout(tmp_path, monkeypatch, bad):
    runner(monkeypatch, offline=bad)
    result = await validate_examples(tmp_path, [example()])
    assert not result['valid'] and result['check_kind'] == 'network_denied'
    assert result['capability_id'] == 'search'
    assert result['execution']['stdout'] == bad['stdout']


@pytest.mark.asyncio
async def test_legacy_examples_keep_url_alias_and_skip_capability_probes(tmp_path, monkeypatch):
    calls = runner(monkeypatch, {'title': 'legacy', 'url': 'https://example.com/a'})
    legacy = example()
    legacy.pop('capability_id'); legacy.pop('required_fields')
    assert (await validate_examples(tmp_path, [legacy]))['valid']
    assert len(calls) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize('script,marker', [
    ('ctx.check_hostname = False', 'check_hostname_false'),
    ('ctx.verify_mode = ssl.CERT_NONE', 'certificate_verification_disabled'),
    ('requests.get(url, verify=False)', 'verify_false'),
    ('browser.new_context(ignore_https_errors=True)', 'browser_ignores_https_errors'),
    ('ssl._create_unverified_context()', 'unverified_ssl_context'),
])
async def test_package_gate_rejects_explicit_tls_downgrade_before_execution(tmp_path, monkeypatch, script, marker):
    (tmp_path / 'scripts').mkdir()
    (tmp_path / 'scripts/access.py').write_text(script)
    (tmp_path / 'SKILL.md').write_text('---\nname: example-com\ndescription: 查询记录\nmetadata:\n'
                                     '  searchos-category: access\n  host: example.com\n---\npython scripts/access.py\n')
    calls = runner(monkeypatch)
    result = await validate_access_package(tmp_path, 'example-com', [example()])
    assert not result['valid'] and result['stage'] == 'transport_policy'
    assert result['findings'][0]['marker'] == marker and not calls


@pytest.mark.asyncio
async def test_secure_tls_and_mentions_in_comments_do_not_fail_gate(tmp_path, monkeypatch):
    (tmp_path / 'scripts').mkdir()
    (tmp_path / 'scripts/access.py').write_text('import ssl\nctx = ssl.create_default_context()\n'
                                             '# Never use verify=False or ssl._create_unverified_context()\n')
    (tmp_path / 'SKILL.md').write_text('---\nname: example-com\ndescription: 查询记录\nmetadata:\n'
                                     '  searchos-category: access\n  host: example.com\n---\npython scripts/access.py\n')
    runner(monkeypatch)
    assert (await validate_access_package(tmp_path, 'example-com', [example()]))['valid']


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
async def test_boundary_expectations_use_full_stdout_and_keep_offline_on_positive(tmp_path, monkeypatch, expected, exit_code):
    calls = []
    row = {'title': 'record', 'source_url': 'https://example.com/a'}
    async def command(package, argv, **kwargs):
        calls.append((argv, kwargs))
        if argv[-1] == '--help': return response({'usage': 'access'})
        inputs = json.loads(argv[-1])
        if not isinstance(inputs, dict):
            return response({'status': 'invalid_input', 'records': [], 'warnings': []}, 1)
        if not kwargs['network']:
            return response({'status': 'network_error', 'records': [], 'warnings': ['network denied']}, 1)
        if inputs['query'] == 'boundary':
            payload = {'status': expected, 'records': [row] if expected == 'ok' else [], 'warnings': ['x' * 3000]}
            saved = kwargs['execution_dir']/'boundary'
            saved.mkdir(parents=True); (saved/'stdout.log').write_text(json.dumps(payload))
            return {**response(payload, exit_code), 'stdout': '{"status":', 'execution_id': 'boundary'}
        return response({'status': 'ok', 'records': [row], 'warnings': []})
    monkeypatch.setattr('searchos.skills.runtime.command_runtime.run_command', command)
    boundary = dict(example(query='boundary'), expected_status=expected, check_kind='boundary')
    # 即使调用方把边界例放前面，断网探针仍应选普通成功输入。
    report = await validate_examples(tmp_path, [boundary, example()])
    assert report['valid']
    offline_objects = [json.loads(argv[-1]) for argv, options in calls if not options['network']
                       and argv[-1] != '--help' and isinstance(json.loads(argv[-1]), dict)]
    assert offline_objects == [{'query': 'alpha'}]


@pytest.mark.asyncio
@pytest.mark.parametrize('expected,bad', [
    ('empty', response({'status': 'ok', 'records': [], 'warnings': []})),
    ('empty', response({'status': 'empty', 'records': [], 'warnings': []}, 1)),
    ('empty', response({'status': 'empty', 'records': [{'title': 'record'}], 'warnings': []})),
    ('empty', response({'status': 'empty', 'records': []})),
    ('invalid_input', response({'status': 'invalid_input', 'records': [], 'warnings': []})),
    ('invalid_input', response({'status': 'error', 'records': [], 'warnings': ['not invalid']}, 1)),
    ('invalid_input', {'exit_code': 71, 'status': 'blocked', 'started': False,
                       'stdout': json.dumps({'status': 'invalid_input', 'records': [], 'warnings': []})}),
    ('empty', response({'status': 'empty', 'records': [], 'warnings': [], 'fixture': True})),
    ('empty', response({'status': 'empty', 'records': [], 'warnings': [], 'success': False})),
    ('empty', response({'status': 'empty', 'records': [], 'warnings': [], 'error': 'upstream failed'})),
    ('invalid_input', response({'status': 'invalid_input', 'records': [], 'warnings': [], 'input_mode': 'fixture'}, 1)),
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
async def test_boundary_probe_does_not_swallow_cancellation(tmp_path, monkeypatch):
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
async def test_invalid_boundary_can_explain_error_without_becoming_a_fixture(tmp_path, monkeypatch):
    async def command(package, argv, **kwargs):
        if argv[-1] == '--help': return response({'usage': 'access'})
        inputs = json.loads(argv[-1])
        if not isinstance(inputs, dict) or inputs.get('query') == 'boundary':
            return response({'status': 'invalid_input', 'records': [], 'warnings': [], 'error': 'query is invalid'}, 1)
        if not kwargs['network']:
            return response({'status': 'network_error', 'records': [], 'warnings': []}, 1)
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
