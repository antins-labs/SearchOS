"""代理选择贯穿探测、隔离 CLI、草稿样例和浏览器。"""
import json
import os

import pytest

from searchos.skills.runtime.network import proxy_environment, browser_proxy_options


def test_explicit_modes_do_not_leak_secrets_or_inherit_bypass():
    env = {'HTTPS_PROXY': 'http://user:secret@127.0.0.1:8080/private?key=hidden',
           'ALL_PROXY': 'socks5://127.0.0.1:1080', 'NO_PROXY': '*', 'API_KEY': 'private'}
    assert proxy_environment('direct', environ=env) == {
        'SEARCHOS_PROXY_MODE': 'direct', 'NO_PROXY': '*', 'no_proxy': '*'}
    inherited = proxy_environment(environ=env)
    assert inherited['HTTPS_PROXY'] == 'http://127.0.0.1:8080'
    assert inherited['ALL_PROXY'] == 'socks5://127.0.0.1:1080'
    forced = proxy_environment('proxy', environ=env)
    assert forced['NO_PROXY'] == 'localhost,127.0.0.1,::1'
    assert 'secret' not in json.dumps(forced) and 'API_KEY' not in forced
    assert env['NO_PROXY'] == '*'
    with pytest.raises(ValueError, match='proxy_unavailable'):
        proxy_environment('proxy', environ={})
    with pytest.raises(ValueError, match='proxy_mode'):
        proxy_environment('typo', environ={})
    assert browser_proxy_options('direct', environ=env) == {'args': ['--no-proxy-server']}


@pytest.mark.asyncio
async def test_direct_exec_and_probe_have_same_environment(tmp_path, monkeypatch):
    from searchos.skills.runtime.command_runtime import run_command
    from searchos.skills.runtime.legacy.executor_runtime import run_python_probe, ExecutionPolicy
    monkeypatch.setenv('HTTP_PROXY', 'http://127.0.0.1:1')
    monkeypatch.setenv('HTTPS_PROXY', 'http://127.0.0.1:1')
    package = tmp_path/'package'; package.mkdir()
    code = "import os,json,urllib.request\nprint(json.dumps({'proxies': urllib.request.getproxies(), 'bypass': urllib.request.proxy_bypass('www.zhipin.com'), 'mode': os.environ['SEARCHOS_PROXY_MODE']}))"
    (package/'probe.py').write_text(code)
    result = await run_command(package, ['python', 'probe.py'], work_dir=tmp_path/'work',
                               execution_dir=tmp_path/'runs', proxy_mode='direct')
    assert result['exit_code'] == 0, result
    data = json.loads(result['stdout'])
    assert data['bypass'] and data['mode'] == 'direct'
    assert set(data['proxies']) == {'no'}
    request = json.loads((tmp_path/'runs'/result['execution_id']/'request.json').read_text())
    assert request['proxy_mode'] == 'direct'
    probe = await run_python_probe(code, package, policy=ExecutionPolicy.access(proxy_mode='direct'))
    assert json.loads(probe['stdout']) == data
    assert os.environ['HTTPS_PROXY'] == 'http://127.0.0.1:1'


@pytest.mark.asyncio
async def test_proxy_selection_survives_draft_and_validation(tmp_path, monkeypatch):
    from searchos.skills.pipeline.access.tools import BuilderWorkspace
    from searchos.skills.pipeline.access.valid import validate_examples
    from searchos.skills.pipeline.drafts import save_draft, load_draft
    from searchos.skills.runtime import command_runtime
    builder = BuilderWorkspace(tmp_path/'example-com')
    try:
        await builder.write_file('scripts/search.py', 'print(1)')
        await builder.dispatch('register_example', {'argv':['python', 'scripts/search.py'],
                               'output':'', 'records_key':'records', 'proxy_mode':'direct'})
        pointer = save_draft(tmp_path/'draft', builder.output_dir, builder.files, name=builder.expected_name,
                             examples=builder.examples, require_host=True)
        package, saved = load_draft(pointer)
        seen = []
        async def command(*args, **kwargs):
            seen.append(kwargs)
            return {'exit_code':0, 'stdout': json.dumps({'records':[{'url':'https://example.com/1', 'title':'data'}]})}
        monkeypatch.setattr(command_runtime, 'run_command', command)
        assert (await validate_examples(package, saved['examples']))['valid']
        assert seen[-1]['proxy_mode'] == 'direct' and seen[-1]['network']
        assert not seen[0]['network']
    finally:
        builder.close()


@pytest.mark.asyncio
async def test_playwright_probe_route_applies_to_async_and_sync(monkeypatch):
    from playwright.async_api import BrowserType as Async
    from playwright.sync_api import BrowserType as Sync
    from searchos.skills.runtime.legacy.executor_proxy import _patch_playwright
    async def async_launch(self, **kwargs): return kwargs
    def sync_launch(self, **kwargs): return kwargs
    for key in ('launch', 'launch_persistent_context'):
        monkeypatch.setattr(Async, key, async_launch)
        monkeypatch.setattr(Sync, key, sync_launch)
    _patch_playwright(None, 'direct')
    for key in ('launch', 'launch_persistent_context'):
        a = await getattr(Async, key)(None, proxy={'server':'http://proxy'}, args=['--proxy-server=old'])
        b = getattr(Sync, key)(None, proxy={'server':'http://proxy'}, args=['--proxy-server=old'])
        assert a == b == {'args':['--no-proxy-server']}
