from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from searchos.harness.middleware.context.control_middleware import ControlMiddleware
from searchos.harness.middleware.context.layered_context import (
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

    async def await_pending_flushes(self, timeout: float = 5.0) -> int:
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
    assert "search({\"query\":\"first query\"})" in prompt
    assert "open({\"id_or_url\":\"2\",\"loc\":256})" in prompt
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

    second = first + [search_2, ToolMessage(
        content="result 2", tool_call_id="search-2", name="search",
    )]
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
async def test_control_middleware_delegates_model_wrapper():
    workspace = _Workspace()
    middleware = ControlMiddleware(workspace=workspace, force_layered=True)
    search = _call("search", {"query": "query"}, "search-1")

    async def handler(_request):
        return search

    await middleware.awrap_model_call(
        _Request([HumanMessage(content="task")]),
        handler,
    )
    assert isinstance(middleware._inner, SearchEpisodeMiddleware)
    assert middleware._inner._active is not None


def test_control_middleware_reads_runtime_setting(monkeypatch):
    from searchos.config.settings import settings

    monkeypatch.setattr(settings, "use_layered_context", True)
    middleware = ControlMiddleware(workspace=_Workspace())

    assert isinstance(middleware._inner, SearchEpisodeMiddleware)
