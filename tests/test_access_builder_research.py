"""研究会话隔离与增量生成行为。"""
import asyncio
import json

import pytest

from searchos.skills.pipeline.access.tools import BuilderWorkspace


@pytest.fixture(autouse=True)
def block_unconfigured_research_fallback(monkeypatch, request):
    from searchos.tools.simple_browser.backend.base import FetchResult
    async def blocked(self, url, **kwargs):
        return FetchResult(url=url, status=0, error='fixture: HTTP unavailable')
    async def public_url(url):
        if not url.startswith('https://example.com/'):
            raise ValueError('fixture: non-public or disallowed URL')
    if request.node.originalname != 'test_research_http_reader_preserves_proxy_and_encoding_options':
        monkeypatch.setattr('searchos.tools.simple_browser.backend.aiohttp.AiohttpBackend.fetch', blocked)
    monkeypatch.setattr('searchos.tools.simple_browser.image_reading.validate_public_url', public_url)


@pytest.mark.asyncio
@pytest.mark.parametrize('trust_env,allow_redirects', [(False, True), (True, False)])
async def test_research_http_reader_preserves_proxy_and_encoding_options(monkeypatch, trust_env, allow_redirects):
    from searchos.tools.simple_browser.backend.aiohttp import AiohttpBackend
    calls = {}
    class Response:
        status = 200
        headers = {'Content-Type': 'text/html'}
        async def text(self, **kwargs): return '<html><body>Public data.</body></html>'
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
    class Session:
        def __init__(self, **kwargs): calls['session'] = kwargs
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        def get(self, url, **kwargs):
            calls['request'] = kwargs
            return Response()
    monkeypatch.setattr('searchos.tools.simple_browser.backend.aiohttp.aiohttp.ClientSession', Session)
    monkeypatch.setattr('searchos.tools.simple_browser.backend.aiohttp.aiohttp.TCPConnector', lambda **kwargs: None)
    backend = AiohttpBackend(max_retries=0, trust_env=trust_env, allow_redirects=allow_redirects)
    result = await backend.fetch('https://example.com/api')
    assert result.ok and 'Public data' in result.markdown
    assert calls['session']['trust_env'] is trust_env
    assert calls['request']['allow_redirects'] is allow_redirects
    assert calls['request']['headers']['Accept-Encoding'] == 'gzip, deflate'


@pytest.mark.asyncio
async def test_research_failed_reader_uses_one_http_fallback_with_inherited_proxy(monkeypatch):
    from searchos.skills.pipeline.access.browser import ResearchBrowser
    from searchos.tools.simple_browser.backend.base import FetchResult
    from searchos.tools.simple_browser.render import PageContents
    from searchos.tools.simple_browser.state import _format_fetch_error

    browser = ResearchBrowser()
    attempts = []
    async def fetch(url, **kwargs):
        return PageContents(url=url, text=_format_fetch_error(url, 0, 'reader unreachable'))
    async def fallback(self, url, **kwargs):
        assert self._trust_env is True and self._allow_redirects is False
        attempts.append(url)
        return FetchResult(url=url, markdown='Real HTTP content supports pagination.', title='Docs')
    monkeypatch.setattr('searchos.tools.simple_browser.tools._fetch_page', fetch)
    monkeypatch.setattr('searchos.tools.simple_browser.backend.aiohttp.AiohttpBackend.fetch', fallback)

    opened = await browser.dispatch('web_open', {'id_or_url': 'https://example.com/api'})
    assert opened['live_evidence'] is True and opened['content_source'] == 'page'
    assert opened['access_method'] == 'http_fallback' and opened['proxy_mode'] == 'inherit'
    assert opened['reader_failure']['fetch_status'] == 'failed'
    assert not opened.get('error') and 'Real HTTP content' in opened['content']
    found = await browser.dispatch('web_find', {'pattern': 'pagination'})
    assert found['live_evidence'] is True and 'Real HTTP content' in found['content']
    await browser.dispatch('web_open', {'id_or_url': 'https://example.com/api'})
    await browser.dispatch('web_open', {'id_or_url': '99'})
    assert attempts == ['https://example.com/api']


