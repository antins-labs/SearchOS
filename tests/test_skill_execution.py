"""技能协议测试：模拟执行器，保留真实工作目录、记录与产物。"""
import asyncio
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from searchos.tools import skill_execution as se
from searchos.tools.search_state import _workspace_var, _current_task_id_var, _source_scope_var
from searchos.skills.core.schema import parse_skill_file
from searchos.socm.workspace import WorkspaceManager
from searchos.tools.simple_browser import state, tools

_REAL_SKILL = se._skill


@pytest.fixture
def context(tmp_path, monkeypatch):
    package = tmp_path / 'sample-skill'
    package.mkdir()
    (package / 'SKILL.md').write_text('---\nname: sample-skill\ndescription: Sample CLI\nmetadata:\n  searchos-category: access\n---\nOriginal instructions\n')
    (package / 'run.py').write_text('print(1)')
    skill = parse_skill_file(package)
    monkeypatch.setattr(se, '_skill', lambda name: skill)
    root = tmp_path / 'session'
    ws = WorkspaceManager(tmp_path, session_id='session')
    ws.create()
    monkeypatch.setattr(ws, 'load_state', lambda: SimpleNamespace(intent='original research query'))
    tokens = [(state._browser_var, state._browser_var.set(state.BrowserState())), (_workspace_var, _workspace_var.set(ws)), (_current_task_id_var, _current_task_id_var.set('task-a')),
              (_source_scope_var, _source_scope_var.set({'mode': 'web'}))]
    yield root, package
    for var, token in reversed(tokens):
        var.reset(token)


def execute(call='call-1', argv=None, **kwargs):
    return se.exec_skill.coroutine('sample-skill', argv or ['python', 'run.py'], call, **kwargs)


def install_runner(monkeypatch, payload=None):
    calls = []
    async def runtime(skill_dir, argv, *, work_dir, execution_dir, **kwargs):
        calls.append({'work': work_dir, 'skill': skill_dir, **kwargs})
        execution_id = kwargs['execution_id']
        saved = execution_dir / execution_id
        artifact = saved / 'artifacts' / 'result.json'
        se._write_json(artifact, payload or {'message': 'diagnostic'})
        result = {'execution_id': execution_id, 'status': 'completed', 'started': True,
                  'exit_code': 0, 'stdout': '', 'stderr': '', 'truncated': False,
                  'artifacts': [{'id': 'result.json', 'path': 'result.json', 'sha256': hashlib.sha256(artifact.read_bytes()).hexdigest()}]}
        se._write_json(saved / 'record.json', result)
        return result
    monkeypatch.setattr('searchos.skills.runtime.command_runtime.run_command', runtime)
    return calls


def test_requires_load_and_freezes_package(context, monkeypatch):
    calls = install_runner(monkeypatch)
    response, _ = asyncio.run(execute())
    assert 'load_skill' in json.loads(response)['error']
    loaded = se.load_package('sample-skill')
    (context[1] / 'SKILL.md').write_text('changed')
    assert se.load_package('sample-skill')['body'] == loaded['body']
    asyncio.run(execute())
    assert len(calls) == 1
    assert calls[0]['skill'] != context[1]


def test_replay_and_conflicting_call_id(context, monkeypatch):
    calls = install_runner(monkeypatch)
    se.load_package('sample-skill')
    asyncio.run(execute())
    response, artifact = asyncio.run(execute())
    assert json.loads(response)['replayed']
    assert artifact['execution']['started'] is False
    response, _ = asyncio.run(execute(argv=['python', 'run.py', '--different']))
    assert 'different request' in json.loads(response)['error']
    assert len(calls) == 1


def test_task_isolation_and_shared_saved_pages(context, monkeypatch):
    calls = install_runner(monkeypatch)
    se.load_package('sample-skill')
    result = json.loads(asyncio.run(execute())[0])
    assert 'artifacts' not in result
    _current_task_id_var.set('task-b')
    state._browser_var.set(state.BrowserState())
    assert 'diagnostic' in asyncio.run(tools.open.ainvoke({'id_or_url': result['page_url']}))
    se.load_package('sample-skill')
    asyncio.run(execute())
    assert calls[0]['work'] != calls[1]['work']


