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
    if not request.node.originalname.startswith('test_research_http_reader_'):
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


@pytest.fixture
def http_reader_response(monkeypatch):
    """Fake only HTTP transport, keeping research fallback and parsing real."""
    def install(content_type, body, *, status=200):
        calls = {'chunks': 0, 'requests': 0}
        class Response:
            headers = {'Content-Type': content_type}
            content = None
            async def iter_chunked(self, size):
                for offset in range(0, len(body), size):
                    calls['chunks'] += 1
                    yield body[offset:offset+size]
            async def __aenter__(self): return self
            async def __aexit__(self, *args): pass
        response = Response()
        response.status = status
        response.content = response
        class Session:
            def __init__(self, **kwargs): calls['session'] = kwargs
            async def __aenter__(self): return self
            async def __aexit__(self, *args): pass
            def get(self, url, **kwargs):
                calls['requests'] += 1
                calls['request'] = kwargs
                return response
        monkeypatch.setattr('searchos.tools.simple_browser.backend.aiohttp.aiohttp.ClientSession', Session)
        monkeypatch.setattr('searchos.tools.simple_browser.backend.aiohttp.aiohttp.TCPConnector', lambda **kwargs: calls.setdefault('connector', kwargs))
        from searchos.tools.simple_browser.render import PageContents
        from searchos.tools.simple_browser.state import _format_fetch_error
        async def primary(url, **kwargs):
            return PageContents(url=url, text=_format_fetch_error(url, -2, 'unsupported_content_type'))
        monkeypatch.setattr('searchos.tools.simple_browser.tools._fetch_page', primary)
        return calls
    return install


@pytest.mark.asyncio
@pytest.mark.parametrize('content_type', ['application/json', 'application/json; charset=utf-8', 'Application/vnd.test+json'])
async def test_research_http_reader_reads_api_json_as_findable_page(http_reader_response, content_type):
    import ssl
    from searchos.skills.pipeline.access.browser import ResearchBrowser
    payload = {'status': 'ok', 'message': {'items': [{'title': ['Readable 中文'], 'DOI': '10.1/example'}]}}
    calls = http_reader_response(content_type, json.dumps(payload, ensure_ascii=False).encode())
    browser = ResearchBrowser()
    url = 'https://example.com/works?query=research&rows=1'
    opened = await browser.dispatch('web_open', {'id_or_url': url})
    assert opened['live_evidence'] is True and opened['fetch_status'] == 'ok'
    assert opened['access_method'] == 'http_fallback' and opened['source_url'] == url
    assert json.loads(browser.state.get_page().text) == payload
    found = await browser.dispatch('web_find', {'pattern': 'Readable 中文'})
    assert found['live_evidence'] is True and 'Readable 中文' in found['content']
    await browser.dispatch('web_open', {'id_or_url': url})
    assert calls['requests'] == 1 and calls['session']['trust_env'] is True
    assert calls['request']['allow_redirects'] is False
    assert calls['connector']['ssl'].verify_mode == ssl.CERT_REQUIRED


@pytest.mark.asyncio
@pytest.mark.parametrize('body', [b'{"items":', b'{"x": NaN}', b'{"x": Infinity}', b'{"x":1e309}',
    b'{"status":"ok","status":"error"}', b'\xff', b'<html>not JSON</html>', b''])
async def test_research_http_reader_rejects_malformed_json_as_live_evidence(http_reader_response, body):
    from searchos.skills.pipeline.access.browser import ResearchBrowser
    http_reader_response('application/json', body)
    result = await ResearchBrowser().dispatch('web_open', {'id_or_url': 'https://example.com/api'})
    assert result['live_evidence'] is False and result['fetch_status'] == 'failed'
    assert 'invalid JSON' in result['fallback_error']


@pytest.mark.asyncio
@pytest.mark.parametrize('status', [302, 404, 429, 500])
async def test_research_http_reader_keeps_json_http_failures_unusable(http_reader_response, status):
    from searchos.skills.pipeline.access.browser import ResearchBrowser
    calls = http_reader_response('application/json', b'{"items":[]}', status=status)
    result = await ResearchBrowser().dispatch('web_open', {'id_or_url': 'https://example.com/api'})
    assert result['live_evidence'] is False and result['fetch_status'] == 'failed'
    assert result['fallback_error'] == f'HTTP {status}'
    assert calls['requests'] == 1 and calls['chunks'] == 0


@pytest.mark.asyncio
async def test_research_http_reader_bounds_json_before_decoding(http_reader_response):
    from searchos.skills.pipeline.access.browser import ResearchBrowser
    calls = http_reader_response('application/json', b'{"large":"' + b'x' * 2_000_000 + b'"}')
    result = await ResearchBrowser().dispatch('web_open', {'id_or_url': 'https://example.com/api'})
    assert result['live_evidence'] is False
    assert 'exceeds 1000000 bytes' in result['fallback_error']
    assert calls['chunks'] <= 16  # Stop at the first chunk beyond the decoded byte cap.


@pytest.mark.asyncio
@pytest.mark.parametrize('content_type', ['text/json', 'application/javascript', 'application/+json', 'text/html+json'])
async def test_research_http_reader_does_not_sniff_unapproved_json_types(http_reader_response, content_type):
    from searchos.skills.pipeline.access.browser import ResearchBrowser
    calls = http_reader_response(content_type, b'{"items":[]}')
    result = await ResearchBrowser().dispatch('web_open', {'id_or_url': 'https://example.com/api'})
    assert result['live_evidence'] is False and 'unsupported content-type' in result['fallback_error']
    assert calls['chunks'] == 0


@pytest.mark.asyncio
async def test_research_http_reader_json_does_not_widen_default_html_reader(http_reader_response):
    from searchos.tools.simple_browser.backend.aiohttp import AiohttpBackend
    calls = http_reader_response('application/json', b'{"items":[]}')
    result = await AiohttpBackend(max_retries=0).fetch('https://example.com/api')
    assert not result.ok and 'unsupported content-type' in result.error
    assert calls['chunks'] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize('under_limit', [False, True])
async def test_research_http_reader_json_limit_counts_utf8_bytes_across_chunks(http_reader_response, under_limit):
    from searchos.tools.simple_browser.backend.aiohttp import AiohttpBackend
    value = {'title': '中' * 22000, 'count': 0}
    body = json.dumps(value, ensure_ascii=False).encode()
    calls = http_reader_response('application/json', body)
    result = await AiohttpBackend(max_retries=0, allow_json=True,
        max_html_bytes=len(body) - int(under_limit)).fetch('https://example.com/api')
    assert calls['chunks'] == 2
    assert result.ok is not under_limit
    assert result.html == ''
    if under_limit:
        assert f'exceeds {len(body)-1} bytes' in result.error
    else:
        assert json.loads(result.markdown) == value


@pytest.mark.asyncio
async def test_research_http_reader_bounds_json_rendering_expansion(http_reader_response):
    from searchos.tools.simple_browser.backend.aiohttp import AiohttpBackend
    body = b'[' * 50 + b','.join([b'0'] * 500) + b']' * 50
    http_reader_response('application/json', body)
    result = await AiohttpBackend(max_retries=0, allow_json=True,
        max_html_bytes=len(body)).fetch('https://example.com/api')
    assert not result.ok and 'rendered JSON exceeds' in result.error
    assert result.markdown == ''


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
