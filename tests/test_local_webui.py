"""WebUI Local upload, source scope, answer, and citation regressions."""

# ruff: noqa: E402, I001

from __future__ import annotations

import sys
import asyncio
import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field

_REPO = Path(__file__).resolve().parent.parent
for path in (str(_REPO), str(_REPO / "web")):
    if path not in sys.path:
        sys.path.insert(0, path)

from api.routes import search
from searchos.local.index.catalog import CatalogMarkdownStore, Subindex
from searchos.local.library import LocalLibraryService
from searchos.local.pipeline import DocumentRecapPipeline


class _FakeModel(BaseChatModel):
    response_content: str = "项目代号是蓝鲸。 [资料 1 · L1-2](citation:1)"
    captured: list = Field(default_factory=list)
    rounds: list = Field(default_factory=list)

    @property
    def _llm_type(self):
        return "local-test"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.captured.extend(messages)
        self.rounds.append(messages)
        reads = [
            m for m in messages if isinstance(m, ToolMessage) and "[LOCAL_SOURCE]" in str(m.content)
        ]
        if reads:
            content = self.response_content or str(reads[-1].content).split("\n\n", 1)[-1]
            message = AIMessage(content=content)
        else:
            catalogs = [m for m in messages if isinstance(m, ToolMessage)]
            if catalogs:
                ref = re.search(r'ref_id="([^"\n]+)"', str(catalogs[-1].content)).group(1)
                name, args = "local_open", {"ref_id": ref}
            else:
                path = re.search(r'catalog_path="([^"\n]+)"', str(messages[-1].content)).group(1)
                name, args = "local_catalog", {"path": path}
            message = AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": name}])
        return ChatResult(generations=[ChatGeneration(message=message)])

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
        return self._generate(messages, stop, run_manager, **kwargs)


class _FakeRecapClient:
    async def summarize_segments(self, segments):
        return {
            "sections": [
                {
                    "title": segment.title,
                    "summary": "概括这一部分的内容。",
                    "segment_ids": [segment.id],
                }
                for segment in segments
            ]
        }

    async def summarize_segment(self, segment):
        return {"title": segment.title, "summary": "概括这一部分的内容。"}

    async def summarize_document(self, _sections):
        return "文档介绍项目代号和范围。"


class _FakeCatalogClient:
    async def classify_document(self, _document, existing):
        if existing:
            current = existing[0]
            return {"subindexes": [{"subindex_id": current.subindex_id, "title": current.title}]}
        return {"subindexes": [{"subindex_id": "", "title": "项目资料"}]}

    async def revise_subindex(self, title, summary, documents):
        return {
            "title": title,
            "summary": f"{title}包含 {len(documents)} 份文件。",
        }


def test_multiple_libraries_have_isolated_index_trees_and_stable_rename(tmp_path):
    service = LocalLibraryService(tmp_path / "knowledge_base")
    first = service.create_library("课程资料")
    second = service.create_library("论文资料")

    assert first.library_id != second.library_id
    for library in (first, second):
        root = Path(library.index_root)
        assert root == service.indexes_root / library.library_id
        assert (root / "INDEX.md").is_file()
        assert (root / "subindexes").is_dir()
        assert (root / "documents").is_dir()

    renamed = service.rename_library(first.library_id, "信息智能体课程")

    assert renamed.library_id == first.library_id
    assert renamed.index_root == first.index_root
    assert renamed.name == "信息智能体课程"
    assert service.get_library(second.library_id).name == "论文资料"
    assert service.library_graph(first.library_id)["name"] == "信息智能体课程"
    with pytest.raises(ValueError, match="名称不能为空"):
        service.rename_library(first.library_id, "  ")


@pytest.mark.asyncio
async def test_rename_library_route_returns_stable_identity(tmp_path, monkeypatch):
    from api.routes import local_search

    service = LocalLibraryService(tmp_path / "knowledge_base")
    library = service.create_library("旧名称")
    monkeypatch.setattr(local_search, "_service", lambda: service)

    response = await local_search.rename_library(
        library.library_id,
        local_search.LibraryRenameRequest(name="新名称"),
    )

    assert response == {
        "library_id": library.library_id,
        "name": "新名称",
        "created_at": library.created_at,
    }


@pytest.mark.asyncio
async def test_uploaded_markdown_can_answer_and_resolve_original(tmp_path):
    service = LocalLibraryService(tmp_path / "knowledge_base")
    library = service.create_library("测试资料")
    temporary = tmp_path / "incoming"
    temporary.write_text("# 项目\n项目代号是蓝鲸。\n", encoding="utf-8")

    document = await service.index_uploaded_file(
        library.library_id,
        temporary,
        "notes.md",
    )
    result = await service.answer(
        library.library_id,
        [document["document_id"]],
        "项目代号是什么？",
        model=_FakeModel(),
    )
    citation = service.resolve_citation(result.read_observations[0]["ref_id"])

    assert document["searchable"] is True
    assert result.model_calls == 1
    assert result.tool_counts == {"local_open": 1}
    assert document["parse_status"] == "ready"
    assert document["catalog_status"] == "partial"
    assert "蓝鲸" in result.answer
    assert result.read_observations[0]["ref_id"] in result.answer
    assert citation["file_name"] == "notes.md"
    assert citation["location_label"] == "L1-2"
    assert "项目代号是蓝鲸" in citation["content"]
    assert service.original_path(library.library_id, document["document_id"]).name == "notes.md"


