from searchos.harness.middleware.models import SourceContext
from searchos.harness.middleware.extraction import ExtractionCoordinator, WorkspaceEvidenceStore

"""浏览来源身份独立于展示、阅读位置和 find 构造地址。"""

from types import SimpleNamespace

import pytest

from searchos.harness.middleware.extraction import ExtractionReceipt, WebEvidenceMiddleware
from searchos.socm.workspace import WorkspaceManager
from searchos.tools import search_state
from searchos.tools.simple_browser import state, tools
from searchos.tools.simple_browser.render import PageContents


@pytest.fixture
def browser(tmp_path):
    workspace = WorkspaceManager(tmp_path, session_id="source-metadata")
    workspace.create()
    wt = search_state._workspace_var.set(workspace)
    instance = state.BrowserState()
    bt = state._browser_var.set(instance)
    yield instance, workspace
    state._browser_var.reset(bt)
    search_state._workspace_var.reset(wt)


async def call(tool, **args):
    return await tool.ainvoke({"type": "tool_call", "id": "reading", "name": tool.name, "args": args})


def add_page(browser, url):
    browser.add_page(PageContents(
        url=url, title="Population report",
        text="\n".join(f"Region {i} has 120000 residents. Annual population report and source details." for i in range(200)),
    ))


@pytest.mark.asyncio
async def test_long_url_and_scroll_share_original_source(browser):
    instance, _ = browser
    url = "https://example.org/report?document=" + "a" * 150 + "&version=2#table"
    add_page(instance, url)
    first = await call(tools.open, id_or_url=url, loc=0)
    second = await call(tools.open, id_or_url=url, loc=100)
    for message in (first, second):
        source = message.artifact["page_source"]
        assert source["source_url"] == url
        assert source["view_url"] == url
        assert source["page_id"] == state._compute_page_id(url)
        assert f"URL: {url}\n" in message.content
        assert source["viewport"]["coordinate_space"] == "source"
    assert first.artifact["page_source"]["viewport"]["start_line"] == 0
    assert second.artifact["page_source"]["viewport"]["start_line"] == 100


@pytest.mark.asyncio
async def test_find_views_and_real_find_url_keep_source_identity(browser):
    instance, workspace = browser
    # 真实网站路径包含 /find?；不能通过截字符串猜来源。
    url = "https://example.org/find?document=" + "b" * 150
    add_page(instance, url)
    opened = await call(tools.open, id_or_url=url)
    first = await call(tools.find, pattern="Region 10")
    second = await call(tools.find, pattern="Region 20")
    assert first.artifact["page_source"]["view_url"] != second.artifact["page_source"]["view_url"]
    for message in (first, second):
        assert message.artifact["page_source"]["source_url"] == url
        assert message.artifact["page_source"]["page_id"] == opened.artifact["page_source"]["page_id"]
        assert message.artifact["page_source"]["viewport"]["coordinate_space"] == "view"
    reopened = await call(tools.open, id_or_url=0)
    assert reopened.artifact["page_source"]["source_url"] == url
    assert "Region 20" in reopened.content

    middleware = WebEvidenceMiddleware(ExtractionCoordinator(None, WorkspaceEvidenceStore(workspace), batch_n=100), source=SourceContext(workspace=workspace))
    for name, message in [("open", opened), ("find", first), ("find", second)]:
        async def handler(_):
            return message
        await middleware.awrap_tool_call(SimpleNamespace(tool_call={"name": name}), handler)
    assert not middleware.coordinator._flush_tasks
    assert len(middleware.coordinator._pending_buffer) == 3
    assert {item["source_url"] for item in middleware.coordinator._pending_buffer} == {url}


@pytest.mark.asyncio
async def test_artifact_wins_and_plain_text_still_works(browser):
    instance, workspace = browser
    url = "https://example.org/find?document=original"
    add_page(instance, url)
    message = await call(tools.open, id_or_url=url)
    middleware = WebEvidenceMiddleware(ExtractionCoordinator(None, WorkspaceEvidenceStore(workspace)), source=SourceContext(workspace=workspace))
    seen = []

    async def submit(observation, **kwargs):
        seen.append(observation)
        return ExtractionReceipt(accepted=True)

    middleware.coordinator.submit = submit
    plain = SimpleNamespace(content=message.content)
    message.content = message.content.replace(url, "https://wrong.example/display")
    for result in (message, plain):
        async def handler(_):
            return result
        await middleware.awrap_tool_call(SimpleNamespace(tool_call={"name": "find"}), handler)
    assert [obs.source_url for obs in seen] == [url, url]


@pytest.mark.asyncio
async def test_distinct_query_values_do_not_merge_after_long_shared_prefix(browser):
    instance, workspace = browser
    prefix = "https://example.org/report?document=" + "c" * 150
    urls = [prefix + "&version=1", prefix + "&version=2"]
    middleware = WebEvidenceMiddleware(ExtractionCoordinator(None, WorkspaceEvidenceStore(workspace), batch_n=100), source=SourceContext(workspace=workspace))
    frozen = []
    middleware.coordinator._spawn_background_flush = lambda reason, *, snapshot: frozen.append((reason, snapshot))
    for url in urls:
        add_page(instance, url)
        message = await call(tools.open, id_or_url=url)
        async def handler(_):
            return message
        await middleware.awrap_tool_call(SimpleNamespace(tool_call={"name": "open"}), handler)
    assert len(frozen) == 1
    assert frozen[0][0] == "url_switch"
    assert frozen[0][1][0]["source_url"] == urls[0]
    assert middleware.coordinator._pending_buffer[0]["source_url"] == urls[1]


@pytest.mark.asyncio
async def test_error_does_not_reuse_previous_page_artifact(browser):
    instance, _ = browser
    add_page(instance, "https://example.org/report")
    message = await call(tools.open, id_or_url="https://example.org/report", loc=99999)
    assert message.content.startswith("Error:")
    assert message.artifact == {}
    invalid = await call(tools.open, id_or_url="https://example.org/report", view_tokens=0)
    assert invalid.artifact == {}
