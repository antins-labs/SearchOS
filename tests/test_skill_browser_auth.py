"""认证边界：本机存储、短期检索能力、未经授权不能读取会话。"""
import json
import os
from pathlib import Path

import httpx
import pytest

from searchos.skills.runtime import browser_auth as auth
from searchos.skills.runtime.browser_broker import serve_search


@pytest.fixture
def auth_root(tmp_path, monkeypatch):
    from searchos.config.settings import settings
    root = tmp_path/'private/auth'
    monkeypatch.setattr(settings, 'browser_auth_dir', str(root))
    return root


def test_state_stays_local_and_discards_other_sites_and_storage(auth_root):
    auth.save_state({'cookies': [
        {'name': 'auth_token', 'value': 'private-cookie', 'domain': '.x.com'},
        {'name': 'other', 'value': 'private-other', 'domain': 'other.test'},
    ], 'origins': [{'origin':'https://x.com','localStorage':[{'name':'private','value':'private'}]}]})
    assert os.stat(auth_root).st_mode & 0o777 == 0o700
    assert os.stat(auth.state_path()).st_mode & 0o777 == 0o600
    state = auth.read_state()
    assert len(state['cookies']) == 1 and state['origins'] == []
    auth.revoke()
    assert auth.read_state() is None


def test_state_rejects_symlink(auth_root, tmp_path):
    directory = auth.profile_dir()
    other = tmp_path/'other'; other.write_text('do not overwrite')
    (directory/'state.json').symlink_to(other)
    with pytest.raises(ValueError, match='symlink'):
        auth.save_state({'cookies': []})
    assert other.read_text() == 'do not overwrite'


def test_missing_session_requests_login_once_per_attempt(auth_root, monkeypatch):
    opened = []
    monkeypatch.setattr(auth, 'start_login', lambda profile='x': opened.append(profile))
    with pytest.raises(auth.AuthRequired, match='auth_required'):
        auth.require_state()
    assert opened == ['x']


@pytest.mark.asyncio
async def test_broker_only_allows_authenticated_search_and_dies_with_command():
    calls = []
    class Adapter:
        async def search(self, query, limit, mode):
            calls.append((query,limit,mode))
            return {'records':[{'id':'20','url':'https://x.com/jack/status/20','text':'hello'}]}
    async with httpx.AsyncClient(trust_env=False) as client:
        async with serve_search(Adapter()) as env:
            url = env['SEARCHOS_BROWSER_URL']
            assert url.startswith('http://127.0.0.1:')
            headers = {'Authorization':'Bearer '+env['SEARCHOS_BROWSER_TOKEN']}
            assert (await client.post(url,json={'query':'NASA'})).status_code == 403
            assert (await client.post(url,headers={**headers,'Origin':'https://evil.test'},json={'query':'NASA'})).status_code == 403
            for data in [{'query':'NASA','url':'https://evil.test'}, {'query':'NASA','javascript':'document.cookie'},
                         {'query':'NASA','limit':31}, {'query':''}, {'query':'NASA','limit':True}]:
                assert (await client.post(url,headers=headers,json=data)).status_code == 400
            response = await client.post(url,headers=headers,json={'query':'NASA','limit':2,'mode':'latest'})
            assert response.status_code == 200
            assert response.json()['records'][0]['id'] == '20'
            assert calls == [('NASA',2,'latest')]
            assert (await client.get(url.replace('/search','/cookies'),headers=headers)).status_code == 404
        with pytest.raises(httpx.ConnectError):
            await client.post(url,headers=headers,json={'query':'NASA'})


@pytest.mark.asyncio
async def test_expired_session_is_blocked_without_leaking_exception(auth_root, monkeypatch):
    class Adapter:
        async def search(self,*args): raise auth.AuthRequired('secret-cookie-value')
    opened=[]
    monkeypatch.setattr('searchos.skills.runtime.browser_broker.start_login',lambda:opened.append(True))
    async with serve_search(Adapter()) as env, httpx.AsyncClient(trust_env=False) as client:
        response=await client.post(env['SEARCHOS_BROWSER_URL'],headers={'Authorization':'Bearer '+env['SEARCHOS_BROWSER_TOKEN']},json={'query':'NASA'})
        assert response.status_code==401 and response.json()['error']=='auth_required'
        assert 'secret-cookie-value' not in response.text
        assert opened==[True]


