from __future__ import annotations

from pathlib import Path

import pytest


def _temporary(tmp_path, name: str, body: str):
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return path


def test_save_only_is_visible_unsearchable_and_deduplicated(tmp_path):
    from searchos.local.library import LocalLibraryService

    service = LocalLibraryService(tmp_path / "data")
    library = service.create_library("研究资料")
    first = service.save_original_file(
        library.library_id,
        _temporary(tmp_path, "first.md", "# Saved page\n\nEvidence."),
        "saved-page.md",
        origin={"request_url": "https://example.com/page", "saved_form": "web_markdown_copy"},
    )
    assert first["status"] == "saved"
    assert first["searchable"] is False
    assert service.original_path(library.library_id, first["document_id"]).read_text().startswith("# Saved")

    second = service.save_original_file(
        library.library_id,
        _temporary(tmp_path, "second.md", "# Saved page\n\nEvidence."),
        "another-name.md",
        origin={"request_url": "https://mirror.example/page"},
    )
    assert second["deduplicated"] is True
    assert second["document_id"] == first["document_id"]
    assert {item["request_url"] for item in second["origin"]["sources"]} == {
        "https://example.com/page", "https://mirror.example/page",
    }
    documents = service.list_documents(library.library_id)
    assert len(documents) == 1
    assert documents[0]["parse_status"] == "pending"


@pytest.mark.asyncio
async def test_saved_markdown_can_be_parsed_later_and_keeps_origin(tmp_path):
    from searchos.local.index.source_registry import SourceRegistry
    from searchos.local.library import LocalLibraryService

    service = LocalLibraryService(tmp_path / "data")
    library = service.create_library("研究资料")
    saved = service.save_original_file(
        library.library_id,
        _temporary(tmp_path, "page.md", "# Heading\n\nA sufficiently useful local page."),
        "page.md",
        origin={"request_url": "https://example.com/page"},
    )
    parsed = await service.parse_saved_document(library.library_id, saved["document_id"])
    assert parsed["searchable"] is True
    record = SourceRegistry(Path(service.get_library(library.library_id).index_root)).read(
        saved["document_id"],
    )
    assert record.origin["request_url"] == "https://example.com/page"


def test_network_import_job_idempotency(tmp_path):
    from api.network_import_jobs import NetworkImportJobStore

    store = NetworkImportJobStore(tmp_path)
    kwargs = {
        "library_id": "lib_a",
        "source_url": "https://example.com/file.pdf",
        "title": "file",
        "session_id": "",
        "page_id": "",
        "index_after_save": True,
        "idempotency_key": "same-request",
    }
    first = store.create(**kwargs)
    second = store.create(**kwargs)
    assert second.job_id == first.job_id


def test_network_import_prefers_the_saved_workspace_page(tmp_path, monkeypatch):
    from api import network_import_jobs

    from searchos.socm.workspace import WorkspaceManager

    workspace_root = tmp_path / "workspaces"
    monkeypatch.setattr(network_import_jobs, "WORKSPACE_ROOT", workspace_root)
    workspace = WorkspaceManager(workspace_root, "session-a")
    workspace.create()
    workspace.write_page(
        "abc123",
        "https://example.com/report-short",
        "# 完整页面\n\n会话中已经读取的 Markdown 正文。",
        "报告标题",
        source_url="https://example.com/report?final=1",
    )
    job = network_import_jobs.NetworkImportJob(
        job_id="import_abc",
        idempotency_key="page",
        library_id="library",
        source_url="https://example.com/report?final=1",
        session_id="session-a",
        page_id="abc123",
        created_at="2026-09-14T00:00:00+00:00",
        updated_at="2026-09-14T00:00:00+00:00",
    )

    content, content_type, filename = network_import_jobs._saved_page(job)

    assert content.decode() == "# 完整页面\n\n会话中已经读取的 Markdown 正文。"
    assert content_type == "text/markdown"
    assert filename == "报告标题.md"