@pytest.mark.parametrize('payload', [
    {'fixture': True, 'sources': []},
    {'input_mode': 'fixture', 'sources': [{'url': 'https://example.org', 'content': 'fake'}]},
    {'sources': [{'input_mode': 'fixture', 'url': 'https://example.org', 'content': 'fake'}]},
])
def test_diagnostics_and_fixtures_never_become_evidence(context, monkeypatch, payload):
    install_runner(monkeypatch, payload)
    se.load_package('sample-skill')
    result = json.loads(asyncio.run(execute())[0])
    state._browser_var.set(state.BrowserState())
    message = asyncio.run(tools.open.ainvoke({'name': 'open', 'args': {'id_or_url': result['page_url']}, 'id': 'read', 'type': 'tool_call'}))
    assert message.artifact['page_source']['evidence_eligible'] is False
    found = asyncio.run(tools.find.ainvoke({'name': 'find', 'args': {'pattern': 'fixture|failed'}, 'id': 'find', 'type': 'tool_call'}))
    if found.artifact and found.artifact.get('page_source'):
        assert found.artifact['page_source']['evidence_eligible'] is False


def test_failed_legacy_has_no_evidence_and_preserves_query(context, monkeypatch):
    seen = {}
    async def legacy(directory, params, *, query, policy):
        seen.update(query=query, timeout=policy.timeout_s, params=params)
        return {'error': 'failed', 'sources': [{'url': 'https://example.org', 'content': 'not evidence'}]}
    monkeypatch.setattr('searchos.skills.runtime.legacy.executor_runtime.run_executor', legacy)
    (context[1] / 'executor.py').write_text('unused')
    (context[1] / 'SKILL.md').rename(context[1] / 'skill.md')
    se.load_package('sample-skill')
    result = json.loads(asyncio.run(execute(argv=['legacy-executor', '--params', '{}'], timeout_s=3))[0])
    assert seen == {'query': 'original research query', 'timeout': 3, 'params': {}}
    assert result['status'] == 'failed'
    state._browser_var.set(state.BrowserState())
    message = asyncio.run(tools.open.ainvoke({'name': 'open', 'args': {'id_or_url': result['page_url']}, 'id': 'read', 'type': 'tool_call'}))
    assert message.artifact['page_source']['evidence_eligible'] is False
    found = asyncio.run(tools.find.ainvoke({'name': 'find', 'args': {'pattern': 'fixture|failed'}, 'id': 'find', 'type': 'tool_call'}))
    if found.artifact and found.artifact.get('page_source'):
        assert found.artifact['page_source']['evidence_eligible'] is False


def test_local_scope_denied(context, monkeypatch):
    calls = install_runner(monkeypatch)
    se.load_package('sample-skill')
    _source_scope_var.set({'mode': 'local'})
    result = json.loads(asyncio.run(execute())[0])
    assert result['status'] == 'blocked'
    assert calls == []


def test_cancel_releases_lock_and_receipt_prevents_rerun(context, monkeypatch):
    se.load_package('sample-skill')
    calls = []
    async def runtime(*args, **kwargs):
        calls.append(1)
        await asyncio.sleep(100)
    monkeypatch.setattr('searchos.skills.runtime.command_runtime.run_command', runtime)
    async def check():
        running = asyncio.create_task(execute())
        await asyncio.sleep(.02)
        blocked = json.loads((await execute('other'))[0])
        assert 'another command' in blocked['error']
        running.cancel()
        with pytest.raises(asyncio.CancelledError):
            await running
        replay = json.loads((await execute())[0])
        assert replay['status'] == 'cancelled' and replay['replayed']
        install_runner(monkeypatch)
        result = json.loads((await execute('next'))[0])
        assert result['status'] == 'completed'
    asyncio.run(check())
    assert len(calls) == 1