@pytest.mark.asyncio
async def test_research_http_fallback_keeps_public_url_check(monkeypatch):
    from searchos.skills.pipeline.access.browser import ResearchBrowser
    from searchos.tools.simple_browser.render import PageContents
    from searchos.tools.simple_browser.state import _format_fetch_error

    async def fetch(url, **kwargs):
        return PageContents(url=url, text=_format_fetch_error(url, 0, 'reader unavailable'))
    async def fallback(*args, **kwargs):
        pytest.fail('HTTP fallback must not access a rejected URL')
    monkeypatch.setattr('searchos.tools.simple_browser.tools._fetch_page', fetch)
    monkeypatch.setattr('searchos.tools.simple_browser.backend.aiohttp.AiohttpBackend.fetch', fallback)
    result = await ResearchBrowser().dispatch('web_open', {'id_or_url': 'http://127.0.0.1/private'})
    assert result['live_evidence'] is False
    assert 'non-public' in result['fallback_error']


@pytest.mark.asyncio
async def test_research_reports_failed_fetch_without_treating_it_as_page_evidence(monkeypatch):
    from searchos.skills.pipeline.access.browser import ResearchBrowser
    from searchos.tools.simple_browser.render import PageContents
    from searchos.tools.simple_browser.state import _format_fetch_error

    browser = ResearchBrowser()
    async def fetch(url, **kwargs):
        return PageContents(url=url, text=_format_fetch_error(url, 403, 'Forbidden'))
    monkeypatch.setattr('searchos.tools.simple_browser.tools._fetch_page', fetch)

    opened = await browser.dispatch('web_open', {'id_or_url': 'https://example.com/blocked'})
    assert opened['fetch_status'] == 'failed'
    assert opened['content_source'] == 'none'
    assert opened['live_evidence'] is False
    assert opened['source_url'] == 'https://example.com/blocked'
    assert 'http_403' in opened['error']
    assert '[FETCH_ERROR]' in opened['content']
    found = await browser.dispatch('web_find', {'pattern': 'reason'})
    assert found['fetch_status'] == 'failed'
    assert found['live_evidence'] is False
    assert found['source_url'] == opened['source_url']


@pytest.mark.asyncio
async def test_research_search_fallback_remains_a_lead_after_open_find_and_scroll(monkeypatch):
    from searchos.skills.pipeline.access.browser import ResearchBrowser
    from searchos.tools.simple_browser.render import PageContents
    from searchos.tools.simple_browser.search.base import SearchResult
    from searchos.tools.simple_browser.state import _format_fetch_error

    browser = ResearchBrowser()
    class Provider:
        async def search(self, query, max_results):
            return [SearchResult(title='API docs', url='https://example.com/api',
                snippet='API supports pagination.\n' * 15)]
    async def fetch(url, **kwargs):
        return PageContents(url=url, text=_format_fetch_error(url, -1, 'Timeout'))
    browser.provider = Provider()
    monkeypatch.setattr('searchos.tools.simple_browser.tools._fetch_page', fetch)

    searched = await browser.dispatch('web_search', {'query': 'example API'})
    assert searched['content_source'] == 'search_results'
    assert searched['fetch_status'] == 'not_attempted'
    assert searched['live_evidence'] is False
    assert not searched.get('error')
    opened = await browser.dispatch('web_open', {'id_or_url': '0'})
    assert 'API supports pagination' in opened['content']
    assert opened['content_source'] == 'search_fallback'
    assert opened['fetch_status'] == 'failed'
    assert opened['live_evidence'] is False
    assert opened['error']
    found = await browser.dispatch('web_find', {'pattern': 'pagination'})
    scrolled = await browser.dispatch('web_open', {'id_or_url': 'https://example.com/api', 'loc': 10})
    for result in (found, scrolled):
        assert result['content_source'] == 'search_fallback'
        assert result['fetch_status'] == 'failed'
        assert result['live_evidence'] is False
        assert result['source_url'] == 'https://example.com/api'
    assert 'Live fetch failed' not in scrolled['content']  # Metadata survives a later viewport.


@pytest.mark.asyncio
async def test_research_search_engine_backend_does_not_claim_a_live_fetch(monkeypatch):
    from types import SimpleNamespace
    from searchos.skills.pipeline.access.browser import ResearchBrowser
    from searchos.tools.simple_browser.backend.base import BrowserService
    from searchos.tools.simple_browser.backend.search_engine import SearchEngineBackend
    from searchos.tools.simple_browser.render import PageContents

    browser = ResearchBrowser()
    async def fetch(url, **kwargs):
        return PageContents(url=url, text='Cached search content describes an API.')
    monkeypatch.setattr('searchos.tools.simple_browser.tools._fetch_page', fetch)
    monkeypatch.setattr(BrowserService, '_instance', SimpleNamespace(backend=SearchEngineBackend()))
    opened = await browser.dispatch('web_open', {'id_or_url': 'https://example.com/api'})
    assert opened['content_source'] == 'search_cache'
    assert opened['fetch_status'] == 'not_attempted' and opened['live_evidence'] is False
    assert not opened.get('error')


