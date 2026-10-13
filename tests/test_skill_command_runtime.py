"""命令执行契约和真实隔离探针；不以裸跑替代隔离测试。"""
import asyncio
import json
from pathlib import Path
import sys

import pytest

from searchos.skills.runtime import command_runtime as runtime


@pytest.fixture
def dirs(tmp_path):
    skill, work, records = (tmp_path / n for n in ('skill', 'work', 'records'))
    skill.mkdir()
    (skill / 'run.py').write_text("print('ok')")
    return skill, work, records


def run(dirs, argv=None, **kwargs):
    skill, work, records = dirs
    return asyncio.run(runtime.run_command(skill, argv or ['python', 'run.py'],
        work_dir=work, execution_dir=records, network=False, **kwargs))


@pytest.mark.parametrize('argv', [['python', '-c', 'print(1)'], ['bash', '-c', 'true'],
    ['node', '-e', '1'], ['/bin/sh', 'run.py'], ['python', '../escape.py']])
def test_rejects_non_package_entry(dirs, argv):
    result = run(dirs, argv)
    assert result['status'] == 'blocked'
    assert not result['started']


def test_symlink_entry_cannot_escape(dirs, tmp_path):
    outside = tmp_path / 'secret.py'
    outside.write_text('print(1)')
    (dirs[0] / 'link.py').symlink_to(outside)
    assert run(dirs, ['python', 'link.py'])['status'] == 'blocked'


def test_backend_absence_is_closed(dirs, monkeypatch):
    monkeypatch.setattr(runtime.shutil, 'which', lambda _: None)
    result = run(dirs)
    assert result['status'] == 'blocked'
    assert not result['started']
    assert not dirs[1].exists()


def test_environment_does_not_inherit_secrets(dirs, monkeypatch):
    monkeypatch.setenv('AWS_SECRET_ACCESS_KEY', 'secret')
    monkeypatch.setenv('PYTHONPATH', '/malicious')
    env = runtime._environment(dirs[1])
    assert 'AWS_SECRET_ACCESS_KEY' not in env
    assert 'PYTHONPATH' not in env
    assert env['HOME'] == str(dirs[1])


def test_network_environment_matches_probe_proxy_without_credentials(dirs, monkeypatch):
    monkeypatch.setenv('HTTPS_PROXY', 'http://user:secret@127.0.0.1:8080/token?key=private')
    monkeypatch.setenv('http_proxy', 'http://127.0.0.1:8080')
    monkeypatch.setenv('NO_PROXY', 'localhost,127.0.0.1')
    monkeypatch.setenv('OPENAI_API_KEY', 'never-inherit')
    offline = runtime._environment(dirs[1], network=False)
    assert 'HTTPS_PROXY' not in offline and 'http_proxy' not in offline
    online = runtime._environment(dirs[1], network=True)
    assert online['HTTPS_PROXY'] == 'http://127.0.0.1:8080'
    assert online['http_proxy'] == 'http://127.0.0.1:8080'
    assert online['NO_PROXY'] == 'localhost,127.0.0.1'
    assert 'OPENAI_API_KEY' not in online


def test_snapshot_skips_links_and_preserves_bytes(dirs, tmp_path):
    work = dirs[1]
    work.mkdir()
    (work / 'output.txt').write_text('first')
    (work / 'link').symlink_to(tmp_path)
    artifacts = runtime._snapshot(work, dirs[2])
    assert [a['path'] for a in artifacts] == ['output.txt']
    (work / 'output.txt').write_text('second')
    assert (dirs[2] / 'output.txt').read_text() == 'first'


def test_work_quota(dirs, monkeypatch):
    dirs[1].mkdir()
    (dirs[1] / 'big').write_bytes(b'12345')
    monkeypatch.setattr(runtime, 'WORK_LIMIT', 4)
    assert run(dirs)['status'] == 'blocked'


def isolated_run(dirs, **kwargs):
    result = run(dirs, **kwargs)
    if result['status'] == 'blocked':
        pytest.skip('OS isolation unavailable: ' + result.get('error', result['stderr']))
    return result