@pytest.mark.asyncio
async def test_citation_preview_resolves_merged_pages_and_reports_missing_pages(
    tmp_path, monkeypatch,
):
    from dataclasses import replace

    from api.routes import local_search
    from searchos.local.models import PdfRegionLocator
    from searchos.local.reader.references import build_ref_id

    service = LocalLibraryService(tmp_path / "knowledge_base")
    library = service.create_library("课程")
    incoming = tmp_path / "incoming"
    incoming.write_text("课程表", encoding="utf-8")
    document = await service.index_uploaded_file(library.library_id, incoming, "courses.txt")
    record, template = service._verified_blocks(library.library_id, [document["document_id"]])[0]
    pages = [(record, replace(template, block_id=f"p{page}", text=f"COURSE_PAGE_{page}",
                             source_locators=(PdfRegionLocator(page_start=page, page_end=page),)))
             for page in range(1, 11)]
    monkeypatch.setattr(service, "_verified_blocks", lambda *args: pages)
    monkeypatch.setattr(local_search, "_service", lambda: service)

    def ref(start, end, revision=record.source_revision):
        return build_ref_id(library_id=library.library_id, document_id=record.document_id,
                            source_revision=revision,
                            locators=[PdfRegionLocator(page_start=start, page_end=end)])

    result = await local_search.resolve_citation(
        local_search.CitationResolveRequest(ref_id=ref(7, 10)),
    )
    assert result["location_label"] == "P7-10"
    assert result["content"] == "\n\n".join(
        f"[P{page}]\nCOURSE_PAGE_{page}" for page in range(7, 11)
    )
    assert result["warnings"] == record.warnings
    single = service.resolve_citation(ref(6, 6))
    assert single["content"] == "[P6]\nCOURSE_PAGE_6"
    partial = service.resolve_citation(ref(7, 11))
    assert partial["content"] == result["content"]
    assert any("未完整覆盖" in warning for warning in partial["warnings"])
    with pytest.raises(ValueError, match="不可用"):
        service.resolve_citation(ref(12, 13))
    with pytest.raises(ValueError, match="VERSION_MISMATCH"):
        service.resolve_citation(ref(7, 10, "0" * 64))


@pytest.mark.asyncio
async def test_citation_preview_slices_a_line_subrange(tmp_path):
    from searchos.local.models import LineRangeLocator
    from searchos.local.reader.references import build_ref_id

    service = LocalLibraryService(tmp_path / "knowledge_base")
    library = service.create_library("笔记")
    incoming = tmp_path / "incoming"
    incoming.write_text("line1\nline2\nline3\nline4\n", encoding="utf-8")
    document = await service.index_uploaded_file(library.library_id, incoming, "notes.txt")
    record, _ = service._verified_blocks(library.library_id, [document["document_id"]])[0]
    ref = build_ref_id(library_id=library.library_id, document_id=record.document_id,
                       source_revision=record.source_revision,
                       locators=[LineRangeLocator(start_line=2, end_line=3)])
    assert service.resolve_citation(ref)["content"] == "line2\nline3"


@pytest.mark.asyncio
async def test_local_answer_publishes_only_bound_final_answer(tmp_path):
    service = LocalLibraryService(tmp_path / "knowledge_base")
    library = service.create_library("测试资料")
    temporary = tmp_path / "incoming"
    temporary.write_text("项目代号是蓝鲸。\n", encoding="utf-8")
    document = await service.index_uploaded_file(
        library.library_id,
        temporary,
        "notes.txt",
    )
    deltas: list[str] = []
    final_generation_started = asyncio.Event()
    release_remainder = asyncio.Event()

    class DelayedFinalModel(_FakeModel):
        async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
            result = self._generate(messages)
            if not result.generations[0].message.tool_calls:
                final_generation_started.set()
                await release_remainder.wait()
            return result

    def capture_delta(delta: str) -> None:
        deltas.append(delta)

    answer_task = asyncio.create_task(
        service.answer(
            library.library_id,
            [document["document_id"]],
            "项目代号是什么？",
            model=DelayedFinalModel(),
            on_delta=capture_delta,
        ),
    )
    await asyncio.wait_for(final_generation_started.wait(), timeout=10)
    assert deltas == []
    assert not answer_task.done()
    release_remainder.set()
    result = await answer_task

    assert deltas == [result.answer]
    assert "项目代号是蓝鲸" in result.answer
    assert result.read_observations[0]["ref_id"] in result.answer


