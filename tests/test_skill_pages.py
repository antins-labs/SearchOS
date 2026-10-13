from searchos.harness.middleware.models import SourceContext
from searchos.harness.middleware.extraction import ExtractionCoordinator, WorkspaceEvidenceStore

"""Skill 页面首次浏览、翻页、跨 agent 读取与统一提取契约。"""

import json
import re
from types import SimpleNamespace

import pytest

from searchos.harness.middleware.extraction import (
    DeliveryMode,
    EvidenceSourceKind,
    ExtractionReceipt,
    WebEvidenceMiddleware,
)
from searchos.socm.workspace import WorkspaceManager
from searchos.tools import search_state
from searchos.tools.simple_browser import state, tools
from searchos.tools.simple_browser.skill_pages import show_skill_result


@pytest.fixture
def pages(tmp_path):
    workspace = WorkspaceManager(tmp_path, session_id="skill-pages")
    workspace.create()
    wt = search_state._workspace_var.set(workspace)
    bt = state._browser_var.set(state.BrowserState())
    yield workspace
    state._browser_var.reset(bt)
    search_state._workspace_var.reset(wt)


def page_url(view):
    return re.search(r"^URL: (\S+)", view, re.MULTILINE).group(1)


@pytest.mark.asyncio
async def test_large_result_is_bounded_browsable_and_durable(pages, monkeypatch):
    from searchos.skills.runtime.legacy import executor_runtime
    from searchos.tools.skill_catalog import _make_typed_tool

    calls = []
    payload = {"success": True, "records": [
        {"name": f"Hotel {i}", "id": i, "source_url": "https://example.org/hotels"}
        for i in range(500)
    ]}

    async def execute(*args, **kwargs):
        calls.append(kwargs)
        return payload

    async def no_fetch(*args, **kwargs):
        pytest.fail("saved result must never perform a network fetch")

    monkeypatch.setattr(executor_runtime, "run_executor", execute)
    monkeypatch.setattr(tools, "_fetch_page", no_fetch)
    tool = _make_typed_tool(skill_name="hotels", skill_dir=pages.path,
                            description="hotels", params_schema={"page": {"type": "integer"}})
    initial = await tool.ainvoke({"page": 1})
    url = page_url(initial)
    assert initial.startswith("[Now viewing]")
    assert len(initial) < state.VIEW_TOKENS * 4 + 1000
    assert "Hotel 0" in initial and "Hotel 499" not in initial
    saved = pages.read_page(state._compute_page_id(url))
    assert json.loads(saved.split("## Result\n\n", 1)[1]) == payload

    # Fresh agent browser reads the same saved snapshot, then follows find IDs.
    state._browser_var.set(state.BrowserState())
    assert await tools.open.ainvoke({"id_or_url": url}) == initial
    found = await tools.find.ainvoke({"pattern": "Hotel 499"})
    assert "Hotel 499" in found
    last = await tools.open.ainvoke({"id_or_url": 0})
    assert "Hotel 499" in last
    assert page_url(last) == url
    assert len(calls) == 1
    assert "not found" in await tools.open.ainvoke({"id_or_url": "skill://hotels/missing"})


@pytest.mark.asyncio
async def test_repeated_calls_have_distinct_snapshots_and_preserve_navigation(pages):
    first = show_skill_result("directory", {}, {"provinces": [{"id": 2, "name": "北京"}]})
    second = show_skill_result("directory", {}, {"provinces": [{"id": 3, "name": "天津"}]})
    assert page_url(first) != page_url(second)
    assert "北京" in await tools.open.ainvoke({"id_or_url": page_url(first)})
    assert '"id": 2' in first
    assert "天津" not in first


