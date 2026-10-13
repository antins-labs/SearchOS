"""长时间创建任务不能被生成脚本触发的开发热重载取消。"""
import os
from pathlib import Path
import subprocess


def test_api_launcher_does_not_reload_generated_python(tmp_path):
    root = Path(__file__).resolve().parents[1]
    python = tmp_path / 'python'
    python.write_text('#!/bin/sh\nif [ "$1" = "-c" ]; then exit 0; fi\nprintf "%s\\n" "$@"\n')
    python.chmod(0o755)
    result = subprocess.run(['bash', str(root/'web/start.sh'), 'api'], env={**os.environ, 'SEARCHOS_PYTHON': str(python)}, capture_output=True, text=True, check=True)
    args = result.stdout.splitlines()
    assert 'uvicorn' in args and 'api.main:app' in args
    assert '--reload' not in args and '--reload-dir' not in args


def test_old_recursive_watcher_reproduces_script_edit_restart(tmp_path):
    from uvicorn import Config
    from uvicorn.supervisors.statreload import StatReload
    script = tmp_path/'searchos/skills/library/access/.pipeline_test/.staging_test/scripts/history.py'
    script.parent.mkdir(parents=True)
    script.write_text('print(1)')
    config = Config('api.main:app', reload=True, reload_dirs=[str(tmp_path/'searchos')], reload_delay=0)
    watcher = StatReload(config, target=lambda _: None, sockets=[])
    assert watcher.should_restart() is None
    before = script.stat().st_mtime
    script.write_text('print(2)')
    os.utime(script, (before + 1, before + 1))
    assert watcher.should_restart() == [script.resolve()]