@pytest.mark.asyncio
async def test_background_enrichment_reuses_document_and_incrementally_updates_catalog(tmp_path):
    service = LocalLibraryService(tmp_path / "knowledge_base")
    library = service.create_library("测试资料")

    async def upload(name: str, text: str):
        temporary = tmp_path / f"incoming-{name}"
        temporary.write_text(text, encoding="utf-8")
        document = await service.index_uploaded_file(library.library_id, temporary, name)
        pipeline = DocumentRecapPipeline(
            output_root=library.index_root,
            recap_client=_FakeRecapClient(),
            catalog_client=_FakeCatalogClient(),
            recap_model_name="test-recap",
            vision_model_name="test-vision",
        )
        return await service.enrich_document(
            library.library_id,
            document["document_id"],
            pipeline=pipeline,
        )

    first = await upload("a.md", "# A\n项目代号是蓝鲸。\n")
    second = await upload("b.md", "# B\n项目交付日期是十月。\n")

    assert first["recap_status"] == "ready"
    assert first["catalog_status"] == "ready"
    assert second["recap_status"] == "ready"
    assert second["catalog_status"] == "ready"
    index = Path(library.index_root) / "INDEX.md"
    subindex = next((Path(library.index_root) / "subindexes").glob("*.md"))
    assert index.is_file()
    assert "a.md" in subindex.read_text(encoding="utf-8")
    assert "b.md" in subindex.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_library_graph_exposes_catalog_and_uncatalogued_documents(tmp_path):
    service = LocalLibraryService(tmp_path / "knowledge_base")
    library = service.create_library("测试资料")

    first_source = tmp_path / "first.md"
    first_source.write_text("# A\n项目代号是蓝鲸。\n", encoding="utf-8")
    first = await service.index_uploaded_file(
        library.library_id,
        first_source,
        "a.md",
    )
    await service.enrich_document(
        library.library_id,
        first["document_id"],
        pipeline=DocumentRecapPipeline(
            output_root=library.index_root,
            recap_client=_FakeRecapClient(),
            catalog_client=_FakeCatalogClient(),
            recap_model_name="test-recap",
            vision_model_name="test-vision",
        ),
    )

    second_source = tmp_path / "second.md"
    second_source.write_text("# B\n尚未生成目录。\n", encoding="utf-8")
    second = await service.index_uploaded_file(
        library.library_id,
        second_source,
        "b.md",
    )

    graph = service.library_graph(library.library_id)
    nodes = {node["id"]: node for node in graph["nodes"]}
    root_id = f"index:{library.library_id}"
    topic = next(node for node in graph["nodes"] if node["node_type"] == "subindex")
    first_id = f"document:{first['document_id']}"
    second_id = f"document:{second['document_id']}"

    assert nodes[root_id]["label"] == "测试资料"
    assert nodes[first_id]["catalog_status"] == "ready"
    assert nodes[second_id]["catalog_status"] == "partial"
    graph_edges = {(edge["source"], edge["target"], edge["relation"]) for edge in graph["edges"]}
    assert graph_edges >= {
        (root_id, topic["id"], "contains"),
        (topic["id"], first_id, "classifies"),
        (root_id, second_id, "pending_catalog"),
    }
    assert "index_root" not in json.dumps(graph)


@pytest.mark.asyncio
async def test_document_index_maps_outline_to_lazy_bounded_segments(tmp_path):
    service = LocalLibraryService(tmp_path / "knowledge_base")
    library = service.create_library("测试资料")
    source = tmp_path / "guide.md"
    source.write_text("# 第一章\n" + ("甲" * 120) + "\n\n# 第二章\n乙。\n", encoding="utf-8")
    uploaded = await service.index_uploaded_file(
        library.library_id,
        source,
        "guide.md",
    )
    await service.enrich_document(
        library.library_id,
        uploaded["document_id"],
        pipeline=DocumentRecapPipeline(
            output_root=library.index_root,
            recap_client=_FakeRecapClient(),
            catalog_client=_FakeCatalogClient(),
            recap_model_name="test-recap",
            vision_model_name="test-vision",
        ),
    )

    index = service.document_index(library.library_id, uploaded["document_id"])
    first_segment = index["segments"][0]
    first_entry = index["outline"][0]
    chunk = service.document_segment(
        library.library_id,
        uploaded["document_id"],
        first_segment["segment_id"],
        limit=20,
    )

    assert index["summary"] == "文档介绍项目代号和范围。"
    assert first_entry["segment_ids"] == [first_segment["segment_id"]]
    assert "content" not in first_segment
    assert len(chunk["content"]) == 20
    assert chunk["next_offset"] == 20
    assert chunk["total_characters"] > 20


@pytest.mark.asyncio
async def test_manual_topic_relationship_edit_moves_and_detaches_document(tmp_path):
    service = LocalLibraryService(tmp_path / "knowledge_base")
    library = service.create_library("测试资料")
    source = tmp_path / "guide.md"
    source.write_text("# 项目\n项目代号是蓝鲸。\n", encoding="utf-8")
    uploaded = await service.index_uploaded_file(
        library.library_id,
        source,
        "guide.md",
    )
    enriched = await service.enrich_document(
        library.library_id,
        uploaded["document_id"],
        pipeline=DocumentRecapPipeline(
            output_root=library.index_root,
            recap_client=_FakeRecapClient(),
            catalog_client=_FakeCatalogClient(),
            recap_model_name="test-recap",
            vision_model_name="test-vision",
        ),
    )
    root = Path(library.index_root)
    store = CatalogMarkdownStore(root)
    catalog = store.load()
    original_id = next(iter(catalog))
    catalog["其他资料"] = Subindex(
        subindex_id="其他资料",
        title="其他资料",
        summary="其他项目资料。",
    )
    catalog["其他资料"].documents[enriched["document_id"]] = catalog[original_id].documents[
        enriched["document_id"]
    ]
    store.write(catalog)

    moved = service.set_document_topics(
        library.library_id,
        enriched["document_id"],
        ["其他资料"],
    )
    moved_edges = {(edge["source"], edge["target"], edge["relation"]) for edge in moved["edges"]}
    document_node = f"document:{enriched['document_id']}"
    assert ("subindex:其他资料", document_node, "classifies") in moved_edges
    assert (f"subindex:{original_id}", document_node, "classifies") not in moved_edges

    detached = service.set_document_topics(
        library.library_id,
        enriched["document_id"],
        [],
    )
    assert any(
        edge["target"] == document_node and edge["relation"] == "pending_catalog"
        for edge in detached["edges"]
    )
    current = next(
        item
        for item in service.list_documents(library.library_id)
        if item["document_id"] == enriched["document_id"]
    )
    assert current["catalog_status"] == "partial"


