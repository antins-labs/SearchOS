"""本地目录的真实搜索结果进入搜索失败记忆，目录读取与错误不形成空查询。"""

from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage

from searchos.config.settings import settings
from searchos.harness.middleware.extraction import InMemoryEvidenceStore
from searchos.harness.middleware.models import TaskContext
from searchos.harness.middleware.sensor.failure_recording_middleware import (
    FailureRecordingMiddleware,
)
from searchos.local.reader import tools
from searchos.socm import SearchState
from searchos.socm.failure_memory import post_mortem


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("args", "status", "count", "expected_content", "memory_count"),
    [
        ({"query": "unmatched term"}, "success", 0, "No local catalog matches", 1),
        ({"query": "history"}, "success", 1, "Historical archive history", 0),
        ({"path": "../outside.md", "query": "history"}, "error", None, "路径超出", 0),
        ({}, None, None, "[LOCAL_CATALOG]", 0),
        ({"query": "  "}, None, None, "[LOCAL_CATALOG]", 0),
    ],
)
async def test_real_local_catalog_failure_collection(
    tmp_path, monkeypatch, args, status, count, expected_content, memory_count
):
    monkeypatch.setattr(settings, "enable_failure_memory", True)
    root = tmp_path / "library"
    root.mkdir()
    (root / "INDEX.md").write_text("# Library\nHistorical archive history\n", encoding="utf-8")
    state = SearchState(source_scope={"mode": "local", "index_root": str(root)})
    workspace = InMemoryEvidenceStore(state)
    middleware = FailureRecordingMiddleware(workspace, task=TaskContext(agent_id="local"))
    token = tools._state_var.set(tools.LocalBrowserState(root=root))
    try:
        call = {"name": "local_catalog", "args": args, "id": "catalog", "type": "tool_call"}

        async def handler(request):
            return await tools.local_catalog.ainvoke(request.tool_call)

        result = await middleware.awrap_tool_call(SimpleNamespace(tool_call=call), handler)
        assert expected_content in result.content
        assert await tools.local_catalog.ainvoke(args) == result.content
        outcome = (result.artifact or {}).get("outcome", {})
        assert outcome.get("status") == status
        assert outcome.get("result_count") == count
        if status is None:
            assert "outcome" not in result.artifact
    finally:
        tools._state_var.reset(token)
    records = workspace.load_state().failure_memory.records
    assert len(records) == memory_count
    if records:
        assert records[0].kind.value == "query"
        assert records[0].target == args["query"]
        assert records[0].reason == "empty_result"
        assert records[0].observed_count == 1


@pytest.mark.asyncio
async def test_catalog_count_matches_returned_candidates(tmp_path):
    (tmp_path / "INDEX.md").write_text(
        "\n".join(f"history record {index}" for index in range(25)), encoding="utf-8"
    )
    token = tools._state_var.set(tools.LocalBrowserState(root=tmp_path))
    try:
        result = await tools.local_catalog.ainvoke(
            {
                "name": "local_catalog", "args": {"query": "history"},
                "id": "many", "type": "tool_call",
            }
        )
    finally:
        tools._state_var.reset(token)
    assert result.artifact["outcome"]["result_count"] == 20
    assert "# Match 19" in result.content and "# Match 20" not in result.content


@pytest.mark.asyncio
async def test_missing_library_does_not_report_successful_empty_search(tmp_path):
    token = tools._state_var.set(tools.LocalBrowserState(root=tmp_path / "missing"))
    try:
        result = await tools.local_catalog.ainvoke(
            {
                "name": "local_catalog", "args": {"query": "history"},
                "id": "missing", "type": "tool_call",
            }
        )
    finally:
        tools._state_var.reset(token)
    assert result.content.startswith("Error: 本地资料库不存在")
    assert result.artifact["outcome"] == {"status": "error"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("catalog_state", "expected_status", "memory_count"),
    [("missing_path", "error", 0), ("no_catalogs", "error", 0), ("empty_index", "success", 1)],
)
async def test_empty_query_requires_searching_an_existing_catalog(
    tmp_path, monkeypatch, catalog_state, expected_status, memory_count
):
    monkeypatch.setattr(settings, "enable_failure_memory", True)
    if catalog_state != "no_catalogs":
        (tmp_path / "INDEX.md").write_text("", encoding="utf-8")
    args = {"query": "history"}
    if catalog_state == "missing_path":
        args["path"] = "documents/missing.md"
    workspace = InMemoryEvidenceStore(
        SearchState(source_scope={"mode": "local", "index_root": str(tmp_path)})
    )
    middleware = FailureRecordingMiddleware(workspace, task=TaskContext(agent_id="local"))
    token = tools._state_var.set(tools.LocalBrowserState(root=tmp_path))
    try:
        call = {"name": "local_catalog", "args": args, "id": "catalog", "type": "tool_call"}

        async def handler(request):
            return await tools.local_catalog.ainvoke(request.tool_call)

        result = await middleware.awrap_tool_call(SimpleNamespace(tool_call=call), handler)
    finally:
        tools._state_var.reset(token)
    assert result.content == "No local catalog matches for: history"
    assert result.artifact["outcome"]["status"] == expected_status
    if expected_status == "success":
        assert result.artifact["outcome"]["result_count"] == 0
    else:
        assert "result_count" not in result.artifact["outcome"]
    assert len(workspace.load_state().failure_memory.records) == memory_count


@pytest.mark.asyncio
async def test_catalog_candidate_links_survive_bounded_review_and_require_real_reading(tmp_path):
    from pathlib import Path

    from searchos.local.library import LocalLibraryService
    from searchos.local.reader.references import build_ref_id

    service = LocalLibraryService(tmp_path / "data")
    library = service.create_library("Local sources")
    source = tmp_path / "source.md"
    source.write_text("# Unrelated source\nThe document contains other facts.\n", encoding="utf-8")
    document = await service.index_uploaded_file(library.library_id, source, source.name)
    record, block = service._verified_blocks(library.library_id, [document["document_id"]])[0]
    ref_id = build_ref_id(
        library_id=library.library_id,
        document_id=record.document_id,
        source_revision=record.source_revision,
        locators=list(block.source_locators),
    )
    root = Path(library.index_root)
    (root / "INDEX.md").write_text(
        "needle " + "x" * 1500 + f"\nneedle [second candidate]({ref_id})\n", encoding="utf-8"
    )
    token = tools._state_var.set(tools.LocalBrowserState(root=root))
    try:
        search_args = {"query": "needle"}
        query = await tools.local_catalog.ainvoke(
            {"name": "local_catalog", "args": search_args, "id": "query", "type": "tool_call"}
        )
        assert query.artifact["results"] == [{"ref_id": ref_id}]
        messages = [
            AIMessage(
                content="",
                tool_calls=[{"name": "local_catalog", "args": search_args, "id": "query"}],
            ),
            query,
        ]
        calls = post_mortem._trace_calls(messages)
        assert ref_id not in calls[0]["content"]
        assert not post_mortem._supported_query("needle", calls)
        reading_args = {"ref_id": ref_id}
        reading = await tools.local_open.ainvoke(
            {"name": "local_open", "args": reading_args, "id": "read", "type": "tool_call"}
        )
    finally:
        tools._state_var.reset(token)
    messages.extend([
        AIMessage(
            content="", tool_calls=[{"name": "local_open", "args": reading_args, "id": "read"}]
        ),
        reading,
    ])
    calls = post_mortem._trace_calls(messages)
    assert post_mortem._supported_query("needle", calls)
