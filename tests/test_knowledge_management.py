"""知识库管理通过真实持久化与 HTTP 接口验证，不操作用户资料。"""

from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from searchos.local.index.catalog import CatalogMarkdownStore, CatalogService
from searchos.local.index.document_store import DocumentMarkdownStore
from searchos.local.index.source_registry import SourceRegistry
from searchos.local.library import LocalLibraryService
from searchos.local.pipeline import DocumentRecapPipeline
from tests.test_local_webui import _FakeCatalogClient, _FakeRecapClient


async def seed(tmp_path):
    service = LocalLibraryService(tmp_path / "data")
    library = service.create_library("管理测试")
    incoming = tmp_path / "incoming"
    incoming.write_text("# 项目资料\n项目代号是蓝鲸。", encoding="utf-8")
    doc = await service.index_uploaded_file(library.library_id, incoming, "原件.md")
    await service.enrich_document(
        library.library_id,
        doc["document_id"],
        pipeline=DocumentRecapPipeline(
            output_root=library.index_root,
            recap_client=_FakeRecapClient(),
            catalog_client=_FakeCatalogClient(),
            recap_model_name="fixture",
        ),
    )
    return service, library, doc


@pytest.mark.asyncio
async def test_edit_names_and_manual_topic_summary_survive_automatic_indexing(tmp_path):
    service, lib, doc = await seed(tmp_path)
    root = Path(lib.index_root)
    store = CatalogMarkdownStore(root)
    topic_id = next(iter(store.load()))
    service.edit_document(lib.library_id, doc["document_id"], "蓝鲸资料")
    service.edit_topic(lib.library_id, "手工主题", "人工核对后的说明", topic_id)
    record = SourceRegistry(root).read(doc["document_id"])
    parsed, _ = DocumentMarkdownStore(root).load_current_document(
        record.document_id,
        content_hash=record.source_revision,
        parse_key=record.parse_key,
    )
    await CatalogService(root, _FakeCatalogClient()).upsert(parsed, record.recap)
    topic = store.load()[topic_id]
    assert topic.title == "手工主题"
    assert topic.summary == "人工核对后的说明"
    assert topic.documents[record.document_id].name == "蓝鲸资料"
    assert service.original_path(lib.library_id, record.document_id).name == "原件.md"


@pytest.mark.asyncio
async def test_empty_topic_is_persistent_and_deleting_topic_preserves_documents(tmp_path):
    service, lib, doc = await seed(tmp_path)
    root = Path(lib.index_root)
    graph = service.edit_topic(lib.library_id, "空主题", "待整理")
    topic_id = next(n["subindex_id"] for n in graph["nodes"] if n["label"] == "空主题")
    assert topic_id in CatalogMarkdownStore(root).load()
    service.set_document_topics(lib.library_id, doc["document_id"], [topic_id])
    service.delete_topic(lib.library_id, topic_id)
    graph = service.library_graph(lib.library_id)
    assert not any(n.get("subindex_id") == topic_id for n in graph["nodes"])
    assert len(service.list_documents(lib.library_id)) == 1
    assert service.original_path(lib.library_id, doc["document_id"]).exists()
    assert doc["document_id"] in CatalogMarkdownStore(root).read_state()["manual_documents"]


@pytest.mark.asyncio
async def test_delete_document_cleans_files_memberships_and_blocks_stale_publish(tmp_path):
    service, lib, doc = await seed(tmp_path)
    root = Path(lib.index_root)
    registry = SourceRegistry(root)
    record = registry.read(doc["document_id"])
    parsed, _ = DocumentMarkdownStore(root).load_current_document(
        record.document_id,
        content_hash=record.source_revision,
        parse_key=record.parse_key,
    )
    original = service.original_path(lib.library_id, record.document_id)
    service.delete_document(lib.library_id, record.document_id)
    assert service.list_documents(lib.library_id) == []
    assert not original.exists()
    assert not (root / "texts" / record.document_id).exists()
    assert not CatalogMarkdownStore(root).contains_document(record.document_id)
    with pytest.raises(FileNotFoundError, match="已删除"):
        registry.write(record)
    with pytest.raises(FileNotFoundError, match="已删除"):
        await CatalogService(root, _FakeCatalogClient()).upsert(parsed, record.recap)
    with pytest.raises(FileNotFoundError):
        service.original_path(lib.library_id, record.document_id)