@pytest.mark.asyncio
async def test_local_answer_drops_model_fabricated_local_reference(tmp_path):
    service = LocalLibraryService(tmp_path / "knowledge_base")
    library = service.create_library("测试资料")
    temporary = tmp_path / "incoming"
    temporary.write_text("本地事实。\n", encoding="utf-8")
    document = await service.index_uploaded_file(library.library_id, temporary, "notes.txt")

    result = await service.answer(
        library.library_id,
        [document["document_id"]],
        "有什么事实？",
        model=_FakeModel(response_content="伪造 [引用](local://other/doc?rev=bad#bad)"),
    )

    assert "local://other" not in result.answer
    assert result.read_observations[0]["ref_id"] not in result.answer
    assert result.citation_count == 0
    assert result.citation_status == "missing"


@pytest.mark.asyncio
async def test_local_answer_maps_numbered_citation_back_to_canonical_source(tmp_path):
    service = LocalLibraryService(tmp_path / "knowledge_base")
    library = service.create_library("测试资料")
    temporary = tmp_path / "incoming"
    temporary.write_text("本地事实。\n", encoding="utf-8")
    document = await service.index_uploaded_file(library.library_id, temporary, "notes.txt")

    result = await service.answer(
        library.library_id,
        [document["document_id"]],
        "有什么事实？",
        model=_FakeModel(response_content="本地事实。 [资料 1 · L1](local://rewritten/by-model)"),
    )

    assert "invalid-local-reference" not in result.answer
    assert f"[资料 1 · L1]({result.read_observations[0]['ref_id']})" in result.answer


@pytest.mark.asyncio
async def test_local_search_request_never_initializes_web_provider(monkeypatch):
    launched = {}

    async def fake_launch(**kwargs):
        launched.update(kwargs)
        return {"session_id": kwargs["session_id"], "status": "running"}

    def fail_provider(_name=None):
        raise AssertionError("Local mode must not initialize a Web provider")

    from api.routes import local_search

    monkeypatch.setattr(local_search, "launch_local_search", fake_launch)
    monkeypatch.setattr(search, "init_search_provider", fail_provider)
    response = await search.create_search(
        search.SearchRequest(
            query="只看本地资料",
            sources={
                "mode": "local",
                "local": {
                    "library_id": "lib_test",
                    "selection": "documents",
                    "document_ids": ["doc_a"],
                    "model_access": True,
                },
            },
        )
    )

    assert response["status"] == "running"
    assert launched["library_id"] == "lib_test"
    assert launched["document_ids"] == ["doc_a"]


@pytest.mark.asyncio
async def test_local_library_scope_launches_without_selected_documents(monkeypatch):
    launched = {}

    async def fake_launch(**kwargs):
        launched.update(kwargs)
        return {"session_id": kwargs["session_id"], "status": "running"}

    from api.routes import local_search

    monkeypatch.setattr(local_search, "launch_local_search", fake_launch)
    response = await search.create_search(search.SearchRequest(
        query="从知识库找出相关资料",
        sources={
            "mode": "local",
            "local": {
                "library_id": "lib_test",
                "selection": "library",
                "document_ids": [],
                "model_access": True,
            },
        },
    ))

    assert response["status"] == "running"
    assert launched["library_id"] == "lib_test"
    assert launched["selection"] == "library"
    assert launched["document_ids"] == []


@pytest.mark.asyncio
async def test_local_follow_up_reuses_the_completed_session(monkeypatch):
    launched = {}

    async def fake_launch(**kwargs):
        launched.update(kwargs)
        return {"session_id": kwargs["session_id"], "status": "running"}

    from api.routes import local_search

    monkeypatch.setattr(local_search, "launch_local_search", fake_launch)
    response = await search.create_search(
        search.SearchRequest(
            query="继续比较",
            follow_up_to="local_session",
            history=[{"query": "第一问", "answer": "第一答"}],
            sources={
                "mode": "local",
                "local": {
                    "library_id": "lib_test",
                    "selection": "documents",
                    "document_ids": ["doc_b"],
                    "model_access": True,
                },
            },
        )
    )

    assert response["session_id"] == "local_session"
    assert launched["session_id"] == "local_session"
    assert launched["document_ids"] == ["doc_b"]
    # No persisted source scope: retain the question but do not import an
    # unverifiable answer from another mode or document selection.
    assert launched["history"] == [{"query": "第一问", "answer": ""}]


