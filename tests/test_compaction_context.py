"""压缩的持久化、交互完整性和失败原子性。"""

import asyncio
from copy import deepcopy

import pytest
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph.message import add_messages

from searchos.agents.runtime import create_search_agent_graph
from searchos.harness.middleware import CompactionContextMiddleware
from searchos.harness.middleware.context.utils.compaction import (
    count_context_tokens,
    render_history,
)


class Summarizer:
    def __init__(self, result="Goal: inspect sources. Done: read A. Next: compare B."):
        self.result = result
        self.requests = []

    async def ainvoke(self, messages):
        self.requests.append(messages)
        return AIMessage(content=self.result)


def component(model=None, **kwargs):
    return CompactionContextMiddleware(
        model or Summarizer(),
        context_window=4000,
        trigger_fraction=0.65,
        keep_recent_fraction=0.1,
        summary_fraction=0.075,
        reserve_fraction=0.05,
        **kwargs,
    )


def history():
    return [
        SystemMessage(content="Respect source evidence."),
        HumanMessage(content="Original task: compare A and B."),
        AIMessage(
            content="",
            tool_calls=[
                {"id": "a", "name": "open", "args": {"url": "https://example.org/a"}},
                {"id": "b", "name": "open", "args": {"url": "https://example.org/b"}},
            ],
        ),
        ToolMessage(content="source A " * 1000, tool_call_id="a"),
        ToolMessage(content="source B " * 1000, tool_call_id="b"),
        HumanMessage(content="Correction: only compare revenue."),
        AIMessage(content="", tool_calls=[{"id": "c", "name": "open", "args": {}}]),
        ToolMessage(content="Recent source C: revenue 42.", tool_call_id="c"),
    ]


@pytest.mark.asyncio
async def test_small_history_is_noop():
    model = Summarizer()
    assert await component(model).abefore_model({"messages": [HumanMessage("Hi")]}, None) is None
    assert not model.requests


@pytest.mark.asyncio
async def test_compaction_preserves_instructions_pairs_and_checkpoint_summary():
    model = Summarizer()
    mw = component(model)
    original = history()
    snapshot = deepcopy(original)
    update = await mw.abefore_model({"messages": original}, None)
    assert original == snapshot
    messages = add_messages(original, update["messages"])
    assert messages[0].content == "Respect source evidence."
    assert {m.content for m in messages if m.type == "human"} >= {
        "Original task: compare A and B.",
        "Correction: only compare revenue.",
    }
    assert [m.tool_call_id for m in messages if m.type == "tool"] == ["c"]
    assert messages[-2].tool_calls[0]["id"] == "c"
    assert (
        len([m for m in messages if m.additional_kwargs.get("sf_kind") == "context_compaction"])
        == 1
    )
    assert update["context_compaction"]["count"] == 1
    assert await mw.abefore_model({"messages": messages}, None) is None
    # The oversized prefix was summarized in bounded requests, including both sources.
    assert len(model.requests) > 1
    assert all("Correction: only compare revenue." in r[-1].content for r in model.requests)
    rendered = "\n".join(r[-1].content for r in model.requests)
    assert "https://example.org/a" in rendered and "source B" in rendered
    assert all(count_context_tokens(r) <= 3500 for r in model.requests)


@pytest.mark.asyncio
async def test_second_compaction_merges_old_handoff_and_new_work():
    model = Summarizer()
    mw = component(model)
    first = await mw.abefore_model({"messages": history()}, None)
    messages = add_messages([], first["messages"])
    messages += [AIMessage(content="New investigation " * 1000), HumanMessage("Continue")]
    model.requests.clear()
    second = await mw.abefore_model(
        {
            "messages": messages,
            **{
                "context_compaction": first["context_compaction"],
            },
        },
        None,
    )
    assert second["context_compaction"]["count"] == 2
    assert "Goal: inspect sources" in model.requests[0][-1].content
    assert (
        len(
            [
                m
                for m in second["messages"]
                if m.additional_kwargs.get("sf_kind") == "context_compaction"
            ]
        )
        == 1
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("result", ["", "too long " * 1000])
async def test_invalid_summary_does_not_mutate_history(result):
    messages = history()
    saved = deepcopy(messages)
    with pytest.raises(ValueError, match="empty or oversized"):
        await component(Summarizer(result)).abefore_model({"messages": messages}, None)
    assert messages == saved


@pytest.mark.asyncio
async def test_cancellation_propagates_without_mutation():
    class Cancelled(Summarizer):
        async def ainvoke(self, messages):
            raise asyncio.CancelledError()

    messages = history()
    saved = deepcopy(messages)
    with pytest.raises(asyncio.CancelledError):
        await component(Cancelled()).abefore_model({"messages": messages}, None)
    assert saved == messages


@pytest.mark.asyncio
async def test_timeout_propagates_without_mutation():
    class Slow(Summarizer):
        async def ainvoke(self, messages):
            await asyncio.sleep(1)

    messages = history()
    saved = deepcopy(messages)
    with pytest.raises(TimeoutError):
        await component(Slow(), timeout=0.01).abefore_model({"messages": messages}, None)
    assert saved == messages


@pytest.mark.asyncio
async def test_huge_latest_tool_result_is_summarized_as_complete_transaction():
    messages = history()[:5]
    update = await component().abefore_model({"messages": messages}, None)
    compacted = add_messages(messages, update["messages"])
    assert not any(m.type == "tool" or getattr(m, "tool_calls", []) for m in compacted)
    assert any(m.content == "Original task: compare A and B." for m in compacted)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "messages, error",
    [
        ([HumanMessage("x" * 8000), ToolMessage(content="orphan", tool_call_id="bad")], "orphan"),
        (history()[:4], "unfinished"),
    ],
)
async def test_rejects_incomplete_tool_transactions(messages, error):
    with pytest.raises(ValueError, match=error):
        await component().abefore_model({"messages": messages}, None)