@pytest.mark.parametrize('policy', [{'access_deny': ['sample-skill']}, {'access_only': []}, {'access_only': ['other']}])
def test_explicit_skill_scope_checked(context, monkeypatch, policy):
    from searchos.tools import skill_catalog
    from searchos.config.settings import settings
    skill = parse_skill_file(context[1])
    monkeypatch.setattr(skill_catalog, '_registry', lambda: SimpleNamespace(get=lambda _: skill))
    monkeypatch.setattr(settings, 'enable_skills', True)
    monkeypatch.setattr(se, '_skill', _REAL_SKILL)
    token = skill_catalog._skill_access_policy_var.set(policy)
    try:
        with pytest.raises(ValueError, match='unavailable'):
            se.load_package('sample-skill')
    finally:
        skill_catalog._skill_access_policy_var.reset(token)


def test_missing_workspace_is_explicit(context):
    _workspace_var.set(None)
    with pytest.raises(ValueError, match='workspace'):
        se.load_package('sample-skill')


def test_ordinary_json_registers_saved_page_without_rerun(context, monkeypatch):
    calls = install_runner(monkeypatch, {'records': [{'name': 'original result'}]})
    se.load_package('sample-skill')
    result = json.loads(asyncio.run(execute())[0])
    for _ in range(2):
        state._browser_var.set(state.BrowserState())
        message = asyncio.run(tools.open.ainvoke({'name': 'open', 'args': {'id_or_url': result['page_url']}, 'id': 'read', 'type': 'tool_call'}))
        assert 'original result' in message.content
        assert message.artifact['page_source']['evidence_eligible'] is True
    replay = json.loads(asyncio.run(execute())[0])
    assert replay['page_url'] == result['page_url']
    assert len(calls) == 1


def test_registration_rejects_tampered_snapshot(context, monkeypatch):
    from searchos.tools.simple_browser.execution_pages import register_execution_pages
    install_runner(monkeypatch)
    binding = se.load_package('sample-skill')
    result = json.loads(asyncio.run(execute())[0])
    saved = context[0] / 'skill_executions' / result['execution_id']
    record = json.loads((saved / 'record.json').read_text())
    (saved / 'artifacts/result.json').write_text('tampered')
    pages = register_execution_pages(record, binding, saved, 'task-a')
    assert pages['pages_total'] == 0
    assert 'hash mismatch' in pages['unrendered'][0]['reason']


def test_invalid_legacy_call_replays_known_failure(context):
    se.load_package('sample-skill')
    first = json.loads(asyncio.run(execute(argv=['legacy-executor', 'bad']))[0])
    second = json.loads(asyncio.run(execute(argv=['legacy-executor', 'bad']))[0])
    assert first['status'] == second['status'] == 'blocked'
    assert first['error'] == second['error']
    assert second['replayed']


def test_portable_package_cannot_downgrade_to_legacy(context):
    (context[1] / 'executor.py').write_text('unused')
    se.load_package('sample-skill')
    result = json.loads(asyncio.run(execute(argv=['legacy-executor', '--params', '{}']))[0])
    assert result['status'] == 'blocked'
    assert 'portable packages' in result['error']


def test_snapshot_tampering_detected(context):
    binding = se.load_package('sample-skill')
    (Path(binding['directory']) / 'run.py').write_text('changed')
    with pytest.raises(ValueError, match='hash changed'):
        se.load_package('sample-skill')


@pytest.mark.parametrize('started', [True, False])
def test_cancel_uses_saved_start_marker(context, monkeypatch, started):
    se.load_package('sample-skill')
    async def runtime(*args, **kwargs):
        try:
            await asyncio.sleep(100)
        except asyncio.CancelledError:
            se._write_json(kwargs['execution_dir'] / kwargs['execution_id'] / 'record.json',
                           {'status': 'cancelled', 'started': started})
            raise
    monkeypatch.setattr('searchos.skills.runtime.command_runtime.run_command', runtime)
    async def check():
        running = asyncio.create_task(execute())
        await asyncio.sleep(.01)
        running.cancel()
        with pytest.raises(asyncio.CancelledError):
            await running
        assert se.execution_started('call-1') is started
    asyncio.run(check())