@pytest.mark.asyncio
async def test_web_mode_rejects_hidden_local_scope():
    with pytest.raises(HTTPException) as raised:
        await search.create_search(
            search.SearchRequest(
                query="网页问题",
                sources={
                    "mode": "web",
                    "local": {
                        "library_id": "lib_test",
                        "document_ids": ["doc_a"],
                        "model_access": True,
                    },
                },
            )
        )
    assert raised.value.status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize("stop_reason", ["answered", "budget", "timeout"])
async def test_local_agent_route_records_tools_and_isolates_follow_up_scopes(tmp_path, monkeypatch, stop_reason):
    from api.deps import sessions
    from api.routes import local_search
    from searchos.harness.telemetry.conversation_context import conversation_turns

    service = LocalLibraryService(tmp_path / "knowledge_base")
    library = service.create_library("测试资料")
    documents = []
    for name, text in (("first.md", "蓝鲸"), ("second.md", "雪豹")):
        incoming = tmp_path / name
        incoming.write_text(text, encoding="utf-8")
        documents.append(await service.index_uploaded_file(library.library_id, incoming, name))

    class FakeAnsweringService:
        async def answer(self, *args, **kwargs):
            from dataclasses import replace
            answer = await service.answer(*args, model=_FakeModel(response_content=""), **kwargs)
            return replace(answer, reading_stop_reason=stop_reason)

    root = tmp_path / "workspaces"
    monkeypatch.setattr(local_search, "WORKSPACE_ROOT", str(root))
    monkeypatch.setattr(local_search, "_service", lambda: FakeAnsweringService())
    for index, document in enumerate(documents):
        await local_search.launch_local_search(
            session_id="local_follow_up",
            query=f"第{index + 1}份是什么？",
            library_id=library.library_id,
            document_ids=[document["document_id"]],
            history=None if index == 0 else [{"query": "第1份是什么？", "answer": "蓝鲸"}],
        )
        await sessions["local_follow_up"]["task"]
        assert sessions["local_follow_up"]["status"] == "completed"
    workspace = root / "local_follow_up"
    turns = conversation_turns(workspace)
    assert len(turns) == 2
    assert "蓝鲸" in turns[0]["answer"] and "雪豹" in turns[1]["answer"]
    snapshots = [
        json.loads(path.read_text())
        for path in sorted((workspace / "turn_snapshots").glob("*.json"))
    ]
    for index, snapshot in enumerate(snapshots):
        assert snapshot["source_scope"]["document_ids"] == [documents[index]["document_id"]]
        assert {item["document_id"] for item in snapshot["read_observations"]} == {
            documents[index]["document_id"]
        }
    result = json.loads((workspace / "output" / "result.json").read_text())
    assert result["reading_stop_reason"] == stop_reason
    assert all(snapshot["reading_stop_reason"] == stop_reason for snapshot in snapshots)
    assert result["executor"] == "local_search_agent"
    assert result["evidence_count"] == 0
    assert result["tool_counts"] == {"local_open": 1}
    assert result["model_calls"] == 1
    records = [
        json.loads(line) for line in (workspace / "trajectory.jsonl").read_text().splitlines()
    ]
    assert all(record["reading_stop_reason"] == stop_reason
               for record in records if record.get("type") == "task_complete")
    steps = [record for record in records if record.get("type") == "step"]
    assert [step["action"]["name"] for step in steps] == ["local_open"] * 2
    assert any(r.get("type") == "answer_stream_delta" for r in records)
    assert sum(r.get("type") == "local_read_observed" for r in records) == 2


@pytest.mark.asyncio
async def test_local_answer_keeps_complete_recent_history_answers(tmp_path):
    service = LocalLibraryService(tmp_path / "knowledge_base")
    library = service.create_library("测试资料")
    temporary = tmp_path / "notes.md"
    temporary.write_text("# 项目\n项目代号是蓝鲸。\n", encoding="utf-8")
    document = await service.index_uploaded_file(
        library.library_id,
        temporary,
        "notes.md",
    )
    history_answer = "前文" * 500 + "HISTORY_TAIL_MARKER"
    model = _FakeModel()

    await service.answer(
        library.library_id,
        [document["document_id"]],
        "它的代号是什么？",
        history=[{"query": "上一轮问题", "answer": history_answer}],
        model=model,
    )

    context = "\n".join(str(m.content) for m in model.captured)
    assert history_answer in context
    assert "HISTORY_TAIL_MARKER" in context


@pytest.mark.asyncio
async def test_original_route_is_inline_and_uses_native_media_type(tmp_path, monkeypatch):
    from api.routes import local_search

    service = LocalLibraryService(tmp_path / "knowledge_base")
    library = service.create_library("测试资料")
    temporary = tmp_path / "incoming"
    temporary.write_text("# 项目\n原始正文。\n", encoding="utf-8")
    document = await service.index_uploaded_file(library.library_id, temporary, "notes.md")
    monkeypatch.setattr(local_search, "_service", lambda: service)

    response = await local_search.download_original(
        library.library_id,
        document["document_id"],
    )

    assert response.media_type == "text/markdown"
    assert response.headers["content-disposition"].startswith("inline;")


