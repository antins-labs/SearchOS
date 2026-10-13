"""Hybrid 从明确的资料库范围探索，而非依赖手选文档。"""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "web"))
from api.routes import local_search, search


@pytest.mark.asyncio
async def test_hybrid_library_request_keeps_readable_snapshot(monkeypatch, tmp_path):
    captured = {}
    record = SimpleNamespace(
        document_id="doc-a",
        model_dump=lambda **_: {
            "document_id": "doc-a",
            "relative_path": "notes.md",
            "source_revision": "r1",
            "generation": "g1",
        },
    )
    service = SimpleNamespace(
        get_library=lambda _: SimpleNamespace(library_id="chosen", index_root=str(tmp_path)),
        list_documents=lambda _: [
            {"document_id": "doc-a", "searchable": True},
            {"document_id": "pending", "searchable": False},
        ],
        _verified_blocks=lambda library_id, ids: [(record, None)] if ids == ["doc-a"] else [],
    )

    async def launch(**kwargs):
        captured.update(kwargs)
        return search.SearchResponse(session_id=kwargs["session_id"], status="running")

    monkeypatch.setattr(local_search, "_service", lambda: service)
    monkeypatch.setattr(search, "init_search_provider", lambda _: None)
    monkeypatch.setattr(search, "_launch_search", launch)
    await search.create_search(
        search.SearchRequest(
            query="根据库内资料补充相关信息",
            sources={
                "mode": "hybrid",
                "local": {
                    "library_id": "chosen",
                    "selection": "library",
                    "document_ids": [],
                    "model_access": True,
                },
            },
        )
    )
    scope = captured["state"].source_scope
    assert scope["selection"] == "library"
    assert scope["library_id"] == "chosen"
    assert [r["document_id"] for r in scope["documents"]] == ["doc-a"]


@pytest.mark.asyncio
async def test_library_snapshot_can_be_searched_without_reading_other_libraries(
    monkeypatch, tmp_path
):
    from searchos.agents.orchestrator.catalog import _is_agent_enabled
    from searchos.local.index.source_registry import SourceRecord
    from searchos.local.library import LocalLibraryService
    from searchos.local.reader.tools import local_catalog, local_open, reset_local_browser
    from searchos.tools.search_state import _source_scope_var

    service = LocalLibraryService(tmp_path / "data")
    library = service.create_library("Research")
    other = service.create_library("Outside")
    incoming = tmp_path / "input.txt"
    incoming.write_text("The Atlas method uses a navigation map to locate records.")
    doc = await service.index_uploaded_file(library.library_id, incoming, "atlas-notes.txt")
    incoming.write_text("Outside confidential material.")
    outside = await service.index_uploaded_file(other.library_id, incoming, "private.txt")
    captured = {}

    async def launch(**kwargs):
        captured.update(kwargs)
        return search.SearchResponse(session_id=kwargs["session_id"], status="running")

    monkeypatch.setattr(local_search, "_service", lambda: service)
    monkeypatch.setattr(search, "init_search_provider", lambda _: None)
    monkeypatch.setattr(search, "_launch_search", launch)
    selection = {
        "mode": "hybrid",
        "local": {"library_id": library.library_id, "selection": "library", "model_access": True},
    }
    await search.create_search(
        search.SearchRequest(query="Explore the collection", sources=selection)
    )
    scope = captured["state"].source_scope
    records = [SourceRecord.model_validate(r) for r in scope["documents"]]
    token = _source_scope_var.set(scope)
    try:
        assert _is_agent_enabled("local_search_agent")
        browser = reset_local_browser(
            scope["index_root"],
            source_roots=[Path(r.source_path).parent for r in records],
            selected_documents={r.document_id: (r.source_revision, r.generation) for r in records},
        )
        browser.selected_records = {r.document_id: r for r in records}
        catalog = await local_catalog.ainvoke({"query": "atlas"})
        assert doc["document_id"] in str(catalog)
        assert outside["document_id"] not in str(catalog)
        original = await local_catalog.ainvoke({"path": f"documents/{doc['document_id']}.md"})
        import re

        ref = re.search(r'ref_id="([^"\n]+)"', str(original)).group(1)
        content = await local_open.ainvoke({"ref_id": ref})
        assert "navigation map" in str(content)
        denied = await local_catalog.ainvoke({"path": f"documents/{outside['document_id']}.md"})
        assert "navigation map" not in str(denied)
        assert "范围" in str(denied)
    finally:
        _source_scope_var.reset(token)


