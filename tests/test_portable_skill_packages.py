from pathlib import Path
import shutil
import pytest
from searchos.skills.core.schema import parse_skill_file
from searchos.skills.catalog.registry import SkillRegistry
from searchos.skills.packaging import validate_package, package_fingerprint, install_package, export_package


def package(root, name='sample-skill', extra=''):
    folder = root / name
    folder.mkdir(parents=True)
    (folder / 'SKILL.md').write_text(f'---\nname: {name}\ndescription: Test portable skill\nmetadata:\n  searchos-category: access\n{extra}---\nUse scripts/run.py\n')
    (folder / 'scripts').mkdir()
    (folder / 'scripts/run.py').write_text('print("hello")\n')
    return folder


def test_standard_metadata_resources_and_install(tmp_path):
    src = package(tmp_path / 'source')
    skill = validate_package(src)
    assert skill.package_format == 'portable'
    assert skill.meta.category.value == 'access'
    assert not skill.meta.has_executor
    assert 'scripts/run.py' in skill.resources
    dest = install_package(src, tmp_path / 'installed')
    assert package_fingerprint(dest) == skill.package_hash
    with pytest.raises(FileExistsError):
        install_package(src, tmp_path / 'installed')
    exported = export_package(dest, tmp_path / 'export' / src.name)
    assert validate_package(exported).package_hash == skill.package_hash


def test_strict_new_and_tolerant_old(tmp_path):
    src = package(tmp_path, 'invalid_name')
    with pytest.raises(ValueError):
        validate_package(src)
    (src / 'SKILL.md').rename(src / 'skill.md')
    assert parse_skill_file(src).meta.name == 'invalid_name'


def test_cache_detects_resources_and_deletion(tmp_path):
    src = package(tmp_path)
    reg = SkillRegistry(all_disabled=False, disabled_layers=[])
    assert reg.load_directory(tmp_path) == 1
    initial = reg.get(src.name).package_hash
    (src / 'scripts/run.py').write_text('print("updated")')
    reg.load_directory(tmp_path)
    assert reg.get(src.name).package_hash != initial
    shutil.rmtree(src)
    assert reg.load_directory(tmp_path) == 0
    assert reg.size == 0


def test_filter_and_symlink(tmp_path):
    src = package(tmp_path / 'source')
    (src / '.env').write_text('SECRET=abc')
    (src / 'private.pem').write_text('secret')
    dest = install_package(src, tmp_path / 'installed')
    assert not (dest / '.env').exists()
    assert not (dest / 'private.pem').exists()
    (src / 'escape').symlink_to(tmp_path)
    with pytest.raises(ValueError, match='Symlink'):
        validate_package(src)


def test_duplicate_names_diagnosed(tmp_path):
    package(tmp_path / 'one')
    package(tmp_path / 'two')
    reg = SkillRegistry(all_disabled=False, disabled_layers=[])
    assert reg.load_directory(tmp_path) == 1
    assert 'conflict' in reg.diagnostics[-1]


@pytest.mark.asyncio
async def test_router_empty_and_cap(tmp_path):
    from types import SimpleNamespace
    from searchos.skills.catalog.router import discover_skills
    for i in range(4):
        package(tmp_path, f'skill-{i}')
    reg = SkillRegistry(all_disabled=False, disabled_layers=[])
    reg.load_directory(tmp_path)
    class Model:
        content = '{"skills": []}'
        async def ainvoke(self, messages):
            return SimpleNamespace(content=self.content)
    model = Model()
    assert await discover_skills('q', reg.list_all(), limit=2, model=model) == []
    model.content = '{"skills": [{"name":"skill-3"}, {"name":"skill-2"}, {"name":"skill-1"}]}'
    result = await discover_skills('q', reg.list_all(), limit=2, model=model)
    assert [item['name'] for item in result] == ['skill-3', 'skill-2']


def test_staging_validation_and_disabled(tmp_path):
    src = package(tmp_path, extra='availability: disabled\n')
    staging = src.rename(tmp_path / '.staging_sample-skill')
    assert validate_package(staging, expected_name='sample-skill').meta.name == 'sample-skill'
    staging.rename(src)
    reg = SkillRegistry(all_disabled=False, disabled_layers=[])
    assert reg.load_directory(tmp_path) == 0


def test_export_runs_without_searchos(tmp_path):
    import subprocess
    import sys
    src = package(tmp_path / 'source')
    dest = export_package(src, tmp_path / 'export' / src.name)
    completed = subprocess.run([sys.executable, '-I', str(dest / 'scripts/run.py')],
                               cwd=tmp_path, capture_output=True, text=True, check=True)
    assert completed.stdout.strip() == 'hello'


def test_symlink_in_filtered_tree_rejected(tmp_path):
    src = package(tmp_path)
    (src / '.cache').mkdir()
    (src / '.cache' / 'link').symlink_to(tmp_path)
    with pytest.raises(ValueError, match='Symlink'):
        validate_package(src)