def test_images_are_not_serialized_as_base64_and_arguments_are_counted():
    message = HumanMessage(content=[{"type": "image_url", "image_url": {"url": "data:secret"}}])
    assert "data:secret" not in render_history([message])
    assert "omitted_block_type" in render_history([message])
    small = AIMessage(content="")
    large = AIMessage(content="", tool_calls=[{"id": "t", "name": "x", "args": {"x": "z" * 1000}}])
    assert count_context_tokens([large]) > count_context_tokens([small]) + 300


class Model(FakeMessagesListChatModel):
    def bind_tools(self, tools, **kwargs):
        return self


def graph(middleware, checkpointer=None):
    return create_search_agent_graph(
        model=Model(responses=[AIMessage(content="Continue from handoff.")]),
        tools=[],
        middleware=middleware,
        checkpointer=checkpointer,
    )


@pytest.mark.asyncio
async def test_real_graph_resume_with_new_instance_and_thread_isolation():
    saver = MemorySaver()
    summary = Summarizer()
    config = {"configurable": {"thread_id": "compact"}}
    g = graph([component(summary)], saver)
    result = await g.ainvoke({"messages": history()}, config)
    assert result["context_compaction"]["count"] == 1
    assert not any(m.type == "tool" and m.tool_call_id == "a" for m in result["messages"])
    # Rebuild the graph: continuation depends on checkpoint state, not Python instance caches.
    new_summary = Summarizer()
    rebuilt = graph([component(new_summary)], saver)
    resumed = await rebuilt.ainvoke({"messages": [HumanMessage("Finish the comparison.")]}, config)
    assert resumed["context_compaction"]["count"] == 1
    assert not new_summary.requests
    other = await rebuilt.ainvoke(
        {"messages": [HumanMessage("Separate task")]},
        {"configurable": {"thread_id": "other"}},
    )
    assert not other.get("context_compaction")
    assert not any(
        m.additional_kwargs.get("sf_kind") == "context_compaction" for m in other["messages"]
    )


@pytest.mark.asyncio
async def test_not_loaded_does_not_compact():
    result = await graph([]).ainvoke(
        {"messages": history()},
        {"configurable": {"thread_id": "plain"}},
    )
    assert not result.get("context_compaction")
    assert any(m.type == "tool" and m.tool_call_id == "a" for m in result["messages"])


@pytest.mark.parametrize("window", [16000, 128000])
def test_budgets_scale_with_model_window(window):
    model = Summarizer()
    model.profile = {"max_input_tokens": window}
    mw = CompactionContextMiddleware(model)
    assert mw.context_window == window
    assert mw.trigger_tokens == int(window * 0.8)
    assert mw.keep_recent_tokens == int(window * 0.08)
    assert mw.summary_tokens == int(window * 0.02)
    assert mw.reserve_tokens == int(window * 0.08)


def test_missing_window_requires_explicit_configuration():
    with pytest.raises(ValueError, match="context_window"):
        CompactionContextMiddleware(Summarizer())
    assert CompactionContextMiddleware(Summarizer(), context_window=16000).context_window == 16000


@pytest.mark.parametrize(
    "kwargs",
    [
        {"trigger_fraction": 1},
        {"trigger_fraction": 0},
        {"trigger_fraction": float("nan")},
        {"reserve_fraction": -0.1},
        {"summary_fraction": 0},
        {"keep_recent_fraction": 0.75},
        {"context_window": 0},
        {"context_window": True},
    ],
)
def test_invalid_percentage_configuration(kwargs):
    options = {"context_window": 16000, **kwargs}
    with pytest.raises(ValueError):
        CompactionContextMiddleware(Summarizer(), **options)


@pytest.mark.asyncio
async def test_same_history_triggers_only_for_smaller_window():
    small_model, large_model = Summarizer(), Summarizer()
    small_model.profile = {"max_input_tokens": 8000}
    large_model.profile = {"max_input_tokens": 128000}
    small = CompactionContextMiddleware(small_model)
    large = CompactionContextMiddleware(large_model)
    assert await small.abefore_model({"messages": history()}, None) is not None
    assert await large.abefore_model({"messages": history()}, None) is None
    assert small_model.requests and not large_model.requests


@pytest.mark.asyncio
async def test_smaller_summary_model_gets_bounded_requests():
    model = Summarizer()
    model.profile = {"max_input_tokens": 2000}
    mw = component(model)
    await mw.abefore_model({"messages": history()}, None)
    assert all(count_context_tokens(r) <= 1600 for r in model.requests)


@pytest.mark.asyncio
async def test_oversized_handoff_gets_one_bounded_revision():
    class Revise(Summarizer):
        async def ainvoke(self, messages):
            self.requests.append(messages)
            return AIMessage(
                "too much " * 100 if len(self.requests) == 1 else "Verified A; next compare B."
            )

    model = Revise()
    mw = component(model)
    summary = await mw._summarize("read source A", "task: compare")
    assert summary == "Verified A; next compare B."
    assert len(model.requests) == 2
    assert all(count_context_tokens(req) <= mw._summary_input_budget for req in model.requests)
