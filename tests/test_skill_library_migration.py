"""批量迁移：资产独立性、调用语义与旧配置兼容。"""
import concurrent.futures
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

from searchos.skills.catalog.registry import SkillRegistry
from searchos.skills.core.schema import parse_skill_file
from searchos.skills.migrate_library import migrate, TEMPLATE
from searchos.skills.names import canonical_skill_name
from searchos.skills.packaging import export_package, validate_package

LIBRARY = Path(__file__).resolve().parents[1] / 'searchos/skills/library'


def run(script, *args, cwd):
    return subprocess.run([sys.executable, '-I', str(script), *args], cwd=cwd,
                          capture_output=True, text=True, timeout=15)


def test_all_active_packages_are_standard_and_all_cli_help_runs(tmp_path):
    entries = [p for p in LIBRARY.rglob('*') if p.name == 'SKILL.md'
               and not any(part.startswith(('_', '.')) for part in p.relative_to(LIBRARY).parts)]
    assert len(entries) >= 498
    scripts = []
    for entry in entries:
        skill = validate_package(entry.parent)
        assert skill.package_format == 'portable'
        assert not (entry.parent / 'executor.py').exists()
        if (entry.parent / 'scripts/run.py').exists():
            script = entry.parent / 'scripts/run.py'
            assert script.read_bytes() == TEMPLATE.read_bytes()
            source = (entry.parent / 'scripts/source.py').read_text()
            assert 'from searchos' not in source and 'import searchos' not in source
            scripts.append(script)
    assert len(scripts) >= 465
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = list(pool.map(lambda script: (script, run(script, '--help', cwd=tmp_path)), scripts))
    assert [(str(p), r.stderr) for p, r in outcomes if r.returncode] == []


def test_names_preserve_runtime_filters_and_metadata():
    registry = SkillRegistry(only=['data_worldbank_org'])
    assert registry.load_directory(LIBRARY) == 1
    skill = registry.get('data_worldbank_org')
    assert skill is registry.get('data-worldbank-org')
    assert skill.meta.category.value == 'access'
    assert 'data-worldbank-org' in registry.generate_catalog(access_allow={'data_worldbank_org'})
    registry.add_excluded('data_worldbank_org')
    assert registry.get('data-worldbank-org') is None
    assert registry.load_directory(LIBRARY) == 0
    assert canonical_skill_name('unmigrated_custom') == 'unmigrated_custom'
    from searchos.config.web_overlay import SkillsOverlay
    overlay = SkillsOverlay(access_only=['data_worldbank_org'], strategy_deny=['multi_source_verification'])
    assert overlay.access_only == ['data-worldbank-org']
    assert overlay.strategy_deny == ['multi-source-verification']


def test_exported_real_source_runs_outside_repository(tmp_path):
    exported = export_package(LIBRARY / 'access/data-worldbank-org', tmp_path / 'data-worldbank-org')
    result = run(exported / 'scripts/run.py', '--function', '__invalid_function__',
                 '--result-file', str(tmp_path / 'result.json'), cwd=tmp_path)
    assert result.returncode == 1
    data = json.loads((tmp_path / 'result.json').read_text())
    assert 'error' in data
    assert 'unknown' in str(data['error']).lower() or 'invalid' in str(data['error']).lower()


def old_package(root, name='example_source', code=None):
    folder = root / 'access' / name
    folder.mkdir(parents=True)
    (folder / 'skill.md').write_text('Source-specific notes.')
    (folder / 'manifest.yaml').write_text('description: Example source\nparams_schema:\n  query:\n    type: string\n    required: true\n  limit:\n    type: integer\n    required: false\n    default: 99\n')
    (folder / 'executor.py').write_text(code or '''async def execute(params, ctx):
    print("source diagnostic")
    return {"received": params, "context_is_none": ctx is None}
''')
    return folder