def test_real_execution_and_snapshot(dirs):
    (dirs[0] / 'run.py').write_text("from pathlib import Path\nPath('result.txt').write_text('saved')\nprint('ok')")
    result = isolated_run(dirs)
    assert result['status'] == 'completed', result
    assert result['started']
    assert result['stdout'].strip() == 'ok'
    assert result['artifacts'][0]['path'] == 'result.txt'
    record = dirs[2] / result['execution_id']
    assert (record / 'artifacts/result.txt').read_text() == 'saved'
    assert json.loads((record / 'record.json').read_text()) == result


def test_real_timeout(dirs):
    # First prove the backend works so a timeout is not confused with startup.
    isolated_run(dirs)
    (dirs[0] / 'run.py').write_text('import time\ntime.sleep(30)')
    result = run(dirs, timeout_s=.4)
    assert result['status'] == 'timed_out'
    assert result['started']


def test_real_secrets_and_package_write_denied(dirs, tmp_path):
    secret = tmp_path / 'secret'
    secret.write_text('private')
    (dirs[0] / 'run.py').write_text(f'''from pathlib import Path
for p in ({str(secret)!r}, {str(dirs[0] / 'run.py')!r}):
    try:
        Path(p).write_text('bad')
        raise RuntimeError('escaped')
    except PermissionError:
        pass
try:
    Path({str(secret)!r}).read_text()
    raise RuntimeError('read secret')
except (PermissionError, FileNotFoundError):
    pass
print('isolated')
''')
    result = isolated_run(dirs)
    assert result['status'] == 'completed', result
    assert secret.read_text() == 'private'


@pytest.mark.parametrize(('interpreter', 'filename', 'source'), [
    ('bash', 'run.sh', "printf 'shell' > answer.txt"),
    ('node', 'run.mjs', "import fs from 'node:fs'; fs.writeFileSync('answer.txt', 'node');"),
])
def test_real_other_languages(dirs, interpreter, filename, source):
    if runtime.shutil.which(interpreter) is None:
        pytest.skip(f'{interpreter} unavailable')
    (dirs[0] / filename).write_text(source)
    result = isolated_run(dirs, argv=[interpreter, filename])
    assert result['status'] == 'completed', result
    assert any(a['id'] == 'answer.txt' for a in result['artifacts'])


def test_real_output_limit(dirs):
    (dirs[0] / 'run.py').write_text("print('x' * 2000000)")
    result = isolated_run(dirs)
    assert result['status'] == 'completed', result
    assert len(result['stdout']) == runtime.OUTPUT_LIMIT
    assert result['truncated']
    assert (dirs[2] / result['execution_id'] / 'stdout.log').stat().st_size == runtime.LOG_LIMIT


def test_real_cancellation_preserves_record(dirs):
    isolated_run(dirs)
    (dirs[0] / 'run.py').write_text("import time\nprint('started', flush=True)\ntime.sleep(30)")

    async def cancel():
        task = asyncio.create_task(runtime.run_command(dirs[0], ['python', 'run.py'],
            work_dir=dirs[1], execution_dir=dirs[2], network=False))
        await asyncio.sleep(.3)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(cancel())
    records = [json.loads(p.read_text()) for p in dirs[2].glob('*/record.json')]
    assert any(r['status'] == 'cancelled' and r['started'] for r in records)


def test_rejects_overlapping_roots(dirs):
    result = asyncio.run(runtime.run_command(dirs[0], ['python', 'run.py'],
        work_dir=dirs[0] / 'work', execution_dir=dirs[2]))
    assert result['status'] == 'blocked'


def test_backend_configuration_is_explicit(dirs, monkeypatch):
    monkeypatch.setattr(runtime.sys, 'platform', 'linux')
    monkeypatch.setattr(runtime.shutil, 'which', lambda _: '/usr/bin/bwrap')
    command, backend = runtime._backend(['/usr/bin/python3', str(dirs[0] / 'run.py')], dirs[0], dirs[1], False)
    assert backend == 'bubblewrap'
    assert '--unshare-all' in command
    assert '--share-net' not in command
    assert '--ro-bind' in command
    assert str(Path.home()) not in command


