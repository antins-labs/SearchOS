from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from searchos.harness.middleware.context.search_episode_middleware import (
    SearchEpisodeMiddleware,
)


@dataclass
class _Request:
    messages: list


class _Workspace:
    def __init__(self) -> None:
        self.state = SimpleNamespace(
            evidence_graph=SimpleNamespace(nodes=[]),
            coverage_map=SimpleNamespace(cells={}),
        )

    def load_state(self):
        return self.state


class _EvidenceSource:
    def __init__(self) -> None:
        self.committed_node_ids: frozenset[str] = frozenset()
        self.flushes = 0

    async def await_idle(self, timeout: float = 5.0) -> int:
        self.flushes += 1
        return 0


def _call(name: str, args: dict, call_id: str) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[{"name": name, "args": args, "id": call_id, "type": "tool_call"}],
    )


@pytest.mark.asyncio
async def test_previous_search_episode_keeps_inputs_and_drops_outputs():
    workspace = _Workspace()
    evidence = _EvidenceSource()
    middleware = SearchEpisodeMiddleware(workspace, evidence_source=evidence)
    task = HumanMessage(content="research task")
    search_1 = _call("search", {"query": "first query"}, "search-1")

    async def first_handler(_request):
        return search_1

    await middleware.awrap_model_call(_Request([task]), first_handler)

    first_episode = [
        task,
        search_1,
        ToolMessage(content="SEARCH OUTPUT SECRET", tool_call_id="search-1", name="search"),
        _call("open", {"id_or_url": "2", "loc": 256}, "open-1"),
        ToolMessage(content="PAGE OUTPUT SECRET", tool_call_id="open-1", name="open"),
    ]
    evidence.committed_node_ids = frozenset({"e_123", "e_128"})
    workspace.state.evidence_graph.nodes = [
        SimpleNamespace(id="e_123"),
        SimpleNamespace(id="e_128"),
    ]
    workspace.state.coverage_map.cells = {
        "required_documents/passport.requirement": SimpleNamespace(
            status=SimpleNamespace(value="filled"),
            supporting_evidence_ids=["e_123"],
        ),
        "required_documents/photo.requirement": SimpleNamespace(
            status=SimpleNamespace(value="filled"),
            supporting_evidence_ids=["e_128"],
        ),
    }
    search_2 = _call("search", {"query": "second query"}, "search-2")

    async def second_handler(_request):
        return search_2

    await middleware.awrap_model_call(_Request(first_episode), second_handler)

    second = first_episode + [
        search_2,
        ToolMessage(content="CURRENT OUTPUT", tool_call_id="search-2", name="search"),
    ]
    captured = []

    async def capture(request):
        captured.append(request)
        return AIMessage(content="continue")

    await middleware.awrap_model_call(_Request(second), capture)

    prompt = "\n".join(str(message.content) for message in captured[-1].messages)
    assert 'search({"query":"first query"})' in prompt
    assert 'open({"id_or_url":"2","loc":256})' in prompt
    assert "evidence_added: [e_123, e_128]" in prompt
    assert "required_documents: +2 cells" in prompt
    assert "SEARCH OUTPUT SECRET" not in prompt
    assert "PAGE OUTPUT SECRET" not in prompt
    assert "CURRENT OUTPUT" in prompt
    assert evidence.flushes == 1


@pytest.mark.asyncio
async def test_coverage_delta_ignores_sibling_agent_evidence():
    workspace = _Workspace()
    evidence = _EvidenceSource()
    middleware = SearchEpisodeMiddleware(workspace, evidence_source=evidence)

    task = HumanMessage(content="task")
    search_1 = _call("search", {"query": "first"}, "search-1")

    async def first_handler(_request):
        return search_1

    await middleware.awrap_model_call(_Request([task]), first_handler)

    first = [
        task,
        search_1,
        ToolMessage(content="result", tool_call_id="search-1", name="search"),
    ]
    evidence.committed_node_ids = frozenset({"own-evidence"})
    workspace.state.evidence_graph.nodes = [
        SimpleNamespace(id="own-evidence"),
        SimpleNamespace(id="sibling-evidence"),
    ]
    workspace.state.coverage_map.cells = {
        "table/own.value": SimpleNamespace(
            status=SimpleNamespace(value="filled"),
            supporting_evidence_ids=["own-evidence"],
        ),
        "table/sibling.value": SimpleNamespace(
            status=SimpleNamespace(value="filled"),
            supporting_evidence_ids=["sibling-evidence"],
        ),
    }
    search_2 = _call("search", {"query": "second"}, "search-2")

    async def second_handler(_request):
        return search_2

    await middleware.awrap_model_call(_Request(first), second_handler)

    second = first + [
        search_2,
        ToolMessage(
            content="result 2",
            tool_call_id="search-2",
            name="search",
        ),
    ]
    captured = []

    async def capture(request):
        captured.append(request)
        return "ok"

    await middleware.awrap_model_call(_Request(second), capture)
    prompt = "\n".join(str(message.content) for message in captured[0].messages)
    assert "table: +1 cells" in prompt
    assert "+2 cells" not in prompt