@pytest.mark.asyncio
async def test_delete_pending_document_and_library_preserves_other_library(tmp_path):
    service, lib, doc = await seed(tmp_path)
    other = service.create_library("保留的资料库")
    incoming = tmp_path / "saved"
    incoming.write_text("尚未解析", encoding="utf-8")
    pending = service.save_original_file(lib.library_id, incoming, "pending.txt")
    service.delete_document(lib.library_id, pending["document_id"])
    assert [d["document_id"] for d in service.list_documents(lib.library_id)] == [
        doc["document_id"]
    ]
    record = SourceRegistry(Path(lib.index_root)).read(doc["document_id"])
    service.delete_library(lib.library_id)
    assert [r.library_id for r in service.list_libraries()] == [other.library_id]
    assert service.library_graph(other.library_id)["nodes"]
    assert not Path(record.source_path).exists()
    with pytest.raises(KeyError):
        service.get_library(lib.library_id)
    with pytest.raises(FileNotFoundError, match="已删除"):
        SourceRegistry(Path(lib.index_root)).ensure_library()


@pytest.mark.asyncio
async def test_management_http_validation_and_job_cancellation(tmp_path, monkeypatch):
    from api import topic_recap_jobs
    from api.local_index_jobs import LocalIndexJobStore
    from api.routes import local_search

    service, lib, doc = await seed(tmp_path)
    monkeypatch.setattr(local_search, "LOCAL_DATA_ROOT", service.data_root)
    monkeypatch.setattr(local_search, "_service", lambda: service)
    monkeypatch.setattr(topic_recap_jobs, "schedule_topic_recaps", lambda *args: None)
    jobs = LocalIndexJobStore(service.data_root)
    job = jobs.create(
        library_id=lib.library_id,
        document_id=doc["document_id"],
        source_revision=doc["source_revision"],
        file_name=doc["name"],
    )
    app = FastAPI()
    app.include_router(local_search.router)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        base = f"/api/local/libraries/{lib.library_id}"
        assert (
            await client.patch(base + f"/documents/{doc['document_id']}", json={"name": "  "})
        ).status_code == 422
        response = await client.patch(
            base + f"/documents/{doc['document_id']}", json={"name": "新版名称"}
        )
        assert response.status_code == 200
        assert any(n["label"] == "新版名称" for n in response.json()["nodes"])
        response = await client.post(
            base + "/topics", json={"title": "测试主题", "summary": "说明"}
        )
        topic_id = next(
            n["subindex_id"] for n in response.json()["nodes"] if n["label"] == "测试主题"
        )
        assert (
            await client.patch(base + f"/topics/{topic_id}", json={"title": "改名主题"})
        ).status_code == 200
        assert (await client.delete(base + f"/topics/{topic_id}")).status_code == 200
        assert (await client.delete(base + f"/topics/{topic_id}")).status_code == 404
        assert (await client.delete(base + f"/documents/{doc['document_id']}")).status_code == 200
        assert jobs.read(job.job_id).status == "cancelled"
        assert (
            await client.get(base + f"/documents/{doc['document_id']}/original")
        ).status_code == 404
        assert (await client.delete(base)).status_code == 200
        assert (await client.get(base + "/documents")).status_code == 404


@pytest.mark.asyncio
async def test_unknown_document_and_cross_library_mutations_do_not_remove_files(tmp_path):
    service, lib, doc = await seed(tmp_path)
    other = service.create_library("其他库")
    with pytest.raises(KeyError):
        service.delete_document(other.library_id, doc["document_id"])
    with pytest.raises(ValueError):
        service.delete_document(lib.library_id, "../sources")
    assert service.original_path(lib.library_id, doc["document_id"]).exists()
