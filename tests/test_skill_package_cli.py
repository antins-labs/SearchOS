"""Local package management must work before model configuration."""
import json
import sys
from pathlib import Path

import pytest
from searchos import cli


def package(tmp_path: Path) -> Path:
    path = tmp_path / 'source' / 'portable-demo'
    path.mkdir(parents=True)
    (path / 'SKILL.md').write_text('---\nname: portable-demo\ndescription: Example package\n---\nRead the input.\n')
    return path


def invoke(monkeypatch, args):
    monkeypatch.setattr(sys, 'argv', ['searchos', 'skills', *map(str, args)])
    # If the early dispatch regresses, this fails before any setup side effect.
    monkeypatch.setattr(cli, '_load_env', lambda: pytest.fail('package command loaded model environment'))
    with pytest.raises(SystemExit) as exc:
        cli.main()
    return exc.value.code


def test_validate_install_export_without_model_setup(tmp_path, monkeypatch, capsys):
    source = package(tmp_path)
    assert invoke(monkeypatch, ['validate', source]) == 0
    validated = json.loads(capsys.readouterr().out)
    assert validated['package_format'] == 'portable'
    library = tmp_path / 'library'
    assert invoke(monkeypatch, ['install', source, '--library', library]) == 0
    installed = json.loads(capsys.readouterr().out)
    assert Path(installed['path']).is_dir()
    exported = tmp_path / 'export' / source.name
    assert invoke(monkeypatch, ['export', installed['path'], '--output', exported]) == 0
    assert json.loads(capsys.readouterr().out)['package_hash'] == validated['package_hash']
    assert (exported / 'SKILL.md').read_bytes() == (source / 'SKILL.md').read_bytes()


def test_install_refuses_overwrite_and_reports_error(tmp_path, monkeypatch, capsys):
    source = package(tmp_path)
    args = ['install', source, '--library', tmp_path / 'library']
    assert invoke(monkeypatch, args) == 0
    capsys.readouterr()
    assert invoke(monkeypatch, args) == 1
    assert '技能包操作失败' in capsys.readouterr().err


def test_invalid_package_returns_failure(tmp_path, monkeypatch, capsys):
    source = package(tmp_path)
    (source / 'SKILL.md').write_text('# Missing metadata')
    assert invoke(monkeypatch, ['validate', source]) == 1
    assert 'frontmatter' in capsys.readouterr().err