@pytest.mark.asyncio
async def test_network_import_fetches_web_markdown_when_direct_page_access_is_blocked(monkeypatch):
    from types import SimpleNamespace

    from api import network_import_jobs

    from searchos.tools.simple_browser.backend.jina import JinaReaderBackend

    async def fake_fetch(_self, url, *, query="", timeout=60):
        return SimpleNamespace(
            ok=True,
            markdown="# 百度百科\n\n完整页面内容。",
            title="条目标题",
            url=url,
            error="",
            status=200,
        )

    monkeypatch.setattr(JinaReaderBackend, "fetch", fake_fetch)
    job = network_import_jobs.NetworkImportJob(
        job_id="import_abc",
        idempotency_key="page",
        library_id="library",
        source_url="https://baike.baidu.com/item/example?bst=temporary",
        created_at="2026-09-14T00:00:00+00:00",
        updated_at="2026-09-14T00:00:00+00:00",
    )

    content, filename, final_url = await network_import_jobs._fetch_web_markdown(job)

    assert content.decode().startswith("# 百度百科")
    assert filename == "条目标题.md"
    assert final_url == job.source_url


@pytest.mark.asyncio
async def test_network_import_uses_markdown_page_copy_after_direct_403(tmp_path, monkeypatch):
    from api import network_import_jobs

    class ForbiddenResponse:
        status = 403
        headers = {}

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

    class ForbiddenSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        def get(self, *_args, **_kwargs):
            return ForbiddenResponse()

    async def allow_url(_url):
        return None

    async def fetch_markdown(job):
        return "# 完整页面\n".encode(), "entry.md", job.source_url

    monkeypatch.setattr(network_import_jobs, "LOCAL_DATA_ROOT", tmp_path)
    monkeypatch.setattr(network_import_jobs.aiohttp, "ClientSession", ForbiddenSession)
    monkeypatch.setattr(network_import_jobs, "validate_public_url", allow_url)
    monkeypatch.setattr(network_import_jobs, "_fetch_web_markdown", fetch_markdown)
    job = network_import_jobs.NetworkImportJob(
        job_id="import_abc",
        idempotency_key="page",
        library_id="library",
        source_url="https://baike.baidu.com/item/example?bst=temporary",
        created_at="2026-09-14T00:00:00+00:00",
        updated_at="2026-09-14T00:00:00+00:00",
    )

    path, name, final_url = await network_import_jobs._download(job)
    try:
        assert path.read_text() == "# 完整页面\n"
        assert name == "entry.md"
        assert final_url == job.source_url
    finally:
        path.unlink()


def test_network_import_downloads_when_the_url_has_no_saved_page(tmp_path, monkeypatch):
    from api import network_import_jobs

    monkeypatch.setattr(network_import_jobs, "WORKSPACE_ROOT", tmp_path / "workspaces")
    job = network_import_jobs.NetworkImportJob(
        job_id="import_abc",
        idempotency_key="image",
        library_id="library",
        source_url="https://example.com/chart.png",
        session_id="session-a",
        page_id="abc123",
        created_at="2026-09-14T00:00:00+00:00",
        updated_at="2026-09-14T00:00:00+00:00",
    )

    assert network_import_jobs._saved_page(job) is None


@pytest.mark.asyncio
async def test_network_import_runs_in_background_to_saved_unindexed(tmp_path, monkeypatch):
    from api import network_import_jobs

    from searchos.local.library import LocalLibraryService

    service = LocalLibraryService(tmp_path)
    library = service.create_library("资料")
    store = network_import_jobs.NetworkImportJobStore(tmp_path)

    async def fake_download(_job):
        return (
            _temporary(tmp_path, "network.md", "# Network copy\n\nEvidence."),
            "network.md",
            "https://cdn.example/network.md",
        )

    monkeypatch.setattr(network_import_jobs, "_download", fake_download)
    job = network_import_jobs.schedule_network_import(
        library_id=library.library_id,
        source_url="https://example.com/network.md",
        title="Network",
        session_id="",
        page_id="",
        index_after_save=False,
        idempotency_key="background-save",
        store=store,
    )
    await network_import_jobs._tasks[job.job_id]
    completed = store.read(job.job_id)
    assert completed.status == "completed"
    assert completed.stage == "saved_unindexed"
    document = service.list_documents(library.library_id)[0]
    assert document["searchable"] is False
    assert document["origin"]["final_url"] == "https://cdn.example/network.md"