@pytest.mark.asyncio
async def test_research_success_and_tool_errors_never_share_stale_page_metadata(monkeypatch):
    from searchos.skills.pipeline.access.browser import ResearchBrowser
    from searchos.tools.simple_browser.render import PageContents

    browser = ResearchBrowser()
    async def fetch(url, **kwargs):
        return PageContents(url='https://example.com/docs', text='API supports pagination.\nMore details.')
    monkeypatch.setattr('searchos.tools.simple_browser.tools._fetch_page', fetch)

    opened = await browser.dispatch('web_open', {'id_or_url': 'https://example.com/redirect'})
    assert opened['source_url'] == 'https://example.com/docs'
    assert opened['view_url'] == 'https://example.com/docs'
    assert opened['content_source'] == 'page'
    assert opened['fetch_status'] == 'ok' and opened['live_evidence'] is True
    assert opened['read_from_cache'] is False
    cached = await browser.dispatch('web_open', {'id_or_url': 'https://example.com/docs'})
    assert cached['read_from_cache'] is True
    assert cached['live_evidence'] is True
    found = await browser.dispatch('web_find', {'pattern': 'pagination'})
    assert found['source_url'] == 'https://example.com/docs' and found['live_evidence'] is True
    failed = await browser.dispatch('web_open', {'id_or_url': '99'})
    assert failed['fetch_status'] == 'tool_error' and failed['error']
    assert failed['live_evidence'] is False
    assert failed['source_url'] == '' and failed['view_url'] == ''


@pytest.mark.asyncio
async def test_research_search_open_find_keeps_parent_and_other_builders_isolated(tmp_path, monkeypatch):
    from searchos.tools.simple_browser import state
    from searchos.tools.simple_browser.search.base import SearchResult
    from searchos.tools.simple_browser.render import PageContents
    from searchos.tools.search_state import _workspace_var

    parent = state.BrowserState()
    marker = object()
    bt = state._browser_var.set(parent)
    wt = _workspace_var.set(marker)
    a, b = BuilderWorkspace(tmp_path/'a'), BuilderWorkspace(tmp_path/'b')

    class Provider:
        async def search(self, query, max_results):
            assert _workspace_var.get() is None
            await asyncio.sleep(0)
            return [SearchResult(title=query, url='https://example.com/'+query, snippet='API documentation')]

    async def fetch(url, **kwargs):
        assert _workspace_var.get() is None
        return PageContents(url=url, title='Docs', text='Search supports pagination.\nAuthentication required.', urls={})

    a.browser.provider = b.browser.provider = Provider()
    monkeypatch.setattr('searchos.tools.simple_browser.tools._fetch_page', fetch)
    try:
        await asyncio.gather(a.dispatch('web_search', {'query': 'alpha'}), b.dispatch('web_search', {'query': 'beta'}))
        assert a.browser.state.search_history == ['alpha']
        assert b.browser.state.search_history == ['beta']
        opened = await a.dispatch('web_open', {'id_or_url': '0'})
        assert 'pagination' in opened['content']
        found = await a.dispatch('web_find', {'pattern': 'Authentication'})
        assert 'Authentication' in found['content']
        assert found['purpose'] == 'research_only'
        assert state._browser_var.get() is parent and not parent.has_pages
        assert _workspace_var.get() is marker
        with pytest.raises(ValueError, match='HTTP'):
            await a.dispatch('web_open', {'id_or_url': 'file:///etc/passwd'})
        assert state._browser_var.get() is parent
        assert _workspace_var.get() is marker
        assert a.files == set() and b.files == set()
    finally:
        a.close(); b.close()
        state._browser_var.reset(bt)
        _workspace_var.reset(wt)


