"""Service supervision contracts; no launchctl changes or real SearchOS jobs."""
import importlib.util
import json
import os
from pathlib import Path
import plistlib
import socket
import subprocess
import sys
import time

import pytest

SOURCE = Path(__file__).resolve().parents[1] / 'web/service.py'
spec = importlib.util.spec_from_file_location('local_service', SOURCE)
service = importlib.util.module_from_spec(spec)
spec.loader.exec_module(service)


def config(tmp_path):
    return {'repo': str(tmp_path / 'repo with spaces'), 'python': sys.executable,
            'node': '/opt/homebrew/bin/node', 'path': '/usr/bin:/bin',
            'api_port': 18000, 'web_port': 13100, 'keep_awake': True,
            'logs': str(tmp_path / 'logs'), 'environment': {'SF_PUSH_CONTACT': 'mailto:test@example.test'}}


def test_plist_and_commands_preserve_paths_and_loopback(tmp_path):
    cfg = config(tmp_path)
    plist = plistlib.loads(plistlib.dumps(service.launch_plist(cfg, tmp_path / 'config.json')))
    assert plist['KeepAlive'] and plist['RunAtLoad']
    assert plist['ThrottleInterval'] >= 10
    assert plist['ProgramArguments'][1] == str(tmp_path / 'repo with spaces/web/service.py')
    commands = service.commands(cfg)
    assert commands['api'][0][commands['api'][0].index('--host') + 1] == '127.0.0.1'
    assert commands['web'][0][commands['web'][0].index('--hostname') + 1] == '127.0.0.1'
    assert commands['awake'][0] == ['/usr/bin/caffeinate', '-s']
    cfg['keep_awake'] = False
    assert 'awake' not in service.commands(cfg)


def test_environment_and_config_privacy(tmp_path, monkeypatch):
    cfg = config(tmp_path)
    monkeypatch.setenv('NEXT_PUBLIC_API_URL', 'http://wrong.test')
    env = service.service_env(cfg)
    assert env['SF_NEXT_DIST_DIR'] == '.next-service'
    assert env['SF_API_PROXY'] == 'http://127.0.0.1:18000'
    assert env['SF_SERVICE_KEEP_AWAKE'] == 'ac'
    assert 'NEXT_PUBLIC_API_URL' not in env
    path = tmp_path / 'config.json'
    service.save_json(path, cfg)
    assert path.stat().st_mode & 0o777 == 0o600
    assert service.read_config(path) == cfg
    cfg['web_port'] = cfg['api_port']
    service.save_json(path, cfg)
    with pytest.raises(ValueError):
        service.read_config(path)


def test_occupied_port_is_not_taken_over(tmp_path):
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        listener.listen()
        cfg = config(tmp_path)
        cfg['api_port'] = listener.getsockname()[1]
        with pytest.raises(RuntimeError, match='已被占用'):
            service.check_ports(cfg)
        assert listener.fileno() != -1


def test_supervisor_restarts_crashed_child_and_stops_cleanly(tmp_path):
    counter = tmp_path / 'starts'
    child = tmp_path / 'child.py'
    child.write_text('''import os, time
from pathlib import Path
p = Path(__file__).with_name('starts')
previous = p.read_text() if p.exists() else ''
p.write_text(previous + str(os.getpid()) + '\\n')
if not previous: raise SystemExit(7)
time.sleep(60)
''')
    cfg = config(tmp_path)
    harness = '''import importlib.util, json, sys
from pathlib import Path
spec = importlib.util.spec_from_file_location('svc', sys.argv[1])
svc = importlib.util.module_from_spec(spec); spec.loader.exec_module(svc)
cfg = json.loads(sys.argv[2])
svc.commands = lambda _: {'fake': ([sys.executable, sys.argv[3]], Path(sys.argv[3]).parent)}
svc.run(cfg)
'''
    proc = subprocess.Popen([sys.executable, '-c', harness, str(SOURCE), json.dumps(cfg), str(child)])
    try:
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            if counter.exists() and len(counter.read_text().splitlines()) >= 2:
                break
            assert proc.poll() is None
            time.sleep(0.1)
        starts = counter.read_text().splitlines()
        assert len(starts) == 2
        assert starts[0] != starts[1]
        proc.terminate()
        assert proc.wait(timeout=8) == 0
        with pytest.raises(ProcessLookupError):
            os.kill(int(starts[-1]), 0)
        assert service.restart_delay(1000) == 60
    finally:
        if proc.poll() is None:
            proc.terminate()
            proc.wait(timeout=15)
