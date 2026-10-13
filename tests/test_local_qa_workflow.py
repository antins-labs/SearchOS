"""Selected-document QA must execute the existing Local Search Agent and native tools."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field

from searchos.harness.middleware.context.utils.messages import has_orphan_tool_message
from searchos.local.library import LocalLibraryService
from searchos.local.reader.references import build_ref_id
from searchos.local.reader.tools import local_catalog, local_open, reset_local_browser


@pytest.fixture(autouse=True)
def iterative_reading_path(monkeypatch):
    # These cases exercise the fallback agent loop; prefill is covered by WebUI tests.
    from searchos.agents.local_search import qa
    monkeypatch.setattr(qa, "_PREFILL_MAX_TOKENS", 0)


class ScriptedLocalModel(BaseChatModel):
    replies: list[AIMessage] = Field(default_factory=list)
    seen: list[Any] = Field(default_factory=list)
    toolsets: list[set[str]] = Field(default_factory=list)
    bound_toolsets: list[set[str]] = Field(default_factory=list)

    @property
    def _llm_type(self):
        return "scripted-local-agent"

    def bind_tools(self, tools, **kwargs):
        self.toolsets.append({getattr(tool, "name", "") for tool in tools})
        return self.bind(_tool_names=self.toolsets[-1])

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.seen.append(messages)
        self.bound_toolsets.append(set(kwargs.get("_tool_names", ())))
        if not self.replies:
            raise AssertionError("Agent performed an unexpected extra model call")
        return ChatResult(generations=[ChatGeneration(message=self.replies.pop(0))])

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
        return self._generate(messages, stop, run_manager, **kwargs)


def call(name, args, index=1):
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": f"call_{index}"}])


async def source(
    tmp_path, content="# 基本信息\n培养目标。\n## 课程表\n数学 4 学分；计算机 3 学分。"
):
    service = LocalLibraryService(tmp_path / "data")
    library = service.create_library("课程资料")
    incoming = tmp_path / "incoming"
    incoming.write_text(content, encoding="utf-8")
    document = await service.index_uploaded_file(library.library_id, incoming, "courses.md")
    verified = service._verified_blocks(library.library_id, [document["document_id"]])
    refs = [
        build_ref_id(
            library_id=library.library_id,
            document_id=record.document_id,
            source_revision=record.source_revision,
            locators=list(block.source_locators),
        )
        for record, block in verified
    ]
    return service, library, document["document_id"], verified, refs


@pytest.mark.asyncio
async def test_selected_agent_reads_later_course_section_before_final_answer(tmp_path):
    service, library, document_id, verified, refs = await source(tmp_path)
    model = ScriptedLocalModel(
        replies=[
            call("local_catalog", {"path": f"documents/{document_id}.md"}),
            call("local_open", {"ref_id": refs[0]}, 2),
            call("local_find", {"ref_id": refs[1], "pattern": ["数学", "计算机"]}, 3),
            call("local_open", {"ref_id": refs[1]}, 4),
            AIMessage(content=f"课程包括数学（4 学分）和计算机（3 学分）。[课程表]({refs[1]})"),
        ]
    )
    tools, reads = [], []
    result = await service.answer(
        library.library_id,
        [document_id],
        "所有的课都给我梳理下",
        model=model,
        on_tool=lambda name, args, output: tools.append(name),
        on_read=reads.append,
    )
    assert tools == ["local_catalog", "local_open", "local_find", "local_open"]
    assert model.toolsets and all(
        names <= {"local_catalog", "local_open", "local_find", "local_answer"} for names in model.toolsets
    )
    assert "数学 4 学分" in reads[-1]["text"]
    assert "计算机（3 学分）" in result.answer
    assert result.model_calls == 5
    assert result.read_observations[-1]["ref_id"] in result.answer
    assert result.read_observations[-1]["generation"] == verified[-1][0].generation
    assert len(result.citations) == 1
    assert result.citation_status == "source_bound_not_grounded"
    assert any(
        isinstance(message, ToolMessage) and "数学" in str(message.content)
        for message in model.seen[-1]
    )


@pytest.mark.asyncio
async def test_library_scope_searches_catalog_before_reading_relevant_document(tmp_path):
    service, library, _, _, refs = await source(tmp_path)
    model = ScriptedLocalModel(replies=[
        call("local_catalog", {"query": "计算机"}),
        call("local_open", {"ref_id": refs[-1]}, 2),
        AIMessage(content=f"计算机课程为 3 学分。[课程表]({refs[-1]})"),
    ])
    tools = []

    result = await service.answer(
        library.library_id,
        [],
        "计算机课程多少学分？",
        model=model,
        on_tool=lambda name, args, output: tools.append(name),
    )

    assert tools == ["local_catalog", "local_open"]
    assert "3 学分" in result.answer
    assert len(result.read_observations) == 1
    assert any("整个当前知识库" in str(message.content) for message in model.seen[0])


@pytest.mark.asyncio
async def test_no_source_answer_does_not_end_agent_before_reading(tmp_path):
    service, library, document_id, _, refs = await source(tmp_path)
    model = ScriptedLocalModel(
        replies=[
            AIMessage(content="目前未读取课程表，是否需要继续读取？"),
            call("local_open", {"ref_id": refs[-1]}, 2),
            AIMessage(content=f"数学 4 学分，计算机 3 学分。[课程表]({refs[-1]})"),
        ]
    )
    result = await service.answer(library.library_id, [document_id], "整理全部课程", model=model)
    assert result.model_calls == 3
    assert "是否需要" not in result.answer
    assert "数学" in result.answer
    assert len(result.read_observations) == 1


@pytest.mark.asyncio
async def test_selected_scope_blocks_other_documents_and_global_catalog(tmp_path):
    service, library, doc, verified, refs = await source(tmp_path)
    incoming = tmp_path / "second"
    incoming.write_text("# 隐藏文件\n未选中资料。", encoding="utf-8")
    other = await service.index_uploaded_file(library.library_id, incoming, "hidden.md")
    other_record, other_block = service._verified_blocks(
        library.library_id, [other["document_id"]]
    )[0]
    other_ref = build_ref_id(
        library_id=library.library_id,
        document_id=other_record.document_id,
        source_revision=other_record.source_revision,
        locators=list(other_block.source_locators),
    )
    record = verified[0][0]
    reset_local_browser(
        library.index_root,
        source_roots=[Path(record.source_path).parent],
        selected_documents={doc: (record.source_revision, record.generation)},
    )
    root = await local_catalog.ainvoke({})
    assert doc in root
    assert other["document_id"] not in root and "hidden.md" not in root
    assert "范围" in await local_catalog.ainvoke({"path": f"documents/{other['document_id']}.md"})
    assert "范围" in await local_catalog.ainvoke({"path": "subindexes/any.md", "query": "hidden"})
    assert "范围" in await local_open.ainvoke({"ref_id": other_ref})
    assert "[LOCAL_SOURCE]" in await local_open.ainvoke({"ref_id": refs[0]})
    reset_local_browser(library.index_root)


@pytest.mark.asyncio
async def test_native_reading_continues_beyond_two_windows(tmp_path):
    service, library, doc, _, refs = await source(tmp_path, "# 课程\n" + "课程记录。" * 2000)
    model = ScriptedLocalModel(
        replies=[
            call("local_open", {"ref_id": refs[0], "loc": offset, "max_chars": 1000}, i)
            for i, offset in enumerate((0, 1000, 2000, 3000), 1)
        ]
        + [AIMessage(content=f"课程整理结果。[来源]({refs[0]})")]
    )
    result = await service.answer(library.library_id, [doc], "梳理课程", model=model)
    assert len(result.read_observations) == 4
    assert result.model_calls == 5
    assert result.reading_stop_reason == "answered"
    assert [item["range"]["start"] for item in result.read_observations] == [0, 1000, 2000, 3000]


@pytest.mark.asyncio
async def test_native_source_can_be_reread_and_scope_is_restored(tmp_path):
    from searchos.local.reader.tools import _state

    service, library, doc, _, refs = await source(tmp_path)
    original = reset_local_browser(tmp_path / "previous-library")
    model = ScriptedLocalModel(replies=[
        call("local_open", {"ref_id": refs[0]}),
        call("local_open", {"ref_id": refs[0]}, 2),
        AIMessage(content=f"培养目标说明。[来源]({refs[0]})"),
    ])
    result = await service.answer(library.library_id, [doc], "说明培养目标", model=model)
    assert len(result.read_observations) == 2
    assert result.tool_counts["local_open"] == 2
    assert any(
        isinstance(message, ToolMessage) and "[LOCAL_SOURCE]" in str(message.content)
        for message in model.seen[-1]
    )
    assert _state() is original


@pytest.mark.asyncio
async def test_reading_exceeds_former_model_token_and_character_limits(tmp_path):
    service, library, doc, _, refs = await source(tmp_path, "# 课程\n" + "课程记录。" * 3000)
    model = ScriptedLocalModel(replies=[
        call("local_open", {"ref_id": refs[0], "max_chars": 8000}, i)
        for i in range(18)
    ] + [AIMessage(content=f"已整理课程记录。[来源]({refs[0]})")])
    result = await service.answer(library.library_id, [doc], "解读这份文件", model=model)
    assert result.model_calls == 19
    assert result.input_tokens_estimate > 200_000
    assert sum(len(item["text"]) for item in result.read_observations) > 120_000
    assert result.reading_stop_reason == "answered"
    assert result.citation_count == 1


@pytest.mark.asyncio
async def test_shared_context_control_trims_history_without_ending_reading(tmp_path, monkeypatch):
    from searchos.harness.middleware.context.dynamic_trim_middleware import DynamicTrimMiddleware

    monkeypatch.setattr(DynamicTrimMiddleware, "_effective_max_tokens", lambda *args: 6000)
    service, library, doc, _, refs = await source(tmp_path)
    first = call("local_open", {"ref_id": refs[0]})
    first.content = "过期规划。" * 6000
    model = ScriptedLocalModel(replies=[
        first,
        call("local_open", {"ref_id": refs[-1]}, 2),
        AIMessage(content=f"数学 4 学分，计算机 3 学分。[课程表]({refs[-1]})"),
    ])
    result = await service.answer(library.library_id, [doc], "整理全部课程", model=model)
    assert result.model_calls == 3
    assert len(result.read_observations) == 2
    assert result.reading_stop_reason == "answered"
    final_context = "\n".join(str(m.content) for m in model.seen[-1])
    assert "整理全部课程" in final_context
    assert "数学 4 学分" in final_context
    assert "过期规划" not in final_context
    assert not has_orphan_tool_message(model.seen[-1])


@pytest.mark.asyncio
async def test_parallel_tools_share_budget_and_agent_answers_in_same_graph(tmp_path):
    from searchos.agents.local_search.qa import QABudget, run_document_qa

    _, library, _, verified, refs = await source(tmp_path)
    batch = AIMessage(content="", tool_calls=[
        {"name": "local_open", "args": {"ref_id": ref}, "id": f"read_{i}"}
        for i, ref in enumerate(refs)
    ])
    model = ScriptedLocalModel(replies=[batch, AIMessage(content=f"培养目标说明。[来源]({refs[0]})")])
    calls = []
    result = await run_document_qa(
        index_root=library.index_root, records=[verified[0][0]], query="解读文件",
        model=model, budget=QABudget(tool_calls=1), on_tool=lambda *args: calls.append(args),
    )
    assert result.model_calls == 2
    assert result.tool_counts == {"local_open": 1}
    assert len(calls) == len(result.observations) == 1
    assert result.stop_reason == "budget"
    assert model.bound_toolsets[-1] == {"local_answer"}
    assert any(isinstance(m, ToolMessage) and "[LOCAL_SOURCE]" in str(m.content) for m in model.seen[-1])
    assert any(isinstance(m, ToolMessage) and "预算已用完" in str(m.content) for m in model.seen[-1])
    assert "培养目标说明" in result.answer


@pytest.mark.asyncio
async def test_empty_budget_answer_is_not_published_as_success(tmp_path):
    from searchos.agents.local_search.qa import QABudget, run_document_qa

    _, library, _, verified, refs = await source(tmp_path)
    model = ScriptedLocalModel(replies=[call("local_open", {"ref_id": refs[-1]}), AIMessage(content="")])
    with pytest.raises(RuntimeError, match="未返回最终答案"):
        await run_document_qa(
            index_root=library.index_root, records=[verified[0][0]], query="解读文件",
            model=model, budget=QABudget(tool_calls=1),
        )


@pytest.mark.asyncio
async def test_all_budgeted_tool_rounds_fit_the_agent_graph(tmp_path):
    from searchos.agents.local_search.qa import QABudget, run_document_qa

    _, library, _, verified, refs = await source(tmp_path)
    budget = QABudget()
    model = ScriptedLocalModel(replies=[
        call("local_open", {"ref_id": refs[-1]}, i)
        for i in range(budget.tool_calls)
    ] + [AIMessage(content=f"课程整理完毕。[来源]({refs[-1]})")])
    result = await run_document_qa(
        index_root=library.index_root, records=[verified[0][0]], query="整理课程",
        model=model, budget=budget,
    )
    assert result.tool_counts["local_open"] == budget.tool_calls
    assert result.model_calls == budget.tool_calls + 1
    assert model.bound_toolsets[-1] == {"local_answer"}
    assert "课程整理完毕" in result.answer


@pytest.mark.asyncio
async def test_final_answer_tool_cannot_skip_source_reading(tmp_path):
    from searchos.agents.local_search.qa import run_document_qa

    _, library, _, verified, refs = await source(tmp_path)
    deltas = []
    model = ScriptedLocalModel(replies=[
        call("local_answer", {"answer": "尚无原文的过早回答"}),
        call("local_open", {"ref_id": refs[-1]}, 2),
        call("local_answer", {"answer": f"课程说明。[来源]({refs[-1]})"}, 3),
    ])
    result = await run_document_qa(index_root=library.index_root, records=[verified[0][0]],
                                    query="整理课程", model=model, on_delta=deltas.append)
    assert len(result.observations) == 1
    assert "过早回答" not in "".join(deltas)
    assert "".join(deltas) == result.answer