@pytest.mark.asyncio
async def test_initial_and_followup_views_use_identical_buffered_extraction(pages):
    middleware = WebEvidenceMiddleware(ExtractionCoordinator(None, WorkspaceEvidenceStore(pages)), source=SourceContext(workspace=pages))
    observations = []

    async def submit(observation, *, delivery):
        observations.append((observation, delivery))
        return ExtractionReceipt(accepted=True)

    middleware.coordinator.submit = submit
    initial = show_skill_result("directory", {}, {"rows": [{"name": f"row_{i}"} for i in range(1000)]})
    url = page_url(initial)
    followup = await tools.open.ainvoke({"id_or_url": url, "loc": 100})
    for name, text in [("skill_directory", initial), ("open", followup)]:
        result = SimpleNamespace(content=text)

        async def handler(_):
            return result

        returned = await middleware.awrap_tool_call(SimpleNamespace(tool_call={"name": name}), handler)
        assert returned.content == text
    assert len(observations) == 2
    for (obs, delivery), text in zip(observations, [initial, followup]):
        assert obs.content == text
        assert obs.source_url == url
        assert obs.page_id == state._compute_page_id(url)
        assert obs.source_kind == EvidenceSourceKind.PAGE
        assert delivery == DeliveryMode.BUFFERED
    assert "row_999" not in observations[0][0].content


@pytest.mark.asyncio
async def test_raw_skill_json_is_no_longer_a_special_extraction_input(pages):
    middleware = WebEvidenceMiddleware(ExtractionCoordinator(None, WorkspaceEvidenceStore(pages)), source=SourceContext(workspace=pages))

    async def submit(*args, **kwargs):
        pytest.fail("raw skill JSON must not trigger the old full-result extraction")

    middleware.coordinator.submit = submit
    result = SimpleNamespace(content=json.dumps({"data": "x" * 500}))

    async def handler(_):
        return result

    assert await middleware.awrap_tool_call(
        SimpleNamespace(tool_call={"name": "skill_fixture"}), handler
    ) is result


def test_long_skill_url_is_not_truncated(pages):
    view = show_skill_result("a" * 100, {}, {"ok": True})
    assert page_url(view) in state._get_browser().pages


@pytest.mark.parametrize("result", [
    {"records": [{"value": None, "details": [{"text": 'a|b\nc"\\', "empty": []}]},
                 {"value": "null", "flag": False, "details": {}}],
     "pagination": {"page": 1, "total": 2}},
    [1, "two", None, True, {"nested": [[], {}, -1.2e20]}],
    "long text " * 100, [], {}, None, 42,
])
def test_compact_json_preserves_arbitrary_structure(result):
    from searchos.tools.simple_browser.skill_pages import format_skill_result

    formatted = format_skill_result(result)
    assert json.loads(formatted) == result


def test_compact_json_packs_short_fields_and_respects_width():
    from searchos.tools.simple_browser.skill_pages import format_skill_result

    result = {f"field_{i}": i for i in range(50)}
    formatted = format_skill_result(result)
    lines = formatted.splitlines()
    assert all(len(line) <= 80 for line in lines)
    assert all(len(line) >= 65 for line in lines[:-1])
    assert len(lines) < 15
    assert list(json.loads(formatted)) == list(result)
    assert format_skill_result({"a": 1, "b": [2, 3]}) == '{"a": 1, "b": [2, 3]}'


@pytest.mark.asyncio
async def test_nested_detail_remains_in_place_and_browsable(pages):
    payload = {"records": [
        {"school": f"school_{i}", "details": {"text": "detail " * 100}}
        for i in range(65)
    ]}
    initial = show_skill_result("scores", {}, payload)
    assert "school_0" in initial and "school_64" not in initial
    found = await tools.find.ainvoke({"pattern": "school_64"})
    assert "school_64" in found
    detail = await tools.open.ainvoke({"id_or_url": 0})
    assert "school_64" in detail
    assert "detail detail" in detail


@pytest.mark.asyncio
@pytest.mark.parametrize("url", ["https://example.org/large", "skill://fixture/large"])
async def test_open_window_budget_for_web_and_skill_pages(pages, url):
    from searchos.tools.simple_browser.render import PageContents

    state._get_browser().add_page(PageContents(url=url, text="abcdefghij " * 10000))
    default = await tools.open.ainvoke({"id_or_url": url})
    explicit = await tools.open.ainvoke({"id_or_url": url, "view_tokens": state.VIEW_TOKENS})
    small = await tools.open.ainvoke({"id_or_url": url, "view_tokens": 2048})
    large = await tools.open.ainvoke({"id_or_url": url, "view_tokens": 8192})
    assert default == explicit
    assert len(small) < len(default) < len(large)
    assert len(large) < 8192 * 4 + 1000
    for invalid in (0, -1, 8193):
        assert "Error: view_tokens" in await tools.open.ainvoke({"id_or_url": url, "view_tokens": invalid})