@pytest.mark.asyncio
async def test_background_index_job_is_durable_and_does_not_block_searchability(
    tmp_path, monkeypatch
):
    from api import local_index_jobs

    service = LocalLibraryService(tmp_path / "knowledge_base")
    library = service.create_library("测试资料")
    temporary = tmp_path / "incoming"
    temporary.write_text("# 项目\n先解析，后编目。\n", encoding="utf-8")
    document = await service.index_uploaded_file(library.library_id, temporary, "notes.md")
    release = asyncio.Event()

    async def delayed_enrichment(self, library_id, document_id, *, recap_progress=None):
        assert service.list_documents(library_id)[0]["searchable"] is True
        assert recap_progress is not None
        recap_progress(1, 3)
        await release.wait()
        recap_progress(3, 3)
        return {
            **service.list_documents(library_id)[0],
            "document_id": document_id,
            "recap_status": "ready",
            "catalog_status": "ready",
        }

    monkeypatch.setattr(LocalLibraryService, "enrich_document", delayed_enrichment)
    store = local_index_jobs.LocalIndexJobStore(tmp_path / "knowledge_base")
    job = local_index_jobs.schedule_background_index(
        document,
        library_id=library.library_id,
        store=store,
    )
    await asyncio.sleep(0)

    assert service.list_documents(library.library_id)[0]["searchable"] is True
    assert store.read(job.job_id).status == "running"
    assert store.read(job.job_id).recap_segments_completed == 1
    assert store.read(job.job_id).recap_segments_total == 3
    assert (tmp_path / "knowledge_base" / "jobs" / f"{job.job_id}.json").is_file()

    release.set()
    await local_index_jobs._tasks[job.job_id]
    assert store.read(job.job_id).status == "completed"
    assert store.read(job.job_id).recap_segments_completed == 3


@pytest.mark.asyncio
async def test_running_background_job_resumes_after_api_restart(tmp_path, monkeypatch):
    from api import local_index_jobs

    service = LocalLibraryService(tmp_path / "knowledge_base")
    library = service.create_library("测试资料")
    temporary = tmp_path / "incoming"
    temporary.write_text("# 项目\n恢复后台编目。\n", encoding="utf-8")
    document = await service.index_uploaded_file(library.library_id, temporary, "notes.md")
    store = local_index_jobs.LocalIndexJobStore(tmp_path / "knowledge_base")
    job = store.create(
        library_id=library.library_id,
        document_id=document["document_id"],
        source_revision=document["source_revision"],
        file_name=document["name"],
    )
    store.update(job.job_id, status="running", stage="recap_catalog")

    async def completed_enrichment(self, library_id, document_id, *, recap_progress=None):
        return {
            **self.list_documents(library_id)[0],
            "document_id": document_id,
            "recap_status": "ready",
            "catalog_status": "ready",
        }

    monkeypatch.setattr(LocalLibraryService, "enrich_document", completed_enrichment)
    assert local_index_jobs.resume_background_indexes(store) == 1
    await local_index_jobs._tasks[job.job_id]

    assert store.read(job.job_id).status == "completed"


@pytest.mark.asyncio
async def test_background_job_can_be_cancelled_and_retried(tmp_path, monkeypatch):
    from api import local_index_jobs

    service = LocalLibraryService(tmp_path / "knowledge_base")
    library = service.create_library("测试资料")
    temporary = tmp_path / "incoming"
    temporary.write_text("# 项目\n取消后仍可问答。\n", encoding="utf-8")
    document = await service.index_uploaded_file(library.library_id, temporary, "notes.md")
    waiting = asyncio.Event()

    async def delayed_enrichment(self, library_id, document_id, *, recap_progress=None):
        await waiting.wait()
        raise AssertionError("取消后不应继续执行")

    monkeypatch.setattr(LocalLibraryService, "enrich_document", delayed_enrichment)
    store = local_index_jobs.LocalIndexJobStore(tmp_path / "knowledge_base")
    job = local_index_jobs.schedule_background_index(
        document,
        library_id=library.library_id,
        store=store,
    )
    await asyncio.sleep(0)

    cancelled = await local_index_jobs.cancel_background_index(job.job_id, store=store)
    assert cancelled.status == "cancelled"
    assert service.list_documents(library.library_id)[0]["searchable"] is True
    assert local_index_jobs.resume_background_indexes(store) == 0

    async def completed_enrichment(self, library_id, document_id, *, recap_progress=None):
        return {
            **self.list_documents(library_id)[0],
            "document_id": document_id,
            "recap_status": "ready",
            "catalog_status": "ready",
        }

    monkeypatch.setattr(LocalLibraryService, "enrich_document", completed_enrichment)
    retried = local_index_jobs.retry_background_index(job.job_id, store=store)
    assert retried.status == "queued"
    assert retried.attempt == 2
    await local_index_jobs._tasks[job.job_id]
    assert store.read(job.job_id).status == "completed"


