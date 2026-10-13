"""研究会话隔离与增量生成行为。"""
import asyncio
import json

import pytest

from searchos.skills.pipeline.access.tools import BuilderWorkspace


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