@pytest.mark.asyncio
async def test_no_completed_episode_leaves_request_unchanged():
    workspace = _Workspace()
    middleware = SearchEpisodeMiddleware(workspace)
    task = HumanMessage(content="task")
    search_1 = _call("search", {"query": "only query"}, "search-1")

    async def first_handler(_request):
        return search_1

    await middleware.awrap_model_call(_Request([task]), first_handler)
    messages = [
        task,
        search_1,
        ToolMessage(content="full result", tool_call_id="search-1", name="search"),
    ]
    captured = []

    async def handler(request):
        captured.append(request)
        return AIMessage(content="continue")

    await middleware.awrap_model_call(_Request(messages), handler)
    assert captured[0].messages == messages


@pytest.mark.asyncio
async def test_compacted_history_keeps_handoff_and_current_transaction():
    middleware = SearchEpisodeMiddleware(_Workspace())
    task = HumanMessage("task")
    first = _call("search", {"query": "first"}, "first")
    second = _call("search", {"query": "second"}, "second")

    async def one(request):
        return first

    async def two(request):
        return second

    await middleware.awrap_model_call(_Request([task]), one)
    await middleware.awrap_model_call(
        _Request(
            [
                task,
                first,
                ToolMessage("old", tool_call_id="first"),
                AIMessage("old details"),
                AIMessage("more old details"),
            ]
        ),
        two,
    )
    compacted = [
        task,
        HumanMessage(
            "HANDOFF",
            additional_kwargs={
                "sf_synthetic": True,
                "sf_kind": "context_compaction",
            },
        ),
        second,
        ToolMessage("CURRENT", tool_call_id="second"),
    ]

    async def capture(request):
        assert request.messages == compacted
        return AIMessage("done")

    await middleware.awrap_model_call(_Request(compacted), capture)


@pytest.mark.asyncio
async def test_rebuilt_episode_preserves_corrections_and_progress():
    workspace = _Workspace()
    evidence = _EvidenceSource()
    original = SearchEpisodeMiddleware(workspace, evidence_source=evidence)
    task = HumanMessage("task")
    first = _call("search", {"query": "first"}, "first")
    second = _call("search", {"query": "second"}, "second")

    async def one(request):
        return first

    async def two(request):
        return second

    await original.awrap_model_call(_Request([task]), one)
    evidence.committed_node_ids = frozenset({"own-fact"})
    correction = HumanMessage("Only compare revenue")
    history = [task, first, ToolMessage("OLD SECRET", tool_call_id="first"), correction]
    await original.awrap_model_call(_Request(history), two)
    history += [second, ToolMessage("CURRENT", tool_call_id="second")]
    rebuilt = SearchEpisodeMiddleware(workspace, evidence_source=evidence)

    async def capture(request):
        text = "\n".join(str(m.content) for m in request.messages)
        assert "OLD SECRET" not in text
        assert "own-fact" in text
        assert "CURRENT" in text
        assert correction in request.messages
        return AIMessage("done")

    await rebuilt.awrap_model_call(_Request(history), capture)


@pytest.mark.asyncio
async def test_socm_snapshot_remains_visible_on_unchanged_requests():
    from searchos.harness.middleware import SOCMContextMiddleware, TaskContext

    middleware = SOCMContextMiddleware(None, task=TaskContext(agent_id="a", task_text="task"))
    middleware.render = lambda: "CURRENT FACT"

    async def capture(request):
        assert sum("CURRENT FACT" in str(m.content) for m in request.messages) == 1
        return AIMessage("done")

    await middleware.awrap_model_call(_Request([HumanMessage("task")]), capture)
    await middleware.awrap_model_call(_Request([HumanMessage("task"), AIMessage("done")]), capture)


@pytest.mark.asyncio
async def test_episode_metadata_survives_real_checkpoint_rebuild():
    from langchain.agents.middleware.types import AgentMiddleware
    from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
    from langgraph.checkpoint.memory import MemorySaver

    from searchos.agents.runtime import create_search_agent_graph

    class Model(FakeMessagesListChatModel):
        def bind_tools(self, tools, **kwargs):
            return self

    captured = []

    class Capture(AgentMiddleware):
        async def awrap_model_call(self, request, handler):
            captured.append(request.messages)
            return await handler(request)

    saver = MemorySaver()
    workspace = _Workspace()

    def graph():
        return create_search_agent_graph(
            model=Model(responses=[AIMessage("continue")]),
            tools=[],
            middleware=[SearchEpisodeMiddleware(workspace), Capture()],
            checkpointer=saver,
        )

    first = _call("search", {"query": "first"}, "a")
    second = _call("search", {"query": "second"}, "b")
    second.additional_kwargs["sf_search_episode"] = {
        "evidence_ids": ["fact-1"],
        "filled_cells": [],
        "previous": {"evidence_added": ["fact-1"], "coverage_delta": {}},
    }
    config = {"configurable": {"thread_id": "episode-rebuild"}}
    await graph().ainvoke(
        {
            "messages": [
                HumanMessage("task"),
                first,
                ToolMessage("OLD SECRET", tool_call_id="a"),
                second,
                ToolMessage("CURRENT", tool_call_id="b"),
            ]
        },
        config,
    )
    await graph().ainvoke({"messages": [HumanMessage("Continue revenue only")]}, config)
    text = "\n".join(str(m.content) for m in captured[-1])
    assert "OLD SECRET" not in text
    assert "CURRENT" in text
    assert "fact-1" in text
    assert "Continue revenue only" in text