@pytest.mark.asyncio
async def test_runtime_blocks_before_script_when_auth_required(tmp_path, auth_root, monkeypatch):
    from searchos.skills.runtime.command_runtime import run_command
    package=tmp_path/'x-com';(package/'scripts').mkdir(parents=True)
    (package/'SKILL.md').write_text('---\nname: x-com\ndescription: 搜索\nmetadata:\n  host: x.com\n  searchos-category: access\n  searchos-browser-profile: x\n  searchos-browser-entries: scripts/search.py\n---\n搜索')
    (package/'scripts/search.py').write_text('raise RuntimeError("must not start")')
    opened=[]
    monkeypatch.setattr(auth,'start_login',lambda profile='x':opened.append(profile))
    result=await run_command(package,['python','scripts/search.py'],work_dir=tmp_path/'work',execution_dir=tmp_path/'runs')
    assert result['auth_required'] and not result['started']
    assert not (tmp_path/'work').exists()
    assert opened==['x']
    assert auth.command_profile(package,['python','scripts/search.py','--help']) is None


@pytest.mark.asyncio
async def test_sandbox_can_search_but_cannot_read_vault(tmp_path, auth_root, monkeypatch):
    from contextlib import asynccontextmanager
    from searchos.skills.runtime.command_runtime import run_command
    auth.save_state({'cookies':[{'name':'auth_token','value':'private-cookie','domain':'.x.com'}]})
    class Adapter:
        async def search(self,*args):
            return {'records':[{'id':'20','url':'https://x.com/jack/status/20','text':'public'}]}
    @asynccontextmanager
    async def bridge(profile):
        async with serve_search(Adapter()) as env:
            yield env
    monkeypatch.setattr('searchos.skills.runtime.browser_broker.browser_bridge',bridge)
    package=tmp_path/'x-com';(package/'scripts').mkdir(parents=True)
    (package/'SKILL.md').write_text('---\nname: x-com\ndescription: 搜索\nmetadata:\n  host: x.com\n  searchos-category: access\n  searchos-browser-profile: x\n  searchos-browser-entries: scripts/search.py\n---\n搜索')
    (package/'scripts/search.py').write_text('''import json,os,sys,urllib.request
request=urllib.request.Request(os.environ['SEARCHOS_BROWSER_URL'],data=b'{"query":"NASA"}',headers={'Content-Type':'application/json','Authorization':'Bearer '+os.environ['SEARCHOS_BROWSER_TOKEN']})
with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request,timeout=5) as response:
    result=json.load(response)
try:
    open(sys.argv[1]).read()
    result['vault_readable']=True
except PermissionError:
    result['vault_readable']=False
print(json.dumps(result))
''')
    result=await run_command(package,['python','scripts/search.py',str(auth.state_path())],work_dir=tmp_path/'work',execution_dir=tmp_path/'runs')
    assert result['exit_code']==0,result
    assert json.loads(result['stdout'])['vault_readable'] is False
    assert 'private-cookie' not in json.dumps(result)


def test_login_navigation_timeout_keeps_window_for_manual_retry(auth_root, monkeypatch):
    from playwright.sync_api import TimeoutError as NavigationTimeout
    from searchos.skills.runtime.browser_login import wait_for_login
    stages = []
    class Page:
        def goto(self, *args, **kwargs): raise NavigationTimeout('private detail')
        def bring_to_front(self): stages.append('front')
        def is_closed(self): return False
        def wait_for_timeout(self, ms): stages.append('wait')
    class Context:
        count = 0
        def cookies(self, url):
            self.count += 1
            return [] if self.count == 1 else [{'name':'auth_token','value':'private-cookie'}]
        def storage_state(self):
            return {'cookies':[{'name':'auth_token','value':'private-cookie','domain':'.x.com'}]}
    monkeypatch.setattr('searchos.skills.runtime.browser_login.write_login_status', lambda stage, **kw: stages.append(stage))
    wait_for_login(Context(), Page(), auth.profile_dir())
    assert stages == ['front','navigation_failed','wait','authenticated']
    assert auth.read_state() is not None