def test_large_result_read_with_open_find_after_reset(context, monkeypatch):
    payload = {'records': [{'name': f'Hotel {i}', 'description': 'A detailed hotel description. ' * 20} for i in range(500)]}
    calls = install_runner(monkeypatch, payload)
    se.load_package('sample-skill')
    result = json.loads(asyncio.run(execute())[0])
    state._browser_var.set(state.BrowserState())
    first = asyncio.run(tools.open.ainvoke({'id_or_url': result['page_url']}))
    assert 'Hotel 0' in first and 'Hotel 499' not in first
    found = asyncio.run(tools.find.ainvoke({'name': 'find', 'args': {'pattern': 'Hotel 499'}, 'id': 'find', 'type': 'tool_call'}))
    assert 'Hotel 499' in found.content
    assert found.artifact['page_source']['evidence_eligible'] is True
    assert len(calls) == 1


@pytest.mark.parametrize('stdout,kind', [('help text', 'diagnostic'), ('{"records": [1]}', 'skill_result'), ('{"fixture": true}', 'fixture')])
def test_stdout_page_classification(context, stdout, kind):
    from searchos.tools.simple_browser.execution_pages import register_execution_pages
    binding = se.load_package('sample-skill')
    result = {'execution_id': 'stdout-run', 'status': 'completed', 'stdout': stdout, 'stderr': 'warning', 'artifacts': []}
    pages = register_execution_pages(result, binding, context[0] / 'skill_executions/stdout-run', 'task-a')
    assert pages['pages'][0]['kind'] == kind
    assert pages['pages'][1]['kind'] == 'diagnostic'


def test_binary_output_is_reported_without_reader(context):
    from searchos.tools.simple_browser.execution_pages import register_execution_pages
    binding = se.load_package('sample-skill')
    saved = context[0] / 'skill_executions/binary-run'
    (saved / 'artifacts').mkdir(parents=True)
    raw = b'\x00\xff'
    (saved / 'artifacts/result.bin').write_bytes(raw)
    result = {'execution_id': 'binary-run', 'status': 'completed', 'artifacts': [{'path': 'result.bin', 'sha256': hashlib.sha256(raw).hexdigest()}]}
    pages = register_execution_pages(result, binding, saved, 'task-a')
    assert pages['pages_total'] == 0
    assert pages['unrendered'][0]['path'] == 'result.bin'


def test_page_save_failure_does_not_change_execution_status(context, monkeypatch):
    install_runner(monkeypatch)
    monkeypatch.setattr('searchos.tools.simple_browser.execution_pages._persist_page', lambda *args: '')
    se.load_package('sample-skill')
    result = json.loads(asyncio.run(execute())[0])
    assert result['status'] == 'completed'
    assert 'persist' in result['page_error']


@pytest.mark.asyncio
@pytest.mark.parametrize('fixture', [False, True])
async def test_execution_pages_follow_existing_extraction_pipeline(context, monkeypatch, fixture):
    from langchain_core.messages import ToolMessage
    from searchos.harness.middleware.extraction.web_middleware import WebEvidenceMiddleware
    install_runner(monkeypatch, {'fixture': fixture, 'records': [{'text': 'Supported source content. ' * 20}]})
    se.load_package('sample-skill')
    content, artifact = await execute()
    result = json.loads(content)
    middleware = WebEvidenceMiddleware(SimpleNamespace(workspace=None))
    observations = []

    async def submit(observation, response):
        observations.append(observation)
        return response

    middleware._submit = submit

    async def executed(_):
        return ToolMessage(content=content, artifact=artifact, tool_call_id='exec')

    await middleware.awrap_tool_call(SimpleNamespace(tool_call={'name': 'exec'}), executed)
    assert not observations
    state._browser_var.set(state.BrowserState())
    for name, args in [('open', {'id_or_url': result['page_url']}), ('find', {'pattern': 'Supported source'})]:
        async def read(_, name=name, args=args):
            return await getattr(tools, name).ainvoke({'name': name, 'args': args, 'id': name, 'type': 'tool_call'})
        await middleware.awrap_tool_call(SimpleNamespace(tool_call={'name': name}), read)
    assert len(observations) == (0 if fixture else 2)