@pytest.mark.asyncio
async def test_incremental_builder_keeps_old_files_and_tests_old_and_new_commands(tmp_path, monkeypatch):
    from langchain_core.messages import AIMessage
    from searchos.skills.pipeline.access.run import build_skill
    from searchos.skills.runtime import command_runtime
    original = tmp_path/'old/example-com'
    (original/'scripts').mkdir(parents=True)
    (original/'SKILL.md').write_text('---\nname: example-com\ndescription: 读取数据\nmetadata:\n  searchos-category: access\n  host: example.com\n---\n读取说明。')
    (original/'scripts/detail.py').write_text('print("old")')
    (original/'debug.log').write_text('excluded')
    seen = []
    async def run(package, argv, **kwargs):
        seen.append(argv)
        return {'exit_code': 0, 'stdout': json.dumps({'records': [{'url': 'https://example.com/1', 'text': 'data'}]})}
    monkeypatch.setattr(command_runtime, 'run_command', run)
    class Model:
        count = 0
        def bind_tools(self, tools): return self
        async def ainvoke(self, messages):
            self.count += 1
            if self.count > 1: return AIMessage(content='完成')
            assert 'scripts/detail.py' in messages[1].content
            return AIMessage(content='', tool_calls=[
                {'id':'1', 'name':'write_file', 'args':{'path':'scripts/search.py','content':'print("new")'}},
                *[{'id':str(i+2), 'name':'register_example', 'args':{'argv':['python',script], 'output':'', 'records_key':'records'}} for i,script in enumerate(['scripts/detail.py','scripts/search.py'])],
            ])
    target = tmp_path/'new/example-com'
    assert await build_skill('example.com', [], output_dir=target, existing_package=original, builder_model=Model()) == target
    assert (target/'scripts/detail.py').read_text() == 'print("old")'
    assert (target/'scripts/search.py').exists()
    assert not (original/'scripts/search.py').exists()
    assert not (target/'debug.log').exists()
    assert {v[1] for v in seen} == {'scripts/detail.py','scripts/search.py'}


@pytest.mark.asyncio
async def test_documented_search_cannot_skip_authentication_validation(tmp_path, monkeypatch):
    from searchos.skills.pipeline.access.valid import validate_access_package
    from searchos.skills.runtime import command_runtime
    package = tmp_path/'x-com'
    (package/'scripts').mkdir(parents=True)
    (package/'SKILL.md').write_text('---\nname: x-com\ndescription: 搜索 X\nmetadata:\n  searchos-category: access\n  host: x.com\n  searchos-browser-profile: x\n  searchos-browser-entries: scripts/search.py\n---\npython scripts/search.py --query NASA\n')
    (package/'scripts/search.py').write_text('print("search")')
    missing = await validate_access_package(package, 'x-com', [])
    assert not missing['valid'] and missing['missing_entries'] == ['scripts/search.py']
    async def run(package, argv, **kwargs):
        if '--help' in argv: return {'exit_code':0}
        return {'status':'blocked','auth_required':True,'started':False,'error':'auth_required'}
    monkeypatch.setattr(command_runtime, 'run_command', run)
    blocked = await validate_access_package(package, 'x-com', [{'argv':['python','scripts/search.py','--query','NASA']}])
    assert not blocked['valid'] and blocked['stage']=='authentication' and blocked['auth_required']


@pytest.mark.asyncio
@pytest.mark.parametrize('change', [True, False])
async def test_update_cannot_finish_by_only_revalidating_old_package(tmp_path, monkeypatch, change):
    from langchain_core.messages import AIMessage
    from searchos.skills.pipeline.access.run import build_skill
    from searchos.skills.runtime import command_runtime
    original = tmp_path/'old/example-com'
    (original/'scripts').mkdir(parents=True)
    (original/'SKILL.md').write_text('---\nname: example-com\ndescription: 读取\nmetadata:\n  searchos-category: access\n  host: example.com\n---\npython scripts/access.py\n')
    (original/'scripts/access.py').write_text('print("old")')
    async def run(*args, **kwargs):
        return {'exit_code': 0, 'stdout': json.dumps({'records':[{'title':'record','source_url':'https://example.com/a'}]})}
    monkeypatch.setattr(command_runtime, 'run_command', run)
    class Model:
        count = 0
        def bind_tools(self, tools): return self
        async def ainvoke(self, messages):
            self.count += 1
            if self.count == 1:
                return AIMessage(content='', tool_calls=[{'id':'read','name':'read_file','args':{'path':'scripts/access.py'}}])
            return AIMessage(content='', tool_calls=[{'id':'edit','name':'edit_file','args':{
                'path':'scripts/access.py','old_text':'old','new_text':'new'}}]) if change else AIMessage(content='完成')
    model = Model()
    target = tmp_path/'new/example-com'
    result = await build_skill('example.com', [], output_dir=target, existing_package=original,
        builder_model=model, max_turns=2, validation_examples=[{'argv':['python','scripts/access.py'],'output':'','records_key':'records'}])
    assert model.count == 2
    if change:
        assert result == target and (target/'scripts/access.py').read_text() == 'print("new")'
    else:
        assert result is None and not target.exists()