def test_office_preview_is_versioned_and_cached(tmp_path, monkeypatch):
    from searchos.local.reader.office_preview import OfficePreviewService

    source = tmp_path / "report.docx"
    source.write_bytes(b"office-v1")
    preview = OfficePreviewService(tmp_path / "knowledge_base")
    conversions = []

    def fake_convert(input_path, target):
        conversions.append(input_path.read_bytes())
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"%PDF-fake")

    monkeypatch.setattr(preview, "_convert", fake_convert)
    first = preview.get_or_create("lib_test", "doc_test", source)
    second = preview.get_or_create("lib_test", "doc_test", source)
    source.write_bytes(b"office-v2")
    third = preview.get_or_create("lib_test", "doc_test", source)

    assert first == second
    assert first != third
    assert conversions == [b"office-v1", b"office-v2"]


def test_office_preview_supplies_cjk_fontconfig_and_invalidates_legacy_cache(
    tmp_path,
    monkeypatch,
):
    from searchos.local.reader import office_preview
    from searchos.local.reader.office_preview import OfficePreviewService

    source = tmp_path / "slides.pptx"
    source.write_bytes(b"office-source")
    preview = OfficePreviewService(tmp_path / "knowledge_base")
    revision = office_preview._sha256(source)
    legacy = preview.root / "lib_test" / "doc_test" / revision / "original.pdf"
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_bytes(b"%PDF-legacy-without-cjk")
    captured = {}

    monkeypatch.setattr(
        office_preview,
        "resolve_soffice_executable",
        lambda _configured: "/Applications/LibreOffice.app/Contents/MacOS/soffice",
    )
    monkeypatch.setattr(
        office_preview,
        "_font_directories",
        lambda _executable: (Path("/System/Library/Fonts/Supplemental"),),
    )

    def fake_run(args, **kwargs):
        config_path = Path(kwargs["env"]["FONTCONFIG_FILE"])
        captured["fontconfig"] = config_path.read_text(encoding="utf-8")
        output_dir = Path(args[args.index("--outdir") + 1])
        (output_dir / "slides.pdf").write_bytes(b"%PDF-with-cjk")
        return SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setattr(office_preview.subprocess, "run", fake_run)
    result = preview.get_or_create("lib_test", "doc_test", source)

    assert result != legacy
    assert result.parent.name == "office-pdf-v2-fontconfig"
    assert "System/Library/Fonts/Supplemental" in captured["fontconfig"]
    assert "Arial Unicode MS" in captured["fontconfig"]
    assert legacy.read_bytes() == b"%PDF-legacy-without-cjk"


@pytest.mark.asyncio
async def test_office_preview_route_returns_inline_pdf(tmp_path, monkeypatch):
    from api.routes import local_search

    source = tmp_path / "report.docx"
    source.write_bytes(b"office")
    preview = tmp_path / "report.pdf"
    preview.write_bytes(b"%PDF-fake")

    class FakeLibraryService:
        def original_path(self, library_id, document_id):
            assert (library_id, document_id) == ("lib_test", "doc_test")
            return source

    class FakePreviewService:
        def get_or_create(self, library_id, document_id, path):
            assert (library_id, document_id, path) == ("lib_test", "doc_test", source)
            return preview

    monkeypatch.setattr(local_search, "_service", lambda: FakeLibraryService())
    monkeypatch.setattr(local_search, "_preview_service", lambda: FakePreviewService())
    response = await local_search.preview_office_original("lib_test", "doc_test")

    assert response.media_type == "application/pdf"
    assert response.headers["content-disposition"].startswith("inline;")


@pytest.mark.asyncio
async def test_prefill_reads_all_selected_text_including_long_block_tail(tmp_path):
    service = LocalLibraryService(tmp_path / "library")
    library = service.create_library("论文")
    docs = []
    for name, body in (("paper.md", "# 论文\n" + "正文资料" * 6000 + "\nPAPER_END"),
                       ("notes.md", "# 补充\nNOTES_END")):
        incoming = tmp_path / name
        incoming.write_text(body)
        docs.append(await service.index_uploaded_file(library.library_id, incoming, name))
    model = _FakeModel()
    result = await service.answer(library.library_id, [d["document_id"] for d in docs],
                                  "结合文档解读", model=model)
    assert result.model_calls == 1
    context = "\n".join(str(m.content) for m in model.rounds[0] if isinstance(m, ToolMessage))
    assert "PAPER_END" in context and "NOTES_END" in context
    assert result.tool_counts == {"local_open": 3}
    assert {o["document_id"] for o in result.read_observations} == {d["document_id"] for d in docs}
    assert result.citation_status == "source_bound_not_grounded"


@pytest.mark.asyncio
async def test_oversized_selection_falls_back_without_prefilling_a_prefix(tmp_path, monkeypatch):
    from searchos.agents.local_search import qa

    monkeypatch.setattr(qa, "_PREFILL_MAX_TOKENS", 5000)
    service = LocalLibraryService(tmp_path / "library")
    library = service.create_library("资料")
    incoming = tmp_path / "paper.md"
    incoming.write_text("# 开头\n起始段落。\n## 附录\n" + "长文内容。" * 4000)
    doc = await service.index_uploaded_file(library.library_id, incoming, "paper.md")
    model = _FakeModel()
    result = await service.answer(library.library_id, [doc["document_id"]], "查询开头", model=model)
    assert result.model_calls == 3
    assert not any(isinstance(m, ToolMessage) for m in model.rounds[0])
    assert result.tool_counts == {"local_catalog": 1, "local_open": 1}


