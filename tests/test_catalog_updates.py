"""目录多重归属、短引用名与并发摘要发布的行为契约。"""

import asyncio

import pytest

from searchos.local.index.catalog import (
    CatalogDocument,
    CatalogMarkdownStore,
    CatalogService,
    Subindex,
)
from searchos.local.models import DocumentRecap, ParsedDocument


def document(name="doc"):
    return ParsedDocument(
        document_id=name,
        name=f"{name}_original.txt",
        source_path="/unused",
        display_path=f"{name}.txt",
        kind="text",
        sha256="a" * 64,
        modified_ns=0,
        size_bytes=10,
    )


class Client:
    def __init__(self):
        self.classifications = 0
        self.revisions = []
        self.fail = False

    async def classify_document(self, doc, existing):
        self.classifications += 1
        return {
            "display_name": "WASP 导航研究",
            "subindexes": [
                {"subindex_id": "", "title": "网页代理"},
                {"subindex_id": "", "title": "站点结构"},
            ],
        }

    async def revise_subindex(self, title, summary, documents):
        self.revisions.append((title, [d.document_id for d in documents]))
        if self.fail:
            raise RuntimeError("model unavailable")
        return {
            "title": "模型不应改名",
            "summary": title + ":" + ",".join(d.summary for d in documents),
        }


@pytest.mark.asyncio
async def test_upload_links_multiple_topics_with_short_name_and_stable_ids(tmp_path):
    client = Client()
    await CatalogService(tmp_path, client).upsert(
        document(), DocumentRecap(summary="站点知识辅助导航")
    )
    store = CatalogMarkdownStore(tmp_path)
    catalog = store.load()
    assert set(catalog) == {"网页代理", "站点结构"}
    assert len(client.revisions) == 2
    for topic in catalog.values():
        assert topic.documents["doc"].name == "WASP 导航研究"
        assert topic.title in topic.summary
        text = (store.subindexes_dir / f"{topic.subindex_id}.md").read_text()
        assert "[WASP 导航研究](../documents/doc.md)" in text
    assert all(item["status"] == "ready" for item in store.read_state()["topics"].values())


@pytest.mark.asyncio
async def test_reindex_preserves_manual_memberships_and_detachment(tmp_path):
    client = Client()
    service = CatalogService(tmp_path, client)
    await service.upsert(document(), DocumentRecap(summary="first"))
    store = CatalogMarkdownStore(tmp_path)
    state = store.read_state()
    state["manual_documents"] = ["doc"]
    catalog = store.load()
    catalog["站点结构"].documents.pop("doc")
    store.mark_pending(catalog, {"站点结构"}, state)
    store.write(catalog)
    store.write_state(state)
    await service.upsert(document(), DocumentRecap(summary="new"))
    assert client.classifications == 1
    assert set(store.load()) == {"网页代理"}
    assert store.load()["网页代理"].documents["doc"].summary == "new"
    store.write({})
    await service.upsert(document(), DocumentRecap(summary="newest"))
    assert store.load() == {}
    assert client.classifications == 1
    assert store.read_state()["display_names"]["doc"] == "WASP 导航研究"


@pytest.mark.asyncio
async def test_stale_recap_cannot_overwrite_new_membership(tmp_path):
    store = CatalogMarkdownStore(tmp_path)
    doc = CatalogDocument("one", "one", "old", 5)
    catalog = {"topic": Subindex("topic", "Topic", "previous", {"one": doc})}
    state = store.read_state()
    store.mark_pending(catalog, {"topic"}, state)
    store.write(catalog)
    store.write_state(state)
    entered, release = asyncio.Event(), asyncio.Event()

    class Delayed(Client):
        async def revise_subindex(self, title, summary, documents):
            self.revisions.append([d.document_id for d in documents])
            if len(self.revisions) == 1:
                entered.set()
                await release.wait()
            return {"title": title, "summary": ",".join(d.document_id for d in documents)}

    client = Delayed()
    job = asyncio.create_task(CatalogService(tmp_path, client).refresh_pending())
    await asyncio.wait_for(entered.wait(), 2)
    current = store.load()
    current["topic"].documents["two"] = CatalogDocument("two", "two", "new", 5)
    state = store.read_state()
    store.mark_pending(current, {"topic"}, state)
    store.write(current)
    store.write_state(state)
    release.set()
    await asyncio.wait_for(job, 2)
    assert client.revisions == [["one"], ["one", "two"]]
    assert store.load()["topic"].summary == "one,two"
    assert store.read_state()["topics"]["topic"]["status"] == "ready"


@pytest.mark.asyncio
async def test_failed_recap_preserves_previous_and_can_retry(tmp_path):
    client = Client()
    service = CatalogService(tmp_path, client)
    await service.upsert(document(), DocumentRecap(summary="first"))
    store = CatalogMarkdownStore(tmp_path)
    old = store.load()["网页代理"].summary
    client.fail = True
    await service.upsert(document(), DocumentRecap(summary="updated"))
    assert store.load()["网页代理"].summary == old
    assert store.read_state()["topics"]["网页代理"]["status"] == "failed"
    client.fail = False
    await service.refresh_pending(retry_failed=True)
    assert "updated" in store.load()["网页代理"].summary
    assert all(item["status"] == "ready" for item in store.read_state()["topics"].values())


@pytest.mark.asyncio
async def test_concurrent_uploads_keep_both_documents(tmp_path):
    client = Client()
    await asyncio.gather(
        *(
            CatalogService(tmp_path, client).upsert(document(name), DocumentRecap(summary=name))
            for name in ["one", "two"]
        )
    )
    for topic in CatalogMarkdownStore(tmp_path).load().values():
        assert set(topic.documents) == {"one", "two"}
        assert "one" in topic.summary and "two" in topic.summary