@pytest.mark.asyncio
async def test_empty_library_followup_retains_library_selection(monkeypatch, tmp_path):
    from searchos.local.library import LocalLibraryService
    from searchos.socm.state import SearchState
    from searchos.socm.workspace import WorkspaceManager

    service = LocalLibraryService(tmp_path / "libraries")
    library = service.create_library("Initially empty")
    workspace = WorkspaceManager(tmp_path / "sessions", "followup")
    workspace.create()
    workspace.save_state(
        SearchState(
            source_scope={
                "mode": "hybrid",
                "library_id": library.library_id,
                "selection": "library",
                "document_ids": [],
                "documents": [],
            }
        )
    )
    incoming = tmp_path / "new.txt"
    incoming.write_text("Newly added material for the next turn.")
    doc = await service.index_uploaded_file(library.library_id, incoming, "new.txt")
    monkeypatch.setattr(search, "WORKSPACE_ROOT", str(workspace.path.parent))
    monkeypatch.setattr(search, "sessions", {})
    monkeypatch.setattr(local_search, "_service", lambda: service)
    monkeypatch.setattr(search, "init_search_provider", lambda _: None)
    captured = {}

    async def launch(**kwargs):
        captured.update(kwargs)
        return search.SearchResponse(session_id=kwargs["session_id"], status="running")

    monkeypatch.setattr(search, "_launch_search", launch)
    await search.create_search(
        search.SearchRequest(query="继续查看资料", follow_up_to=workspace.session_id)
    )
    scope = captured["state"].source_scope
    assert scope["selection"] == "library" and scope["document_ids"] == []
    assert [record["document_id"] for record in scope["documents"]] == [doc["document_id"]]


@pytest.mark.asyncio
async def test_empty_library_does_not_enable_local_agent(monkeypatch, tmp_path):
    from searchos.agents.orchestrator.catalog import _is_agent_enabled
    from searchos.local.library import LocalLibraryService
    from searchos.tools.search_state import _source_scope_var

    service = LocalLibraryService(tmp_path / "libraries")
    library = service.create_library("Empty")
    captured = {}

    async def launch(**kwargs):
        captured.update(kwargs)
        return search.SearchResponse(session_id=kwargs["session_id"], status="running")

    monkeypatch.setattr(local_search, "_service", lambda: service)
    monkeypatch.setattr(search, "init_search_provider", lambda _: None)
    monkeypatch.setattr(search, "_launch_search", launch)
    await search.create_search(
        search.SearchRequest(
            query="查找信息",
            sources={
                "mode": "hybrid",
                "local": {
                    "library_id": library.library_id,
                    "selection": "library",
                    "model_access": True,
                },
            },
        )
    )
    scope = captured["state"].source_scope
    assert scope["library_id"] == library.library_id and scope["documents"] == []
    token = _source_scope_var.set(scope)
    try:
        assert not _is_agent_enabled("local_search_agent")
        assert _is_agent_enabled("search_agent")
    finally:
        _source_scope_var.reset(token)


@pytest.mark.asyncio
async def test_legacy_document_scope_reuses_same_evidence_scope(monkeypatch, tmp_path):
    from searchos.local.library import LocalLibraryService
    from searchos.socm.state import SearchState
    from searchos.socm.workspace import WorkspaceManager

    service = LocalLibraryService(tmp_path / "libraries")
    library = service.create_library("Selected")
    incoming = tmp_path / "input.txt"
    incoming.write_text("Stable original.")
    doc = await service.index_uploaded_file(library.library_id, incoming, "notes.txt")
    records = {
        record.document_id: record
        for record, _ in service._verified_blocks(library.library_id, [doc["document_id"]])
    }
    workspace = WorkspaceManager(tmp_path / "sessions", "legacy")
    workspace.create()
    prior = SearchState(
        source_scope={
            "mode": "hybrid",
            "library_id": library.library_id,
            "index_root": library.index_root,
            "documents": [record.model_dump(mode="json") for record in records.values()],
        }
    )
    prior.coverage_map.add_table("existing", ["Name", "Value"], primary_key=["Name"])
    workspace.save_state(prior)
    captured = {}

    async def launch(**kwargs):
        captured.update(kwargs)
        return search.SearchResponse(session_id=kwargs["session_id"], status="running")

    monkeypatch.setattr(search, "WORKSPACE_ROOT", str(workspace.path.parent))
    monkeypatch.setattr(search, "sessions", {})
    monkeypatch.setattr(local_search, "_service", lambda: service)
    monkeypatch.setattr(search, "init_search_provider", lambda _: None)
    monkeypatch.setattr(search, "_launch_search", launch)
    await search.create_search(
        search.SearchRequest(query="Continue", follow_up_to=workspace.session_id)
    )
    assert "existing" in captured["state"].coverage_map.tables
    assert captured["state"].source_scope["selection"] == "documents"
