"""Hybrid 来源范围、无表证据和任务关联的回归契约。"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from searchos.harness.middleware.extraction import (
    TaskContext,
    ExtractionCoordinator,
    InMemoryEvidenceStore,
    WorkspaceEvidenceStore,
)
from searchos.harness.middleware.extraction.core.commit import ingest_facts
from searchos.harness.middleware.extraction.core.models import ExtractionConfig
from searchos.harness.middleware.extraction.core.preparation import OriginalWindowPreparer
from searchos.harness.middleware.extraction.core.routing import SchemaRouting
from searchos.socm import SearchState

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "web"))

from searchos.harness.middleware.extraction import (
    DeliveryMode,
    EvidenceObservation,
)
from searchos.socm.evidence import EvidenceNode, EvidenceStatus, bind_task_evidence
from searchos.socm.frontier import FrontierTask
from searchos.tools.search_state import _source_scope_var


class FindingsJudge:
    def __init__(self, *, supported=True, malformed=False):
        self.calls = []
        self.supported = supported
        self.malformed = malformed

    async def ainvoke(self, prompt):
        self.calls.append(prompt)
        if self.malformed:
            return SimpleNamespace(content="invalid JSON")
        rows = (
            [{"id": "0", "supported": self.supported}]
            if "核验每项事实" in prompt
            else [
                {
                    "finding": "Alpha requires 120 credits.",
                    "source_excerpt": "Alpha requires 120 credits.",
                    "relation": "supports",
                }
            ]
        )
        return SimpleNamespace(content=json.dumps(rows))


def findings_state():
    state = SearchState(
        intent="Compare the requirements",
        research_mode="findings",
        source_scope={"mode": "hybrid", "documents": []},
    )
    for tid in ["local", "web"]:
        state.frontier.add(
            FrontierTask(id=tid, question=f"Check {tid} requirements", result_mode="findings")
        )
    return state


def observation(tid="local", source="https://example.org/requirements"):
    return EvidenceObservation(
        task_id=tid,
        source_url=source,
        content="Official programme requirements: Alpha requires 120 credits. Applies to 2026 entrants.",
    )


@pytest.mark.asyncio
async def test_findings_commit_without_schema_and_share_one_fact_between_tasks():
    store = InMemoryEvidenceStore(findings_state())
    judge = FindingsJudge()
    coordinator = ExtractionCoordinator(
        judge,
        store,
        commit_rows=ingest_facts,
        preparer=OriginalWindowPreparer(ExtractionConfig()),
        routing=SchemaRouting(),
    )
    first = await coordinator.submit(observation(), delivery=DeliveryMode.SYNC)
    assert first.committed_node_ids
    assert len(judge.calls) == 2
    assert not store.state.coverage_map.tables
    assert store.state.frontier.questions[0].status.value == "pending"
    await coordinator.submit(observation("web"), delivery=DeliveryMode.SYNC)
    assert len(store.state.evidence_graph.nodes) == 1
    assert {b.task_id for b in store.state.evidence_graph.task_bindings} == {"local", "web"}
    eid = store.state.evidence_graph.nodes[0].id
    assert bind_task_evidence(store.state, "web", [eid]) == 0
    restored = SearchState.model_validate_json(store.state.model_dump_json())
    assert restored.evidence_graph.task_bindings == store.state.evidence_graph.task_bindings


@pytest.mark.asyncio
async def test_findings_reject_unsupported_claims_from_pages_and_summaries():
    store = InMemoryEvidenceStore(findings_state())
    judge = FindingsJudge(supported=False)
    coordinator = ExtractionCoordinator(
        judge,
        store,
        commit_rows=ingest_facts,
        preparer=OriginalWindowPreparer(ExtractionConfig()),
        routing=SchemaRouting(),
    )
    await coordinator.submit(observation(), delivery=DeliveryMode.SYNC)
    await coordinator.submit(
        observation(source="agent://search/final_summary"), delivery=DeliveryMode.SYNC
    )
    assert len(judge.calls) == 4
    assert store.state.evidence_graph.nodes == []
    assert store.state.evidence_graph.task_bindings == []


@pytest.mark.asyncio
async def test_findings_anchor_quote_across_browser_line_labels():
    source = "[Now viewing] Programme\nURL: https://example.org/requirements\n\nL0: Alpha requires 120\nL1: credits.\n"
    store = InMemoryEvidenceStore(findings_state())
    coordinator = ExtractionCoordinator(
        FindingsJudge(),
        store,
        commit_rows=ingest_facts,
        preparer=OriginalWindowPreparer(ExtractionConfig()),
        routing=SchemaRouting(),
    )
    await coordinator.submit(
        EvidenceObservation(
            task_id="web", source_url="https://example.org/requirements", content=source
        ),
        delivery=DeliveryMode.SYNC,
    )
    assert len(store.state.evidence_graph.nodes) == 1
    node = store.state.evidence_graph.nodes[0]
    assert node.finding == "Alpha requires 120 credits."
    assert node.source_excerpt == "Alpha requires 120\nL1: credits."
    assert source[slice(*node.span)] == node.source_excerpt
    assert store.state.evidence_graph.observations[0].text == source


@pytest.mark.asyncio
async def test_disallowed_source_is_filtered_before_findings_model_calls():
    state = findings_state()
    state.source_scope = {"mode": "local", "documents": []}
    judge = FindingsJudge()
    store = InMemoryEvidenceStore(state)
    coordinator = ExtractionCoordinator(
        judge,
        store,
        commit_rows=ingest_facts,
        preparer=OriginalWindowPreparer(ExtractionConfig()),
        routing=SchemaRouting(),
    )
    await coordinator.submit(observation(), delivery=DeliveryMode.SYNC)
    assert not judge.calls
    assert not store.state.evidence_graph.nodes


@pytest.mark.asyncio
async def test_findings_failure_releases_observation_for_retry():
    store = InMemoryEvidenceStore(findings_state())
    judge = FindingsJudge(malformed=True)
    coordinator = ExtractionCoordinator(
        judge,
        store,
        commit_rows=ingest_facts,
        preparer=OriginalWindowPreparer(ExtractionConfig()),
        routing=SchemaRouting(),
    )
    await coordinator.submit(observation(), delivery=DeliveryMode.SYNC)
    judge.malformed = False
    receipt = await coordinator.submit(observation(), delivery=DeliveryMode.SYNC)
    assert not receipt.duplicate
    assert len(store.state.evidence_graph.nodes) == 1


@pytest.mark.asyncio
async def test_split_findings_anchor_to_persisted_original_observation():
    from searchos.harness.middleware.extraction import ExtractionConfig
    from searchos.socm.views.trace import resolve_cell_provenance

    original = ("Unrelated introduction.\n" * 150) + "Alpha requires 120 credits.\n"
    store = InMemoryEvidenceStore(findings_state())
    coordinator = ExtractionCoordinator(
        FindingsJudge(),
        store,
        preparer=OriginalWindowPreparer(ExtractionConfig(chunk_char_budget=1200)),
        routing=SchemaRouting(),
        commit_rows=ingest_facts,
        config=ExtractionConfig(chunk_char_budget=1200),
    )
    await coordinator.submit(
        EvidenceObservation(task_id="web", content=original, source_url="https://example.org/long"),
        delivery=DeliveryMode.SYNC,
    )
    restored = SearchState.model_validate_json(store.state.model_dump_json())
    assert len(restored.evidence_graph.nodes) == 1
    node = restored.evidence_graph.nodes[0]
    assert len(restored.evidence_graph.observations) == 1
    observed = restored.evidence_graph.observations[0]
    assert observed.text == original and observed.id == node.observation_id
    assert original[slice(*node.span)] == node.source_excerpt == "Alpha requires 120 credits."
    assert node.span[0] > 1200
    trace = resolve_cell_provenance(restored, evidence_id=node.id)[0]
    assert trace["span_basis"] == "observation"
    assert trace["observation_id"] == observed.id
    assert trace["span"]["start_char"] == node.span[0]


def test_table_local_windows_keep_individual_locator_metadata():
    coordinator = ExtractionCoordinator(
        FindingsJudge(),
        InMemoryEvidenceStore(findings_state()),
        commit_rows=ingest_facts,
        preparer=OriginalWindowPreparer(ExtractionConfig()),
        routing=SchemaRouting(),
    )
    windows = [
        {
            "source_url": "local://same-source",
            "content": "window " + str(page),
            "result_mode": "table",
            "local_source_metadata": {"page": page},
        }
        for page in [7, 8]
    ]
    prepared = coordinator._preparer.prepare_pages(windows)
    assert len(prepared) == 2
    assert [item["local_source_metadata"] for item in prepared] == [{"page": 7}, {"page": 8}]


def test_binding_validation_is_atomic_and_does_not_restore_inactive_evidence():
    state = findings_state()
    state.evidence_graph.add_node(
        EvidenceNode(id="ok", finding="Supported", source="https://example.org")
    )
    state.evidence_graph.add_node(
        EvidenceNode(id="bad", finding="Rejected", status=EvidenceStatus.REJECTED)
    )
    with pytest.raises(ValueError):
        bind_task_evidence(state, "web", ["ok", "bad"])
    assert not state.evidence_graph.task_bindings
    with pytest.raises(ValueError, match="Unknown task"):
        bind_task_evidence(state, "missing", ["ok"])


def test_task_dedup_keeps_source_and_result_modes_distinct():
    state = findings_state()
    for tid, agent, mode in [
        ("a", "search_agent", "findings"),
        ("b", "local_search_agent", "findings"),
        ("c", "search_agent", "table"),
    ]:
        result = state.frontier.add(
            FrontierTask(id=tid, question="same question", agent_type=agent, result_mode=mode)
        )
        assert result.id == tid
    duplicate = state.frontier.add(
        FrontierTask(
            id="d", question="same question", agent_type="search_agent", result_mode="findings"
        )
    )
    assert duplicate.id == "a"
    dependent = state.frontier.add(
        FrontierTask(
            id="dependent",
            question="same question",
            agent_type="search_agent",
            result_mode="findings",
            blocked_by=["b"],
        )
    )
    assert dependent.id == "dependent" and dependent.status.value == "blocked"
    default_agent = state.frontier.add(
        FrontierTask(
            id="default",
            question="same question",
            result_mode="findings",
        )
    )
    assert default_agent.id == "a"


@pytest.mark.asyncio
async def test_hybrid_api_snapshots_selection_and_web_cannot_carry_local_scope(
    tmp_path, monkeypatch
):
    from api.routes import local_search, search

    from searchos.local.library import LocalLibraryService

    service = LocalLibraryService(tmp_path / "data")
    library = service.create_library("Hybrid docs")
    incoming = tmp_path / "incoming"
    incoming.write_text("Alpha requires 120 credits. Applies to 2026 entrants.")
    doc = await service.index_uploaded_file(library.library_id, incoming, "requirements.txt")
    monkeypatch.setattr(local_search, "_service", lambda: service)
    monkeypatch.setattr(search, "init_search_provider", lambda _: None)
    captured = []

    async def launch(**kwargs):
        captured.append(kwargs)
        return search.SearchResponse(session_id=kwargs["session_id"], status="running")

    monkeypatch.setattr(search, "_launch_search", launch)
    selection = {
        "mode": "hybrid",
        "local": {
            "library_id": library.library_id,
            "document_ids": [doc["document_id"]],
            "model_access": True,
        },
    }
    await search.create_search(
        search.SearchRequest(query="Compare online requirements", sources=selection)
    )
    state = captured[-1]["state"]
    assert state.research_mode == "findings"
    record = state.source_scope["documents"][0]
    assert record["document_id"] == doc["document_id"]
    assert record["source_revision"] and record["generation"]
    selection["mode"] = "web"
    with pytest.raises(HTTPException) as exc:
        await search.create_search(search.SearchRequest(query="Only web", sources=selection))
    assert exc.value.status_code == 422
    await search.create_search(
        search.SearchRequest(query="Hybrid without documents", sources={"mode": "hybrid"})
    )
    assert captured[-1]["state"].source_scope == {"mode": "hybrid", "documents": []}

    def unavailable(_):
        raise ValueError("provider not configured")

    monkeypatch.setattr(search, "init_search_provider", unavailable)
    selection["mode"] = "hybrid"
    await search.create_search(
        search.SearchRequest(query="Use available sources", sources=selection)
    )
    limited = captured[-1]["state"].source_scope
    assert limited["mode"] == "hybrid" and limited["documents"]
    assert "web" in limited["unavailable_sources"]
    for mode in ["web", "hybrid"]:
        with pytest.raises(HTTPException) as exc:
            await search.create_search(
                search.SearchRequest(query="No sources", sources={"mode": mode})
            )
        assert exc.value.status_code == 503


@pytest.mark.asyncio
async def test_scope_change_discards_previous_evidence_and_answer_preamble(monkeypatch):
    from api.routes import search

    previous = findings_state()
    previous.source_scope["documents"] = [{"document_id": "previous"}]
    previous.evidence_graph.add_node(EvidenceNode(id="old", finding="private old fact"))
    monkeypatch.setattr(search, "_load_prior_state", lambda _: previous)
    monkeypatch.setattr(search, "init_search_provider", lambda _: None)
    captured = {}

    async def launch(**kwargs):
        captured.update(kwargs)
        return search.SearchResponse(session_id=kwargs["session_id"], status="running")

    monkeypatch.setattr(search, "_launch_search", launch)
    await search.create_search(
        search.SearchRequest(
            query="New scope",
            follow_up_to="hybrid-test",
            sources={"mode": "hybrid"},
            history=[{"query": "Old question", "answer": "private old fact"}],
        )
    )
    assert not captured["state"].evidence_graph.nodes
    assert "private old fact" not in (captured["context_preamble"] or "")
    assert captured["session_id"] == "hybrid-test"


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["web", "hybrid"])
async def test_follow_up_without_sources_inherits_saved_mode(monkeypatch, mode):
    from api.routes import search

    previous = SearchState(source_scope={"mode": mode, "documents": []})
    monkeypatch.setattr(search, "_load_prior_state", lambda _: previous)
    monkeypatch.setattr(search, "init_search_provider", lambda _: None)
    captured = {}

    async def launch(**kwargs):
        captured.update(kwargs)
        return search.SearchResponse(session_id=kwargs["session_id"], status="running")

    monkeypatch.setattr(search, "_launch_search", launch)
    await search.create_search(search.SearchRequest(query="Continue", follow_up_to="saved-mode"))
    assert captured["state"].source_scope["mode"] == mode
    assert captured["state"].research_mode == ("findings" if mode == "hybrid" else "table")
    assert captured["req"].sources.mode == mode


@pytest.mark.asyncio
async def test_next_turn_mode_does_not_change_in_flight_agent_scope():
    import asyncio

    from searchos.agents.orchestrator.catalog import _is_agent_enabled

    proceed = asyncio.Event()

    async def running_turn():
        await proceed.wait()
        return _is_agent_enabled("local_search_agent"), _is_agent_enabled("search_agent")

    token = _source_scope_var.set({"mode": "hybrid", "documents": [{"document_id": "selected"}]})
    try:
        child = asyncio.create_task(running_turn())
        _source_scope_var.set({"mode": "web", "documents": []})
        assert not _is_agent_enabled("local_search_agent")
        proceed.set()
        assert await child == (True, True)
    finally:
        _source_scope_var.reset(token)


def test_explicit_web_scope_disables_local_agent_even_when_globally_enabled(monkeypatch):
    from searchos.agents.orchestrator.catalog import _is_agent_enabled
    from searchos.config.settings import settings

    monkeypatch.setattr(settings, "enable_local_tools", True)
    monkeypatch.setattr(settings, "local_allow_model_access", True)
    token = _source_scope_var.set({"mode": "web", "documents": []})
    try:
        assert not _is_agent_enabled("local_search_agent")
        assert _is_agent_enabled("search_agent")
        _source_scope_var.set({"mode": "hybrid", "documents": []})
        assert not _is_agent_enabled("local_search_agent")
        _source_scope_var.set({"mode": "hybrid", "documents": [{"document_id": "selected"}]})
        assert _is_agent_enabled("local_search_agent")
    finally:
        _source_scope_var.reset(token)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mode,forbidden",
    [
        ("web", "local_search_agent"),
        ("local", "search_agent"),
        ("local", "explore_agent"),
        ("hybrid", "local_search_agent"),  # Empty selection never grants a library.
    ],
)
async def test_source_mode_rejects_forbidden_enqueue_and_direct_spawn(tmp_path, mode, forbidden):
    from searchos.agents import runtime
    from searchos.agents.orchestrator import lifecycle
    from searchos.socm.workspace import WorkspaceManager
    from searchos.tools.tasks import enqueue_tasks

    state = SearchState(research_mode="findings", source_scope={"mode": mode, "documents": []})
    workspace = WorkspaceManager(tmp_path, "mode-gate")
    workspace.create()
    workspace.save_state(state)
    token = _source_scope_var.set(state.source_scope)
    try:
        runtime.set_orchestrator_context(workspace=workspace, model=object())
        result = json.loads(
            await enqueue_tasks.ainvoke(
                {
                    "items_json": json.dumps(
                        [
                            {
                                "agent_type": forbidden,
                                "task": "Attempt an unavailable source",
                                "result_mode": "findings",
                            },
                        ]
                    )
                }
            )
        )
        assert result["rejected"]
        assert not workspace.load_state().frontier.questions
        with pytest.raises(ValueError, match="unavailable in this source scope"):
            await lifecycle._spawn_sub_agent(forbidden, "Attempt direct dispatch", [])
        assert not runtime._ctx.task_pool
    finally:
        _source_scope_var.reset(token)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "workflow",
    [
        "local_first",
        "web_first",
        "parallel",
        "local_only",
        "web_only",
        "unavailable_web",
        "model_error",
        "repair_answer",
        "unsupported_answer",
        "review_unavailable",
        "steer_during_review",
        "forced_stop",
        "forced_stop_table",
    ],
)
async def test_real_hybrid_graph_local_then_web_dependency_and_cited_answer(
    tmp_path, monkeypatch, workflow
):
    """真实调度/工具/Middleware；仅替换模型与网络边界，不发送文档到外部。"""
    import queue
    import re

    from langchain_core.language_models import BaseChatModel
    from langchain_core.messages import AIMessage, ToolMessage
    from langchain_core.outputs import ChatGeneration, ChatResult
    from pydantic import Field

    from searchos.agents import runtime
    from searchos.config.settings import settings
    from searchos.harness.session import SearchSession
    from searchos.local.library import LocalLibraryService
    from searchos.tools.simple_browser import tools as browser_tools
    from searchos.tools.simple_browser.render import PageContents

    seen = []
    steer_queue = queue.Queue()
    tasks = [
        {
            "id": "read_local",
            "agent_type": "local_search_agent",
            "task": "Read selected programme requirements",
            "result_mode": "findings",
        },
        {
            "id": "verify_web",
            "agent_type": "search_agent",
            "task": "Verify requirements online from https://example.org/requirements",
            "result_mode": "findings",
        },
    ]
    if workflow == "local_first":
        tasks[1]["blocked_by"] = ["read_local"]
    elif workflow == "web_first":
        tasks[0]["blocked_by"] = ["verify_web"]
    elif workflow in {"local_only", "unavailable_web"}:
        tasks = tasks[:1]
    elif workflow == "web_only":
        tasks = tasks[1:]

    class Model(BaseChatModel):
        names: list[str] = Field(default_factory=list)
        origin: str = "orchestrator"

        @property
        def _llm_type(self):
            return "hybrid-scripted-offline"

        def bind_tools(self, tools, **kwargs):
            return self.model_copy(update={"names": [t.name for t in tools]})

        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            if workflow == "model_error":
                raise RuntimeError("Synthetic model failure")
            history = [m for m in messages if isinstance(m, ToolMessage)]
            system = "\n".join(str(m.content) for m in messages if m.type == "system")
            if "enqueue_tasks" in self.names:
                if workflow.startswith("forced_stop") and "HARD STOP" in system:
                    return ChatResult(
                        generations=[ChatGeneration(message=AIMessage(content="继续等待子任务。"))]
                    )
                if workflow == "unavailable_web":
                    assert "本轮无法进行外部核实" in system
                    assert "**search_agent**" not in system
                if not history:
                    name, args = "enqueue_tasks", {"items_json": json.dumps(tasks)}
                elif history[-1].name == "enqueue_tasks" or (
                    history[-1].name == "check_agents"
                    and json.loads(str(history[-1].content)).get("remaining", 0)
                ):
                    name, args = "check_agents", {}
                elif history[-1].name == "check_agents":
                    name, args = "read_evidence", {}
                else:
                    payload = json.loads(str(history[-1].content))
                    seen.append(("read_evidence", payload))
                    nodes = payload.get("nodes", payload.get("evidence", []))
                    refs = [n["citation"] for n in nodes]
                    answer = "取得的原文表明 Alpha requires 120 credits. " + " ".join(
                        f"[原文]({r})" for r in refs
                    )
                    repaired = any(
                        "[回答来源检查]" in str(m.content) for m in messages if m.type == "human"
                    )
                    if workflow == "unsupported_answer" or (
                        workflow == "repair_answer" and not repaired
                    ):
                        answer = answer.replace(
                            "Alpha requires 120 credits.", "Alpha requires 900 credits."
                        )
                    if any(
                        "用中文注明学分" in str(m.content) for m in messages if m.type == "human"
                    ):
                        answer += " 即 120 学分。"
                    seen.append(("answer", answer))
                    return ChatResult(
                        generations=[ChatGeneration(message=AIMessage(content=answer))]
                    )
            elif "local_catalog" in self.names:
                if not history:
                    seen.append(("local_prerequisite", system))
                    path = re.search(r"documents/doc_[a-z0-9]+\.md", system).group(0)
                    name, args = "local_catalog", {"path": path}
                elif history[-1].name == "local_catalog":
                    ref = re.search(r'ref_id="([^"\n]+)"', str(history[-1].content)).group(1)
                    name, args = "local_open", {"ref_id": ref}
                else:
                    seen.append(("local", str(history[-1].content)))
                    return ChatResult(
                        generations=[
                            ChatGeneration(
                                message=AIMessage(
                                    content="Alpha requires 120 credits. Read selected source."
                                )
                            )
                        ]
                    )
            elif "open" in self.names:
                if not history:
                    seen.append(("web_prerequisite", system))
                    name, args = "open", {"id_or_url": "https://example.org/requirements"}
                else:
                    seen.append(("web", str(history[-1].content)))
                    return ChatResult(
                        generations=[
                            ChatGeneration(
                                message=AIMessage(
                                    content="Alpha requires 120 credits. Verified on https://example.org/requirements."
                                )
                            )
                        ]
                    )
            else:
                text = str(messages[-1].content)
                if "[RESEARCH_FINALIZE]" in system:
                    payload = json.loads(text)
                    seen.append(("finalizer", self.origin))
                    seen.append(("finalize", payload))
                    assert len(payload["evidence"]) == 2, "Finalization must see late worker facts"
                    answer = "Alpha requires 120 credits. " + " ".join(
                        f"[原文](evidence:{node['id']})" for node in payload["evidence"]
                    )
                    return ChatResult(
                        generations=[ChatGeneration(message=AIMessage(content=answer))]
                    )
                if "[ANSWER_SUPPORT_REVIEW]" in text:
                    payload = json.loads(text.split("\n", 2)[2])
                    seen.append(("answer_review", payload))
                    if (
                        workflow == "steer_during_review"
                        and len([v for k, v in seen if k == "answer_review"]) == 1
                    ):
                        steer_queue.put("用中文注明学分")
                    claims = [
                        {
                            "text": payload["answer"],
                            "kind": "fact",
                            "supported": "Alpha requires 900 credits." not in payload["answer"],
                            "bindings": [
                                {"evidence_id": node["id"], "quote": node["source_excerpt"]}
                                for node in payload["evidence"]
                            ],
                            "reason": "所引原文是 120 credits，不能支持 900 credits。",
                        }
                    ]
                    content = (
                        "invalid"
                        if workflow == "review_unavailable"
                        else json.dumps({"complete": True, "claims": claims})
                    )
                    return ChatResult(
                        generations=[ChatGeneration(message=AIMessage(content=content))]
                    )
                rows = (
                    [{"id": "0", "supported": True}]
                    if "核验每项事实" in text
                    else [
                        {
                            "finding": "Alpha requires 120 credits.",
                            "source_excerpt": "Alpha requires 120 credits.",
                            "relation": "supports",
                        }
                    ]
                )
                return ChatResult(
                    generations=[ChatGeneration(message=AIMessage(content=json.dumps(rows)))]
                )
            seen.append(("tool", name))
            return ChatResult(
                generations=[
                    ChatGeneration(
                        message=AIMessage(
                            content="",
                            tool_calls=[{"name": name, "args": args, "id": f"call_{len(seen)}"}],
                        )
                    )
                ]
            )

    service = LocalLibraryService(tmp_path / "data")
    library = service.create_library("Graph test")
    incoming = tmp_path / "incoming"
    incoming.write_text(
        "Official programme requirements: Alpha requires 120 credits. Applies to 2026 entrants."
    )
    doc = await service.index_uploaded_file(library.library_id, incoming, "requirements.txt")
    record, _ = service._verified_blocks(library.library_id, [doc["document_id"]])[0]
    state = SearchState(
        intent="结合本地与网络核实学分要求",
        research_mode="table" if workflow == "forced_stop_table" else "findings",
        source_scope={
            "mode": "hybrid",
            "library_id": library.library_id,
            "index_root": library.index_root,
            "documents": [record.model_dump(mode="json")],
        },
    )
    if workflow == "unavailable_web":
        state.source_scope["unavailable_sources"] = {"web": "本轮无法进行外部核实。"}

    async def fetch(url, *args, **kwargs):
        return PageContents(
            url=url,
            title="Programme",
            text="Official programme requirements: Alpha requires 120 credits. Applies to 2026 entrants.",
        )

    monkeypatch.setattr(browser_tools, "_fetch_page", fetch)
    for name in [
        "enable_skills",
        "enable_writer_agent",
        "enable_access_skills",
        "enable_strategy_skills",
        "enable_orchestrator_skills",
    ]:
        if hasattr(settings, name):
            monkeypatch.setattr(settings, name, False)
    if workflow.startswith("forced_stop"):
        from searchos.harness.middleware.sensor.core.coverage_stall_sensor import CoverageStallSensor

        async def stop_after_dispatch(self, tool_name, tool_result, tool_input=None):
            if tool_name == "enqueue_tasks":
                return {
                    "force_stop": True,
                    "reason": "test_stop",
                    "hard_block_tools": ["enqueue_tasks"],
                }
            return None

        monkeypatch.setattr(CoverageStallSensor, "check", stop_after_dispatch)
    model = Model()
    roles = [
        "orchestrator",
        "judge",
        "extraction",
        "synthesis",
        "skill_evolver",
        "post_mortem",
        "sub_agent",
    ]
    model_overrides = {role: model for role in roles}
    if workflow.startswith("forced_stop"):
        # The stopped run must use the Orchestrator for the terminal turn.
        # A distinct synthesis model makes the role observable at this seam.
        model_overrides["synthesis"] = Model(origin="synthesis")
    session = SearchSession(
        workspace_root=str(tmp_path / "runs"),
        skill_library_path=str(tmp_path / "skills"),
        max_time_s=25,
        model_overrides=model_overrides,
        skip_synthesis=False,
    )
    result = await session.run(
        state.intent, initial_state=state, session_id="hybrid-offline", steer_queue=steer_queue
    )
    final = result.search_state
    if workflow == "model_error":
        output = json.loads(
            (Path(result.workspace_path) / settings.output_dir / "result.json").read_text()
        )
        assert output["mode"] == "hybrid_partial"
        assert output["execution_error"] == result.execution_error == "RuntimeError"
        assert "研究执行中断" in output["answer"]
        assert not final.evidence_graph.nodes and not runtime._ctx.task_pool
        return
    assert {q.id: q.status.value for q in final.frontier.questions} == {
        task["id"]: "completed" for task in tasks
    }, seen
    assert len(final.evidence_graph.nodes) == len(tasks), seen
    assert {b.task_id for b in final.evidence_graph.task_bindings} == {task["id"] for task in tasks}
    if workflow in {"local_first", "web_first"}:
        key = "web_prerequisite" if workflow == "local_first" else "local_prerequisite"
        prerequisite = next(value for kind, value in seen if kind == key)
        assert (
            "前置任务的已核验发现" in prerequisite and "Alpha requires 120 credits." in prerequisite
        )
    assert not final.coverage_map.tables
    output = json.loads(
        (Path(result.workspace_path) / settings.output_dir / "result.json").read_text()
    )
    if workflow.startswith("forced_stop"):
        from searchos.harness.telemetry.conversation_context import conversation_turns

        conversation = json.loads(
            (
                Path(result.workspace_path) / "conversations" / "snapshots" / "orchestrator.json"
            ).read_text()
        )
        assert len([v for k, v in seen if k == "finalize"]) == 1
        assert ("finalizer", "orchestrator") in seen
        assert ("finalizer", "synthesis") not in seen
        assert output["stop_reason"]
        assert "Alpha requires 120 credits." in output["answer"]
        assert "继续等待子任务" not in output["answer"]
        assert result.final_messages[-1] == {"role": "ai", "content": output["answer"]}
        assert conversation["messages"][-1]["content"] == output["answer"]
        assert conversation["messages"][-1]["metadata"]["finalizer"] == "orchestrator"
        assert conversation_turns(result.workspace_path) == [
            {
                "query": state.intent,
                "answer": output["answer"],
                "steers": [],
            }
        ]
        return
    assert not [payload for kind, payload in seen if kind == "answer_review"]
    assert output["mode"] == (
        "research_finalized" if workflow.startswith("forced_stop") else "hybrid_orchestrator"
    )
    assert "尚未完成来源核验" not in output["answer"]
    if workflow in {"repair_answer", "unsupported_answer"}:
        assert "Alpha requires 900 credits." in output["answer"]
    assert len([name for kind, name in seen if kind == "tool" and name == "enqueue_tasks"]) == 1
    assert not (Path(result.workspace_path) / settings.output_dir / "answer_review.json").exists()
    if workflow != "web_only":
        assert "local://" in output["answer"]
        local_node = next(n for n in final.evidence_graph.nodes if n.source.startswith("local://"))
        assert service.resolve_citation(local_node.source)["file_name"] == "requirements.txt"
    if workflow not in {"local_only", "unavailable_web"}:
        assert "https://example.org/requirements" in output["answer"]
    assert not runtime._ctx.task_pool


@pytest.mark.asyncio
async def test_hybrid_schema_drives_both_task_modes_and_preserves_task_bindings():
    from searchos.harness.middleware.extraction import ExtractionConfig

    state = findings_state()
    state.coverage_map.add_table(
        "programmes", ["Name", "Credits"], primary_key=["Name"], entities=["Alpha"]
    )
    state.frontier.add(
        FrontierTask(
            id="table", question="List credits", result_mode="table", table_id="programmes"
        )
    )
    store = InMemoryEvidenceStore(state)

    class MixedJudge(FindingsJudge):
        async def ainvoke(self, prompt):
            if "FILL MODE" in prompt or "DISCOVER MODE" in prompt or "Credits" in prompt:
                return SimpleNamespace(
                    content=json.dumps(
                        [
                            {
                                "Name": "Alpha",
                                "Credits": "120",
                                "_alignment": "full",
                                "_confidence": "high",
                                "_source_excerpt": "Alpha requires 120 credits.",
                            }
                        ]
                    )
                )
            return await super().ainvoke(prompt)

    coordinator = ExtractionCoordinator(
        MixedJudge(),
        store,
        preparer=OriginalWindowPreparer(
            ExtractionConfig(dual_mode=False, cross_table_backfill=False)
        ),
        routing=SchemaRouting(),
        commit_rows=ingest_facts,
        config=ExtractionConfig(dual_mode=False, cross_table_backfill=False),
    )
    await coordinator.submit(observation("local"), delivery=DeliveryMode.SYNC)
    assert store.state.coverage_map.cells["programmes/Alpha.Credits"].supporting_evidence_ids
    await coordinator.submit(
        EvidenceObservation(
            task_id="table",
            target_table="programmes",
            source_url="https://example.org/requirements",
            content=observation().content,
        ),
        delivery=DeliveryMode.SYNC,
    )
    cell_ids = set(
        store.state.coverage_map.cells["programmes/Alpha.Credits"].supporting_evidence_ids
    )
    assert cell_ids
    table_ids = {
        b.evidence_id for b in store.state.evidence_graph.task_bindings if b.task_id == "table"
    }
    free_ids = {
        b.evidence_id for b in store.state.evidence_graph.task_bindings if b.task_id == "local"
    }
    assert cell_ids <= table_ids
    assert cell_ids <= free_ids
    before = len(store.state.evidence_graph.nodes)
    receipt = await coordinator.submit(
        EvidenceObservation(
            task_id="table",
            target_table="programmes",
            source_url="agent://table/final_summary",
            content=observation().content,
        ),
        delivery=DeliveryMode.SYNC,
    )
    assert receipt.accepted and receipt.committed_node_ids
    assert len(store.state.evidence_graph.nodes) > before


@pytest.mark.asyncio
async def test_new_findings_reset_stall_without_inventing_table_progress():
    from searchos.harness.middleware.sensor.core.coverage_stall_sensor import CoverageStallSensor
    from searchos.socm.views.render import render_orchestrator_view
    from searchos.socm.views.snapshot import SearchStateSnapshot

    store = InMemoryEvidenceStore(findings_state())
    sensor = CoverageStallSensor(store, max_stalled_rounds=2)
    report = {"reports": [{"kind": "search"}]}
    assert await sensor.check("check_agents", report) is None
    store.state.evidence_graph.add_node(
        EvidenceNode(id="fact", finding="Supported", source="https://example.org")
    )
    bind_task_evidence(store.state, "local", ["fact"])
    assert await sensor.check("check_agents", report) is None
    view = render_orchestrator_view(SearchStateSnapshot.from_state(store.state))
    assert "source-supported findings" in view and "local" in view
    assert "Known rows" not in view
    assert await sensor.check("check_agents", report) is None
    assert (await sensor.check("check_agents", report))["force_stop"] is True


@pytest.mark.asyncio
async def test_read_evidence_audit_does_not_expand_source_scope():
    from searchos.local.models import PdfRegionLocator
    from searchos.local.reader.references import build_ref_id
    from searchos.tools.search_state import _workspace_var
    from searchos.tools.socm_read import read_evidence

    state = findings_state()
    ref = build_ref_id(
        library_id="lib_other",
        document_id="doc_other",
        source_revision="a" * 64,
        locators=[PdfRegionLocator(page_start=1, page_end=1)],
    )
    state.evidence_graph.add_node(EvidenceNode(id="outside", source=ref, finding="Unselected file"))
    store = InMemoryEvidenceStore(state)
    token = _workspace_var.set(store)
    try:
        result = json.loads(await read_evidence.ainvoke({"include_inactive": True}))
        assert result["nodes"] == []
    finally:
        _workspace_var.reset(token)


@pytest.mark.asyncio
async def test_task_evidence_filter_intersects_explicit_ids():
    from searchos.tools.search_state import _workspace_var
    from searchos.tools.socm_read import read_evidence

    state = findings_state()
    for eid in ["one", "two"]:
        state.evidence_graph.add_node(
            EvidenceNode(id=eid, source="https://example.org", finding=eid)
        )
    bind_task_evidence(state, "web", ["one"])
    bind_task_evidence(state, "local", ["two"])
    token = _workspace_var.set(InMemoryEvidenceStore(state))
    try:
        result = json.loads(
            await read_evidence.ainvoke({"task_id": "web", "evidence_ids": "one,two"})
        )
        assert [node["id"] for node in result["nodes"]] == ["one"]
        missing = json.loads(
            await read_evidence.ainvoke({"task_id": "missing", "evidence_ids": "one"})
        )
        assert not missing["nodes"]
    finally:
        _workspace_var.reset(token)


@pytest.mark.asyncio
async def test_hybrid_skill_page_keeps_snapshot_source_and_visible_window(tmp_path):
    from searchos.harness.middleware import WebEvidenceMiddleware, SourceContext
    from searchos.socm.workspace import WorkspaceManager
    from searchos.tools.search_state import _current_task_id_var, _workspace_var
    from searchos.tools.simple_browser import state as browser_state
    from searchos.tools.simple_browser.skill_pages import show_skill_result

    store = WorkspaceManager(tmp_path, session_id="skill-findings")
    store.create()
    store.save_state(findings_state())
    judge = FindingsJudge()
    middleware = WebEvidenceMiddleware(
        ExtractionCoordinator(
            judge,
            WorkspaceEvidenceStore(store),
            commit_rows=ingest_facts,
            preparer=OriginalWindowPreparer(ExtractionConfig()),
            routing=SchemaRouting(),
        ),
        context=TaskContext(task_id="web"),
        source=SourceContext(workspace=store),
    )
    payload = {
        "url": "https://example.org/search",
        "records": [
            {"source_url": "https://example.org/alpha", "text": "Alpha requires 120 credits."},
            *[{"text": "filler " * 20} for _ in range(200)],
            {
                "source_url": "https://example.org/beta",
                "text": "Beta permits 90 requests per minute.",
            },
        ],
    }
    token = _current_task_id_var.set("web")
    wt = _workspace_var.set(store)
    bt = browser_state._browser_var.set(browser_state.BrowserState())
    try:
        view = show_skill_result("fixture", {}, payload)
        source = middleware._extract_source_url(view)

        async def handler(_):
            return SimpleNamespace(content=view)

        result = await middleware.awrap_tool_call(
            SimpleNamespace(tool_call={"name": "skill_fixture", "args": {}}), handler
        )
        assert result.content == view
        await middleware.coordinator.finalize()
        state = store.load_state()
        assert [node.source for node in state.evidence_graph.nodes] == [source]
        assert source.startswith("skill://fixture/")
        assert {binding.task_id for binding in state.evidence_graph.task_bindings} == {"web"}
        assert all(
            "Beta permits" not in observation.text
            for observation in state.evidence_graph.observations
        )
        assert all(node.span and node.observation_id for node in state.evidence_graph.nodes)
        assert "https://example.org/alpha" in state.evidence_graph.observations[0].text
    finally:
        browser_state._browser_var.reset(bt)
        _workspace_var.reset(wt)
        _current_task_id_var.reset(token)


@pytest.mark.parametrize("multiple_windows", [False, True])
def test_findings_citations_resolve_fact_ids_and_only_unambiguous_document_aliases(
    multiple_windows,
):
    from langchain_core.messages import AIMessage

    from searchos.harness.session import _write_findings_answer
    from searchos.local.models import PdfRegionLocator
    from searchos.local.reader.references import build_ref_id

    state = SearchState()
    ref = build_ref_id(
        library_id="lib_test",
        document_id="doc_test",
        source_revision="a" * 64,
        locators=[PdfRegionLocator(page_start=7, page_end=10)],
    )
    state.evidence_graph.add_node(EvidenceNode(id="fact", source=ref, finding="A supported fact"))
    if multiple_windows:
        second = build_ref_id(
            library_id="lib_test",
            document_id="doc_test",
            source_revision="a" * 64,
            locators=[PdfRegionLocator(page_start=1, page_end=2)],
        )
        state.evidence_graph.add_node(
            EvidenceNode(id="other", source=second, finding="Another fact")
        )
    outputs = {}
    workspace = SimpleNamespace(write_output=lambda name, text: outputs.update({name: text}))
    _write_findings_answer(
        workspace,
        state,
        "Question",
        {
            "messages": [
                AIMessage(
                    content=(
                        "[资料.pdf · P7-10](evidence:fact) [文档](local://doc_test) [未知](evidence:missing)"
                    )
                )
            ]
        },
    )
    assert f"[资料.pdf · P7-10]({ref})" in outputs["report.md"]
    assert "invalid-evidence-reference" in outputs["report.md"]
    assert ("invalid-local-reference" in outputs["report.md"]) == multiple_windows
    if not multiple_windows:
        assert f"[文档]({ref})" in outputs["report.md"]


@pytest.fixture
def observation_workspace(tmp_path):
    import hashlib

    from searchos.socm.evidence import SourceObservation
    from searchos.socm.workspace import WorkspaceManager

    workspace = WorkspaceManager(tmp_path, "saved-observation")
    workspace.create()
    text = "Alpha requires 120 credits. Alpha lasts 3 years."
    source = "https://example.org/alpha"
    digest = hashlib.sha256(text.encode()).hexdigest()
    oid = (
        "obs_"
        + hashlib.sha256(
            json.dumps([source, digest, None], sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()[:24]
    )
    state = SearchState(research_mode="findings", source_scope={"mode": "hybrid", "documents": []})
    state.frontier.add(
        FrontierTask(
            id="duration",
            question="What is Alpha's duration?",
            result_mode="findings",
            agent_type="search_agent",
        )
    )
    state.evidence_graph.observations.append(
        SourceObservation(id=oid, source=source, text=text, text_hash="sha256:" + digest)
    )
    workspace.save_state(state)
    return workspace, oid


def duration_invoker(calls):
    async def invoke(prompt):
        calls.append(prompt)
        if "核验每项事实" in prompt:
            return '[{"id":"0","supported":true}]'
        return json.dumps(
            [
                {
                    "finding": "Alpha lasts 3 years.",
                    "source_excerpt": "Alpha lasts 3 years.",
                    "relation": "supports",
                }
            ]
        )

    return invoke


@pytest.mark.asyncio
async def test_saved_observation_reextracts_for_new_task_without_copying_source(
    observation_workspace,
):
    from searchos.harness.middleware.extraction.core.replay import extract_saved_observation

    workspace, oid = observation_workspace
    calls = []
    result = await extract_saved_observation(
        workspace, duration_invoker(calls), task_id="duration", observation_id=oid, start=27
    )
    assert len(calls) == 2 and result["next_start"] is None
    state = workspace.load_state()
    node = state.evidence_graph.get_node(result["evidence_ids"][0])
    assert node.finding == "Alpha lasts 3 years."
    assert state.evidence_graph.observations[0].text[slice(*node.span)] == node.source_excerpt
    assert node.span[0] == state.evidence_graph.observations[0].text.index("Alpha lasts")
    assert node.observation_id == oid
    assert len(state.evidence_graph.observations) == 1
    assert state.frontier.questions[0].status.value == "pending"

    def add_task(state):
        state.frontier.add(
            FrontierTask(
                id="compare",
                question="Check duration",
                result_mode="findings",
                agent_type="search_agent",
            )
        )
        return state

    workspace.atomic_update_state(add_task)
    repeated = await extract_saved_observation(
        workspace, duration_invoker(calls), task_id="compare", observation_id=oid
    )
    state = workspace.load_state()
    assert repeated["evidence_ids"] == result["evidence_ids"]
    assert len(state.evidence_graph.nodes) == len(state.evidence_graph.observations) == 1
    assert {b.task_id for b in state.evidence_graph.task_bindings} == {"duration", "compare"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "invalid", ["scope", "task_source", "hash", "start", "window", "cancelled_task"]
)
async def test_saved_observation_preflight_rejects_before_model(observation_workspace, invalid):
    from searchos.harness.middleware.extraction.core.replay import extract_saved_observation
    from searchos.socm.frontier import FrontierTaskStatus

    workspace, oid = observation_workspace
    state = workspace.load_state()
    if invalid == "scope":
        state.source_scope = {"mode": "local", "documents": []}
    elif invalid == "task_source":
        state.frontier.questions[0].agent_type = "local_search_agent"
    elif invalid == "hash":
        state.evidence_graph.observations[0].text += "changed"
    elif invalid == "cancelled_task":
        state.frontier.questions[0].status = FrontierTaskStatus.CANCELLED
    workspace.save_state(state)
    before = workspace.load_state().model_dump_json()
    calls = []
    with pytest.raises(ValueError):
        await extract_saved_observation(
            workspace,
            duration_invoker(calls),
            task_id="duration",
            observation_id=oid,
            start=-1 if invalid == "start" else 0,
            max_chars=12001 if invalid == "window" else 8000,
        )
    assert not calls and workspace.load_state().model_dump_json() == before


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["task", "observation", "scope"])
async def test_saved_observation_rechecks_state_at_commit(observation_workspace, change):
    from searchos.harness.middleware.extraction.core.replay import extract_saved_observation

    workspace, oid = observation_workspace
    calls = []
    inner = duration_invoker(calls)

    async def invoke(prompt):
        if "核验每项事实" in prompt:

            def mutate(state):
                if change == "task":
                    state.frontier.questions[0].question = "Different question"
                elif change == "observation":
                    state.evidence_graph.observations[0].text = "Different source"
                else:
                    state.source_scope = {"mode": "local", "documents": []}
                return state

            workspace.atomic_update_state(mutate)
        return await inner(prompt)

    with pytest.raises(ValueError, match="changed"):
        await extract_saved_observation(workspace, invoke, task_id="duration", observation_id=oid)
    assert not workspace.load_state().evidence_graph.nodes
    assert not workspace.load_state().evidence_graph.task_bindings


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["supported", "unsupported", "timeout", "cancelled", "budget"])
async def test_observation_tool_is_bounded_and_preserves_task_status(
    observation_workspace, monkeypatch, outcome
):
    import asyncio

    from searchos.config.settings import settings
    from searchos.tools import tasks

    workspace, oid = observation_workspace
    calls = []
    inner = duration_invoker(calls)

    class Judge:
        async def ainvoke(self, prompt):
            if outcome == "timeout":
                await asyncio.Future()
            if outcome == "cancelled":
                raise asyncio.CancelledError()
            if outcome == "unsupported" and "核验每项事实" in prompt:
                return SimpleNamespace(content='[{"id":"0","supported":false}]')
            return SimpleNamespace(content=await inner(prompt))

    monkeypatch.setattr(
        tasks,
        "_ctx",
        SimpleNamespace(
            workspace=workspace, judge_model=Judge(), budget_exhausted=outcome == "budget"
        ),
    )
    if outcome == "timeout":
        monkeypatch.setattr(settings, "hybrid_observation_timeout_s", 0.01)
    args = {"task_id": "duration", "observation_id": oid}
    if outcome == "cancelled":
        with pytest.raises(asyncio.CancelledError):
            await tasks.extract_observation.ainvoke(args)
    else:
        result = json.loads(await tasks.extract_observation.ainvoke(args))
        if outcome in {"timeout", "budget"}:
            assert "error" in result
        else:
            assert bool(result["evidence_ids"]) == (outcome == "supported")
    state = workspace.load_state()
    assert bool(state.evidence_graph.nodes) == (outcome == "supported")
    assert state.frontier.questions[0].status.value == "pending"


@pytest.mark.asyncio
async def test_saved_observation_partial_window_reports_remaining_text(observation_workspace):
    from searchos.harness.middleware.extraction.core.replay import extract_saved_observation

    workspace, oid = observation_workspace
    result = await extract_saved_observation(
        workspace, duration_invoker([]), task_id="duration", observation_id=oid, max_chars=27
    )
    assert result["evidence_ids"] == []
    assert result["next_start"] == 27 and result["total_chars"] > 27
    assert not workspace.load_state().evidence_graph.nodes


@pytest.mark.asyncio
async def test_repeated_quote_keeps_requested_window_offsets():
    from searchos.harness.middleware.extraction.core.findings import extract_and_commit

    text = "Alpha lasts 3 years.\n\nAlpha lasts 3 years."
    start = text.rindex("Alpha")
    state = SearchState(research_mode="findings")
    state.frontier.add(
        FrontierTask(id="duration", question="Check duration", result_mode="findings")
    )
    store = InMemoryEvidenceStore(state)
    ids = await extract_and_commit(
        [
            {
                "source_url": "https://example.org/repeat",
                "content": text[start:],
                "observation_text": text,
                "observation_offset": start,
                "task_id": "duration",
            }
        ],
        store=store,
        invoke=duration_invoker([]),
    )
    node = store.state.evidence_graph.get_node(ids[0])
    assert node.span == (start, len(text))


@pytest.mark.asyncio
@pytest.mark.parametrize("source_kind", ["web", "local"])
async def test_reextract_with_schema_automatically_projects_original_source(
    observation_workspace, monkeypatch, source_kind
):
    import hashlib

    from searchos.local.models import PdfRegionLocator
    from searchos.local.reader.references import build_ref_id
    from searchos.tools import schema, tasks

    workspace, oid = observation_workspace
    state = workspace.load_state()
    observed = state.evidence_graph.observations[0]
    if source_kind == "local":
        observed.source = build_ref_id(
            library_id="lib_test",
            document_id="doc_test",
            source_revision="a" * 64,
            locators=[PdfRegionLocator(page_start=7, page_end=10)],
        )
        state.source_scope["documents"] = [
            {"library_id": "lib_test", "document_id": "doc_test", "source_revision": "a" * 64}
        ]
        state.frontier.questions[0].agent_type = "local_search_agent"
        digest = observed.text_hash.removeprefix("sha256:")
        oid = (
            "obs_"
            + hashlib.sha256(
                json.dumps(
                    [observed.source, digest, None], sort_keys=True, ensure_ascii=False
                ).encode()
            ).hexdigest()[:24]
        )
        observed.id = oid
    state.coverage_map.add_table(
        "programmes", ["Name", "Duration"], primary_key=["Name"], entities=["Alpha"]
    )
    workspace.save_state(state)
    calls = []

    class Judge:
        async def ainvoke(self, prompt):
            calls.append(prompt)
            return SimpleNamespace(
                content=json.dumps(
                    [
                        {
                            "Name": "Alpha",
                            "Duration": "3",
                            "_alignment": "full",
                            "_confidence": "high",
                            "_source_excerpt": "Alpha lasts 3 years.",
                        }
                    ]
                )
            )

    context = SimpleNamespace(workspace=workspace, judge_model=Judge(), budget_exhausted=False)
    monkeypatch.setattr(tasks, "_ctx", context)
    monkeypatch.setattr(schema, "_orch_ctx", lambda: context)
    result = json.loads(
        await tasks.extract_observation.ainvoke({"task_id": "duration", "observation_id": oid})
    )
    eid = result["evidence_ids"][0]
    assert calls and all("CELL_PROJECTION_REVIEW" not in call for call in calls)
    final = workspace.load_state()
    assert final.coverage_map.cells["programmes/Alpha.Duration"].value == "3"
    assert len(final.evidence_graph.nodes) == len(final.evidence_graph.observations) == 1
    assert final.evidence_graph.get_node(eid).source == observed.source
    assert final.evidence_graph.get_node(eid).table_id == ""
    assert final.evidence_graph.task_bindings[0].evidence_id == eid


@pytest.mark.asyncio
async def test_hybrid_automatic_table_reuse_binds_new_task_and_reports_actual_rows(tmp_path):
    from searchos.socm.workspace import WorkspaceManager

    workspace = WorkspaceManager(tmp_path, "automatic-table")
    workspace.create()
    state = SearchState(research_mode="findings", source_scope={"mode": "hybrid", "documents": []})
    state.coverage_map.add_table(
        "programmes", ["Name", "Credits"], primary_key=["Name"], entities=["Alpha"]
    )
    for task_id in ["first", "second"]:
        state.frontier.add(
            FrontierTask(
                id=task_id,
                question=f"Check credits for {task_id}",
                agent_type="search_agent",
                result_mode="table",
                table_id="programmes",
            )
        )
    workspace.save_state(state)

    class RowJudge:
        async def ainvoke(self, prompt):
            return SimpleNamespace(
                content=json.dumps(
                    [
                        {
                            "Name": "Alpha",
                            "Credits": "120",
                            "_source_excerpt": "Alpha requires 120 credits.",
                            "_alignment": "full",
                            "_confidence": "high",
                        }
                    ]
                )
            )

    receipts = []
    for task_id in ["first", "second"]:
        coordinator = ExtractionCoordinator(
            RowJudge(),
            workspace,
            commit_rows=ingest_facts,
            preparer=OriginalWindowPreparer(ExtractionConfig()),
            routing=SchemaRouting(),
        )
        receipts.append(
            await coordinator.submit(
                EvidenceObservation(
                    task_id=task_id,
                    target_table="programmes",
                    result_mode="table",
                    source_url="https://example.org/programme",
                    content="[Now viewing]\nL0: Official requirements for Alpha.\nL1: Alpha requires 120 credits.",
                ),
                delivery=DeliveryMode.SYNC,
            )
        )
        assert coordinator.committed_node_ids == frozenset(receipts[-1].committed_node_ids)
        assert receipts[-1].extraction_reports[0].committed_rows == 1
    state = workspace.load_state()
    assert len(state.evidence_graph.nodes) == len(state.evidence_graph.observations) == 1
    assert receipts[0].committed_node_ids == receipts[1].committed_node_ids
    assert {b.task_id for b in state.evidence_graph.task_bindings} == {"first", "second"}
    assert state.evidence_graph.nodes[0].table_id == ""
    assert state.coverage_map.cells["programmes/Alpha.Credits"].value == "120"


@pytest.mark.asyncio
@pytest.mark.parametrize("next_mode", ["hybrid", "web"])
async def test_reopened_followup_preserves_bindings_only_with_same_scope(
    observation_workspace, monkeypatch, next_mode
):
    from api.routes import search

    from searchos.socm.coverage import CellEvidenceBinding, bind_cell_evidence

    workspace, oid = observation_workspace
    state = workspace.load_state()
    state.coverage_map.add_table(
        "programmes", ["Name", "Credits"], primary_key=["Name"], entities=["Alpha"]
    )
    source = state.evidence_graph.observations[0].source
    state.evidence_graph.add_node(
        EvidenceNode(
            id="saved_fact",
            finding="Alpha requires 120 credits.",
            source=source,
            source_excerpt="Alpha requires 120 credits.",
            observation_id=oid,
        )
    )
    bind_cell_evidence(
        state,
        [("programmes/Alpha.Credits", CellEvidenceBinding(evidence_id="saved_fact", value="120"))],
    )
    bind_task_evidence(state, "duration", ["saved_fact"], relation="context")
    workspace.save_state(state)
    monkeypatch.setattr(search, "WORKSPACE_ROOT", str(workspace.path.parent))
    monkeypatch.setattr(search, "init_search_provider", lambda _: None)
    monkeypatch.setattr(search, "sessions", {})
    captured = {}

    async def launch(**kwargs):
        captured.update(kwargs)
        return search.SearchResponse(session_id=kwargs["session_id"], status="running")

    monkeypatch.setattr(search, "_launch_search", launch)
    await search.create_search(
        search.SearchRequest(
            query="Continue checking requirements",
            follow_up_to=workspace.session_id,
            sources={"mode": next_mode},
            history=[{"query": "Earlier question", "answer": "Earlier answer"}],
        )
    )
    restored = captured["state"]
    assert captured["session_id"] == workspace.session_id
    if next_mode == "hybrid":
        assert restored.evidence_graph.model_dump() == state.evidence_graph.model_dump()
        assert restored.coverage_map.model_dump() == state.coverage_map.model_dump()
        assert "Earlier answer" in captured["context_preamble"]
    else:
        assert not restored.evidence_graph.nodes and not restored.evidence_graph.observations
        assert (
            not restored.evidence_graph.task_bindings
            and not restored.coverage_map.evidence_bindings
        )
        assert not restored.coverage_map.tables
        assert "Earlier answer" not in (captured["context_preamble"] or "")
    assert workspace.load_state().evidence_graph.model_dump() == state.evidence_graph.model_dump()


@pytest.mark.asyncio
async def test_stall_sensor_waits_for_current_wave_before_stopping():
    from searchos.harness.middleware.extraction import InMemoryEvidenceStore
    from searchos.harness.middleware.sensor.core.coverage_stall_sensor import CoverageStallSensor

    state = SearchState(research_mode="findings")
    sensor = CoverageStallSensor(InMemoryEvidenceStore(state), max_stalled_rounds=1)
    report = {"kind": "search", "status": "completed", "agent_id": "ppt"}
    assert (
        await sensor.check(
            "check_agents",
            {"reports": [report], "remaining": 3, "running_ids": ["pdf", "web1", "web2"]},
        )
        is None
    )
    signal = await sensor.check("check_agents", {"reports": [report], "remaining": 0})
    assert signal["force_stop"] is True


def test_local_reading_activity_does_not_reset_no_progress_without_extraction():
    from types import SimpleNamespace

    from searchos.harness.middleware.sensor.core.models import ControlState
    from searchos.harness.middleware.sensor.progress_middleware import (
        ReadingProgressMiddleware,
        ToolProgressMiddleware,
    )

    sources = set()
    reading = ReadingProgressMiddleware(sources)
    progress = ToolProgressMiddleware(ControlState(), limit=3)
    delta = SimpleNamespace(coverage_gain=0, new_evidence_count=0)
    for page in range(1, 4):
        result = "[Now viewing local source] paper.pdf\nsource text"
        args = {"ref_id": f"local://doc/s{page}", "loc": 0}
        reading.observe("local_open", result, args)
        progress.observe("local_open", delta, result, args)
    assert len(sources) == 3
    assert progress.control.stopped


@pytest.mark.asyncio
async def test_table_mode_facts_bindings_and_reading_reset_stall():
    from searchos.harness.middleware.sensor.core.coverage_stall_sensor import CoverageStallSensor

    state = findings_state()
    state.research_mode = "table"
    store = InMemoryEvidenceStore(state)
    reads = set()
    sensor = CoverageStallSensor(store, max_stalled_rounds=1, source_progress=lambda: set(reads))
    report = {"reports": [{"kind": "search"}], "remaining": 0}
    state.evidence_graph.add_node(
        EvidenceNode(id="fact", finding="Supported", source="https://example.org")
    )
    assert await sensor.check("check_agents", report) is None
    bind_task_evidence(state, "local", ["fact"])
    assert await sensor.check("check_agents", report) is None
    reads.add("new-window")
    assert await sensor.check("check_agents", {**report, "remaining": 1}) is None
    assert await sensor.check("check_agents", report) is None
    assert (await sensor.check("check_agents", report))["force_stop"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["findings", "table_merged", "table_dual"])
async def test_extraction_retry_preserves_extraction_and_review_protocols(mode):
    from searchos.harness.middleware.extraction import ExtractionConfig

    state = findings_state()
    if mode != "findings":
        state.research_mode = "table"
        state.coverage_map.add_table(
            "programmes", ["Name", "Credits"], primary_key=["Name"], entities=["Alpha"]
        )
        state.frontier.questions[0].result_mode = "table"
        state.frontier.questions[0].table_id = "programmes"
    store = InMemoryEvidenceStore(state)
    prompts, attempts = {}, {}

    class FlakyJudge:
        async def ainvoke(self, prompt):
            # Reproduce the old fallback producing valid JSON with the wrong schema.
            if prompt.startswith("Summarize any factual claims"):
                return SimpleNamespace(
                    content=json.dumps(
                        [{"finding": "Alpha requires 120 credits.", "entity_hint": "Alpha"}]
                    )
                )
            if "核验每项事实" in prompt:
                stage = "review"
                rows = [{"id": "0", "supported": True}]
            elif "从给定原文抽取" in prompt:
                stage = "findings"
                rows = [
                    {
                        "finding": "Alpha requires 120 credits.",
                        "source_excerpt": "Alpha requires 120 credits.",
                        "relation": "supports",
                    }
                ]
            else:
                stage = (
                    "fill"
                    if "FILL MODE" in prompt
                    else "discover"
                    if "DISCOVER MODE" in prompt
                    else "merged"
                )
                rows = (
                    []
                    if stage == "discover"
                    else [
                        {
                            "Name": "Alpha",
                            "Credits": "120",
                            "_source_page": 1,
                            "_source_excerpt": "Alpha requires 120 credits.",
                            "_alignment": "full",
                            "_confidence": "high",
                        }
                    ]
                )
            prompts.setdefault(stage, []).append(prompt)
            attempts[stage] = attempts.get(stage, 0) + 1
            if attempts[stage] < 3:
                raise RuntimeError("synthetic transient failure")
            return SimpleNamespace(content=json.dumps(rows))

    coordinator = ExtractionCoordinator(
        FlakyJudge(),
        store,
        preparer=OriginalWindowPreparer(ExtractionConfig(dual_mode=mode == "table_dual")),
        routing=SchemaRouting(),
        commit_rows=ingest_facts,
        config=ExtractionConfig(dual_mode=mode == "table_dual"),
    )
    receipt = await coordinator.submit(observation(), delivery=DeliveryMode.SYNC)
    assert receipt.committed_node_ids
    assert all(len(values) == 3 and len(set(values)) == 1 for values in prompts.values())
    assert set(prompts) == (
        {"findings", "review"}
        if mode == "findings"
        else {"fill", "discover"}
        if mode == "table_dual"
        else {"merged"}
    )
    if mode == "findings":
        assert store.state.evidence_graph.task_bindings
        assert store.state.evidence_graph.observations
    else:
        assert store.state.coverage_map.cells["programmes/Alpha.Credits"].status.value == "filled"


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["failure", "cancel", "empty_array"])
async def test_extraction_retry_is_bounded_and_preserves_cancellation(outcome):
    import asyncio

    calls, events = [], []

    class Judge:
        async def ainvoke(self, prompt):
            calls.append(prompt)
            if outcome == "cancel":
                raise asyncio.CancelledError()
            if outcome == "failure":
                raise RuntimeError("synthetic failure")
            return SimpleNamespace(content="[]")

    coordinator = ExtractionCoordinator(
        Judge(),
        InMemoryEvidenceStore(findings_state()),
        preparer=OriginalWindowPreparer(ExtractionConfig()),
        routing=SchemaRouting(),
        commit_rows=ingest_facts,
        trajectory_logger=SimpleNamespace(_append_raw=events.append),
    )
    # Long context: retry must retain both the contract and the original source.
    prompt = "OUTPUT_CONTRACT_BEGIN\n" + "原文内容" * 2000 + "\nSOURCE_END"
    if outcome == "cancel":
        with pytest.raises(asyncio.CancelledError):
            await coordinator._extractor.invoke(prompt)
        assert calls == [prompt] and not events
    else:
        raw = await coordinator._extractor.invoke(prompt)
        assert raw == ("" if outcome == "failure" else "[]")
        assert calls == [prompt] * (3 if outcome == "failure" else 1)
        if outcome == "failure":
            assert events[-1]["kind"] == "judge_failed"
            assert not any(event["kind"] == "judge_degraded" for event in events)