@pytest.mark.asyncio
async def test_manual_edit_wins_over_inflight_classification(tmp_path):
    client = Client()
    await CatalogService(tmp_path, client).upsert(document(), DocumentRecap(summary="initial"))
    store = CatalogMarkdownStore(tmp_path)
    entered, release = asyncio.Event(), asyncio.Event()

    class Classifying(Client):
        async def classify_document(self, doc, existing):
            entered.set()
            await release.wait()
            return await super().classify_document(doc, existing)

    job = asyncio.create_task(
        CatalogService(tmp_path, Classifying()).upsert(
            document(), DocumentRecap(summary="new version")
        )
    )
    await asyncio.wait_for(entered.wait(), 2)
    catalog = store.load()
    catalog["站点结构"].documents.pop("doc")
    state = store.read_state()
    state["manual_documents"] = ["doc"]
    store.mark_pending(catalog, {"站点结构"}, state)
    store.write(catalog)
    store.write_state(state)
    release.set()
    await asyncio.wait_for(job, 2)
    assert set(store.load()) == {"网页代理"}
    assert store.load()["网页代理"].documents["doc"].summary == "new version"


@pytest.mark.asyncio
async def test_background_shutdown_and_restart_resume_pending_recaps(tmp_path, monkeypatch):
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "web"))
    from api import topic_recap_jobs as jobs

    from searchos.local.library import LocalLibraryService

    library = LocalLibraryService(tmp_path).create_library("test")
    root = Path(library.index_root)
    store = CatalogMarkdownStore(root)
    topic = Subindex("topic", "Topic", "old", {"doc": CatalogDocument("doc", "short", "new", 1)})
    catalog = {"topic": topic}
    state = store.read_state()
    store.mark_pending(catalog, {"topic"}, state)
    store.write(catalog)
    store.write_state(state)
    entered = asyncio.Event()

    class Blocking(Client):
        async def revise_subindex(self, *args):
            entered.set()
            await asyncio.Event().wait()

    monkeypatch.setattr(jobs, "ModelCatalogClient", Blocking)
    jobs.schedule_topic_recaps(root)
    await asyncio.wait_for(entered.wait(), 2)
    await jobs.stop_topic_recaps()
    assert store.read_state()["topics"]["topic"]["status"] == "pending"
    monkeypatch.setattr(jobs, "LOCAL_DATA_ROOT", str(tmp_path))
    client = Client()
    monkeypatch.setattr(jobs, "ModelCatalogClient", lambda: client)
    jobs.resume_topic_recaps()
    jobs.schedule_topic_recaps(root)  # duplicate triggers coalesce at the lock
    await asyncio.wait_for(asyncio.gather(*list(jobs._tasks.values())), 3)
    assert len(client.revisions) == 1
    assert store.read_state()["topics"]["topic"]["status"] == "ready"


@pytest.mark.asyncio
async def test_manual_move_api_refreshes_both_topics_and_keeps_short_label(tmp_path, monkeypatch):
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "web"))
    from api import topic_recap_jobs
    from api.routes import local_search

    from searchos.local.library import LocalLibraryService

    service = LocalLibraryService(tmp_path / "knowledge_base")
    library = service.create_library("test")
    ids = []
    for name in ["long_original_name", "second"]:
        path = tmp_path / f"{name}.txt"
        path.write_text("Original document body")
        result = await service.index_uploaded_file(library.library_id, path, path.name)
        ids.append(result["document_id"])
    root = Path(library.index_root)
    store = CatalogMarkdownStore(root)
    first = CatalogDocument(ids[0], "简短引用", "first summary", 10)
    second = CatalogDocument(ids[1], "第二篇", "second summary", 10)
    catalog = {
        "A": Subindex("A", "A", "old A", {ids[0]: first, ids[1]: second}),
        "B": Subindex("B", "B", "old B", {ids[1]: second}),
    }
    store.write(catalog)
    scheduled = []
    monkeypatch.setattr(local_search, "_service", lambda: service)
    monkeypatch.setattr(
        topic_recap_jobs, "schedule_topic_recaps", lambda root: scheduled.append(root)
    )
    graph = await local_search.set_document_topics(
        library.library_id, ids[0], local_search.DocumentTopicsRequest(subindex_ids=["B"])
    )
    assert scheduled == [root]
    assert {n["recap_status"] for n in graph["nodes"] if n["node_type"] == "subindex"} == {
        "pending"
    }
    node = next(n for n in graph["nodes"] if n.get("document_id") == ids[0])
    assert node["label"] == "简短引用"
    assert node["original_name"] == "long_original_name.txt"
    assert ids[0] not in store.load()["A"].documents
    assert ids[0] in store.load()["B"].documents
    assert ids[0] in store.read_state()["manual_documents"]
    client = Client()
    client.fail = True
    await CatalogService(root, client).refresh_pending()
    assert store.load()["A"].summary == "old A"
    graph = await local_search.retry_topic_recaps(library.library_id)
    assert {n["recap_status"] for n in graph["nodes"] if n["node_type"] == "subindex"} == {
        "pending"
    }
    client.fail = False
    client.revisions.clear()
    await CatalogService(root, client).refresh_pending()
    assert sorted(client.revisions) == [("A", [ids[1]]), ("B", sorted(ids))]
    assert service.original_path(library.library_id, ids[0]).is_file()