def test_real_multistep_workspace_and_immutable_snapshot(dirs):
    (dirs[0] / 'run.py').write_text("from pathlib import Path\nPath('input.txt').write_text('first')")
    first = isolated_run(dirs)
    assert first['status'] == 'completed', first
    (dirs[0] / 'run.py').write_text("from pathlib import Path\np=Path('input.txt')\nPath('output.txt').write_text(p.read_text().upper())\np.write_text('changed')")
    second = run(dirs)
    assert second['status'] == 'completed', second
    assert (dirs[1] / 'output.txt').read_text() == 'FIRST'
    assert (dirs[2] / first['execution_id'] / 'artifacts/input.txt').read_text() == 'first'
    assert (dirs[2] / second['execution_id'] / 'artifacts/input.txt').read_text() == 'changed'


def test_virtualenv_backend_includes_base_runtime(dirs, tmp_path, monkeypatch):
    base = tmp_path / 'base-python'
    venv = tmp_path / 'venv'
    base.mkdir()
    venv.mkdir()
    monkeypatch.setattr(runtime.sys, 'prefix', str(venv))
    monkeypatch.setattr(runtime.sys, 'exec_prefix', str(venv))
    monkeypatch.setattr(runtime.sys, 'base_prefix', str(base))
    monkeypatch.setattr(runtime.sys, 'base_exec_prefix', str(base))
    monkeypatch.setattr(runtime.sys, 'platform', 'linux')
    monkeypatch.setattr(runtime.shutil, 'which', lambda _: '/usr/bin/bwrap')
    argv, _ = runtime._backend(['/usr/bin/python3'], dirs[0], dirs[1], False)
    assert str(base) in argv
    assert str(venv) in argv


def test_migrated_package_runs_through_os_isolation(tmp_path):
    from searchos.skills.packaging import export_package
    library = Path(__file__).resolve().parents[1] / 'searchos/skills/library/access/data-worldbank-org'
    package = export_package(library, tmp_path / 'data-worldbank-org')
    dirs = (package, tmp_path / 'work', tmp_path / 'records')
    result = isolated_run(dirs, argv=['python', 'scripts/run.py', '--function',
                          '__invalid_function__', '--result-file', 'result.json'])
    # The actual source dispatcher rejects the function; no network is needed.
    assert result['started'] and result['exit_code'] == 1, result
    artifact = dirs[2] / result['execution_id'] / 'artifacts/result.json'
    data = json.loads(artifact.read_text())
    assert data.get('error')
    assert 'unknown' in str(data['error']).lower() or 'invalid' in str(data['error']).lower()


def test_browser_binaries_are_mounted_as_runtime_not_user_profile(tmp_path, monkeypatch):
    fake_home = tmp_path / 'home'
    cache = fake_home / 'Library/Caches/ms-playwright'
    cache.mkdir(parents=True)
    monkeypatch.setattr(runtime.sys, 'platform', 'darwin')
    monkeypatch.setattr(runtime.Path, 'home', lambda: fake_home)
    monkeypatch.setattr(runtime.shutil, 'which', lambda _: '/usr/bin/sandbox-exec')
    work = tmp_path / 'work'
    env = runtime._environment(work)
    assert env['HOME'] == str(work)
    assert env['PLAYWRIGHT_BROWSERS_PATH'] == str(cache)
    command, _ = runtime._backend(['python', 'script.py'], tmp_path / 'skill', work, False)
    assert str(cache) in command[2]
    assert f'(subpath "{fake_home}")' not in command[2]


def test_browser_cache_symlink_cannot_expand_read_permissions(tmp_path, monkeypatch):
    fake_home = tmp_path / 'home'
    cache = fake_home / 'Library/Caches/ms-playwright'
    cache.parent.mkdir(parents=True)
    cache.symlink_to(tmp_path)
    monkeypatch.setattr(runtime.sys, 'platform', 'darwin')
    monkeypatch.setattr(runtime.Path, 'home', lambda: fake_home)
    assert runtime._browser_cache() is None