@pytest.mark.asyncio
async def test_prefill_leaves_local_tools_available_for_further_checks(tmp_path):
    service = LocalLibraryService(tmp_path / "library")
    library = service.create_library("资料")
    incoming = tmp_path / "notes.md"
    incoming.write_text("# 数据\n项目代号是蓝鲸。")
    doc = await service.index_uploaded_file(library.library_id, incoming, "notes.md")

    class FollowupModel(_FakeModel):
        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            if not self.rounds:
                self.rounds.append(messages)
                source = next(m for m in messages if isinstance(m, ToolMessage))
                ref = source.artifact["local_source_metadata"]["ref_id"]
                return ChatResult(generations=[ChatGeneration(message=AIMessage(content="", tool_calls=[{
                    "name": "local_find", "args": {"ref_id": ref, "pattern": "蓝鲸"}, "id": "check",
                }]))])
            return super()._generate(messages, stop, run_manager, **kwargs)

    result = await service.answer(library.library_id, [doc["document_id"]], "核对项目代号", model=FollowupModel())
    assert result.model_calls == 2
    assert result.tool_counts == {"local_open": 1, "local_find": 1}
    assert result.reading_stop_reason == "answered"


@pytest.mark.asyncio
@pytest.mark.parametrize("preload", [True, False])
async def test_final_tool_streams_before_completion_and_binds_split_citations(tmp_path, monkeypatch, preload):
    from langchain_core.messages import AIMessageChunk
    from langchain_core.outputs import ChatGenerationChunk

    if not preload:
        from searchos.agents.local_search import qa
        monkeypatch.setattr(qa, "_PREFILL_MAX_TOKENS", 0)
    service = LocalLibraryService(tmp_path / "library")
    library = service.create_library("资料")
    incoming = tmp_path / "notes.md"
    incoming.write_text("# 数据\n项目代号是蓝鲸。")
    doc = await service.index_uploaded_file(library.library_id, incoming, "notes.md")
    first_visible, resume = asyncio.Event(), asyncio.Event()
    deltas = []

    class StreamingFinalModel(_FakeModel):
        async def _astream(self, messages, stop=None, run_manager=None, **kwargs):
            if not any(isinstance(m, ToolMessage) and "[LOCAL_SOURCE]" in str(m.content) for m in messages):
                message = self._generate(messages).generations[0].message
                call = message.tool_calls[0]
                yield ChatGenerationChunk(message=AIMessageChunk(content="中间规划不应进入答案", tool_call_chunks=[{
                    "name": call["name"], "args": json.dumps(call["args"]), "index": 0, "id": call["id"],
                }]))
                return
            self.rounds.append(messages)
            for i, args in enumerate(['{"answer":"项目代号是蓝鲸。', '[资料', '1]', '"}']):
                yield ChatGenerationChunk(message=AIMessageChunk(content="", tool_call_chunks=[{
                    "name": "local_answer" if i == 0 else None,
                    "id": "answer" if i == 0 else None, "index": 0, "args": args,
                }]))
                if i == 0:
                    await resume.wait()

    def emit(delta):
        deltas.append(delta)
        first_visible.set()

    task = asyncio.create_task(service.answer(library.library_id, [doc["document_id"]],
                                             "项目代号是什么", model=StreamingFinalModel(), on_delta=emit))
    try:
        await asyncio.wait_for(first_visible.wait(), 5)
        assert not task.done()
        assert "项目代号是蓝鲸" in "".join(deltas)
    finally:
        resume.set()
    answer = await asyncio.wait_for(task, 5)
    assert "".join(deltas) == answer.answer
    assert answer.model_calls == (1 if preload else 3)
    assert "中间规划" not in "".join(deltas)
    assert answer.citation_count == 1
    assert "invalid-local-reference" not in answer.answer
    assert service.resolve_citation(answer.citations[0]["ref_id"])["file_name"] == "notes.md"


@pytest.mark.asyncio
async def test_omitted_inline_citations_keep_an_explicit_original_navigation_link(tmp_path):
    service = LocalLibraryService(tmp_path / "library")
    library = service.create_library("资料")
    incoming = tmp_path / "notes.md"
    incoming.write_text("# 数据\n项目代号是蓝鲸。")
    doc = await service.index_uploaded_file(library.library_id, incoming, "notes.md")
    deltas = []
    answer = await service.answer(library.library_id, [doc["document_id"]], "解读文件",
                                  model=_FakeModel(response_content="项目代号是蓝鲸。"), on_delta=deltas.append)
    assert "已读原文入口" in answer.answer
    assert "notes.md · L1-2" in answer.answer
    assert "".join(deltas) == answer.answer
    assert answer.citation_count == 1
    assert service.resolve_citation(answer.citations[0]["ref_id"])["file_name"] == "notes.md"


def test_citation_stream_handles_character_sized_link_and_json_escape_boundaries():
    from searchos.local.library import _CitationStream

    ref = "local://lib/doc?rev=abc#loc"
    raw = f"依据[资料1]，或[原文]({ref})。裸链接 {ref}\n完成。"
    def bind(text):
        return LocalLibraryService._bind_numbered_citations(text, [ref])
    parts = []
    stream = _CitationStream(bind, parts.append)
    for character in raw:
        stream.push(character)
    stream.push("", final=True)
    assert "".join(parts) == bind(raw)
