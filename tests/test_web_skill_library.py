"""技能库读取与文件边界，不执行包内脚本。"""
import os
from pathlib import Path

import pytest


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(os, 'environ', os.environ.copy())
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / 'web'))
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api.routes.skills import library_router
    from searchos.config.settings import settings
    monkeypatch.setattr(settings, 'skill_library_path', str(tmp_path))
    monkeypatch.setattr(settings, 'enable_skills', False)
    package = tmp_path / 'access/example-com'
    (package / 'scripts').mkdir(parents=True)
    (package / 'SKILL.md').write_text('---\nname: example-com\ndescription: 读取站点\nmetadata:\n  searchos-category: access\n---\n# 用法\n执行 scripts/read.py\n')
    (package / 'scripts/read.py').write_text('print("hello")')
    (package / '.env').write_text('DO_NOT_READ=secret')
    app = FastAPI(); app.include_router(library_router)
    with TestClient(app) as c:
        yield c, package


def test_catalog_and_detail_even_when_runtime_disabled(client):
    c, _ = client
    response = c.get('/api/skills/library')
    assert response.status_code == 200
    assert response.json()[0]['name'] == 'example-com'
    detail = c.get('/api/skills/library/access/example-com').json()
    assert '# 用法' in detail['body']
    assert 'scripts/read.py' in detail['files'] and '.env' not in detail['files']
    assert c.get('/api/skills/library/access/example-com/file', params={'path': 'scripts/read.py'}).json()['content'] == 'print("hello")'


@pytest.mark.parametrize('path', ['../.env', '/etc/passwd', '.env', 'scripts/../../.env'])
def test_private_or_outside_file_not_readable(client, path):
    c, _ = client
    assert c.get('/api/skills/library/access/example-com/file', params={'path': path}).status_code == 404


def test_symlinks_and_large_files(client, tmp_path):
    c, package = client
    (package / 'big.txt').write_text('x' * 262145)
    assert c.get('/api/skills/library/access/example-com/file', params={'path': 'big.txt'}).status_code == 413
    (package / 'binary.bin').write_bytes(b'\x00hi')
    assert c.get('/api/skills/library/access/example-com/file', params={'path': 'binary.bin'}).status_code == 415
    (package / 'scripts/link').symlink_to(tmp_path / 'secret')
    assert c.get('/api/skills/library/access/example-com/file', params={'path': 'scripts/link'}).status_code == 404
    assert c.get('/api/skills/library/access/example-com').status_code == 422


def test_full_text_query_category_and_pagination(client):
    c, package = client
    for i in range(5):
        directory = package.parent / f'item-{i}'
        directory.mkdir()
        (directory / 'SKILL.md').write_text(f'---\nname: item-{i}\ndescription: capability\n---\nUniqueNeedle reading {i}\n')
    first = c.get('/api/skills/library/query', params={'q': 'uniqueneedle READING', 'page_size': 2}).json()
    second = c.get('/api/skills/library/query', params={'q': 'uniqueneedle', 'page_size': 2, 'page': 2}).json()
    assert first['total'] == 5 and first['pages'] == 3
    assert [item['name'] for item in first['items']] == ['item-0', 'item-1']
    assert [item['name'] for item in second['items']] == ['item-2', 'item-3']
    assert all('body' not in item for item in first['items'])
    last = c.get('/api/skills/library/query', params={'q': 'uniqueneedle', 'page_size': 2, 'page': 999}).json()
    assert last['page'] == 3 and len(last['items']) == 1
    empty = c.get('/api/skills/library/query', params={'q': 'uniqueneedle', 'category': 'strategy'}).json()
    assert empty['total'] == 0 and empty['items'] == [] and empty['counts']['access'] == 5
    assert c.get('/api/skills/library/query', params={'q': 'absent'}).json()['total'] == 0
    for params in [{'page': 0}, {'page_size': 101}, {'category': 'bad'}]:
        assert c.get('/api/skills/library/query', params=params).status_code == 422