def test_migration_preserves_omitted_defaults_and_cli_io(tmp_path):
    library = tmp_path / 'library'
    old_package(library)
    aliases = tmp_path / 'aliases.json'
    report = migrate(library, aliases)
    assert len(report) == 1
    package = library / 'access/example-source'
    assert json.loads(aliases.read_text()) == {'example_source': 'example-source'}
    assert migrate(library, aliases) == []
    exported = export_package(package, tmp_path / 'export/example-source')
    params = tmp_path / 'input.json'
    params.write_text('{"query":"original"}')
    output = tmp_path / 'out.json'
    result = run(exported / 'scripts/run.py', '--params-file', str(params), '--query', 'override',
                 '--result-file', str(output), cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    assert not result.stdout
    assert 'diagnostic' in result.stderr
    data = json.loads(output.read_text())
    assert data == {'received': {'query': 'override'}, 'context_is_none': True}
    invalid = run(exported / 'scripts/run.py', '--params', '{"query":"x","limit":true}', cwd=tmp_path)
    assert invalid.returncode == 1 and 'expected integer' in invalid.stderr
    assert not invalid.stdout


def test_migration_validates_entire_batch_before_replacing_sources(tmp_path):
    library = tmp_path / 'library'
    first = old_package(library)
    broken = old_package(library, 'broken_source', code='invalid syntax !!!')
    with pytest.raises(SyntaxError):
        migrate(library, tmp_path / 'aliases.json')
    assert (first / 'executor.py').is_file() and (broken / 'executor.py').is_file()
    assert not (library / 'access/example-source').exists()


def test_nullable_parameter_and_percent_help_work(tmp_path):
    exported = export_package(LIBRARY / 'access/www-gov-uk', tmp_path / 'www-gov-uk')
    result = run(exported / 'scripts/run.py', '--help', cwd=tmp_path)
    assert result.returncode == 0
    spec = importlib.util.spec_from_file_location('portable_cli', exported / 'scripts/run.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.validate({'value': None}, {'value': {'type': ['string', 'null']}})
    with pytest.raises(ValueError):
        module.validate({'value': []}, {'value': {'type': ['string', 'null']}})


def test_failed_publish_rolls_back_already_migrated_packages(tmp_path, monkeypatch):
    library = tmp_path / 'library'
    first = old_package(library, 'a_source')
    second = old_package(library, 'b_source')
    original_rename = Path.rename
    def failing_rename(path, target):
        if Path(target) == library / 'access/b-source':
            raise OSError('simulated publish failure')
        return original_rename(path, target)
    monkeypatch.setattr(Path, 'rename', failing_rename)
    with pytest.raises(OSError, match='publish failure'):
        migrate(library, tmp_path / 'aliases.json')
    assert (first / 'executor.py').is_file() and (second / 'executor.py').is_file()
    assert not (library / 'access/a-source').exists()
    assert not (tmp_path / 'aliases.json').exists()


def test_alias_migration_preserves_existing_task_snapshot(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from searchos.tools import skill_execution as execution
    from searchos.tools.search_state import _workspace_var, _current_task_id_var
    old = old_package(tmp_path / 'old', 'data_worldbank_org')
    versions = [parse_skill_file(old)]
    monkeypatch.setattr(execution, '_skill', lambda _: versions[-1])
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    token = _workspace_var.set(SimpleNamespace(path=workspace))
    task = _current_task_id_var.set('existing-task')
    try:
        original = execution.load_package('data_worldbank_org')
        # Simulate the pre-migration filename used by an existing task.
        import hashlib
        root, key = execution._context()
        path = execution._binding_path(root, key, 'data_worldbank_org')
        old_path = path.with_name(hashlib.sha256(b'data_worldbank_org').hexdigest() + '.json')
        if path != old_path:
            path.rename(old_path)
        versions.append(parse_skill_file(LIBRARY / 'access/data-worldbank-org'))
        current = execution.load_package('data-worldbank-org')
        assert current['package_hash'] == original['package_hash']
        assert current['execution'] == 'legacy-executor'
        assert execution._loaded('data-worldbank-org')['directory'] == original['directory']
    finally:
        _workspace_var.reset(token)
        _current_task_id_var.reset(task)
