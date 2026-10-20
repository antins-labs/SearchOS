"""Exercise real direct-search workers with offline models and page data."""

import asyncio
import json
from types import SimpleNamespace
from typing import Any

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import tool
from pydantic import Field

from searchos.agents import runtime, search
from searchos.config.settings import settings
from searchos.harness.middleware.context.steering_middleware import SteeringMiddleware
from searchos.harness.middleware.sensor.budget_middleware import BudgetMiddleware
from searchos.harness.simple_search import run_simple_search
from searchos.harness.steering import SteeringMessage, SteeringQueue
from searchos.socm import SearchState, WorkspaceManager
from searchos.socm.evidence import EvidenceEdge, EvidenceRelation
from searchos.tools import search_state

URL = "https://example.org/widget-release?version=" + "a" * 150
FACT = "Widget was released in 2024."
ANSWER = f"{FACT} [Source]({URL})"


class OfflineModel(BaseChatModel):
    handler: Any = Field(exclude=True)
    calls: list = Field(default_factory=list, exclude=True)
    tool_names: list = Field(default_factory=list, exclude=True)

    @property
    def _llm_type(self):
        return "offline-simple-search"

    def bind_tools(self, tools, **kwargs):
        self.tool_names = [t.name for t in tools]
        return self

    def _generate(self, messages, **kwargs):
        raise AssertionError("Expected asynchronous execution")

    async def _agenerate(self, messages, **kwargs):
        self.calls.append(messages)
        message = await self.handler(len(self.calls), messages)
        return ChatResult(generations=[ChatGeneration(message=message)])


class Extraction:
    def __init__(self):
        self.calls = []

    async def ainvoke(self, prompt):
        self.calls.append(prompt)
        rows = ([{"id": "0", "supported": True}]
                if "Verify whether each fact" in prompt else
                [{"finding": FACT, "source_excerpt": FACT, "relation": "supports",
                  "source_urls": [URL]}])
        return SimpleNamespace(content=json.dumps(rows))


def call(name, args=None, *, number=1):
    return AIMessage(content="", tool_calls=[{
        "name": name, "args": args or {}, "id": f"call-{number}",
    }])


@pytest.fixture
def setup(tmp_path, monkeypatch):
    for setting in ("enable_skills", "enable_failure_memory", "enable_writer_agent",
                    "enable_explore"):
        monkeypatch.setattr(settings, setting, False)
    monkeypatch.setattr(settings, "middleware_pipelines", {})
    monkeypatch.setattr(settings, "research_finalize_timeout_s", .5)
    workspace = WorkspaceManager(tmp_path, "simple")
    workspace.create()
    state = SearchState(intent="When was Widget released?",
                        source_scope={"mode": "web", "documents": []})
    workspace.save_state(state)
    search_state.set_workspace(workspace)
    token = search_state._source_scope_var.set(state.source_scope)

    @tool("open")
    async def open_page(url: str) -> str:
        """Read an original publication."""
        assert url == URL
        return (f"[Now viewing]\nURL: {URL}\n\nL1: Official release announcement. "
                f"{FACT} The publication describes the original release date and its scope.")

    monkeypatch.setattr(search, "get_tools", lambda *args: [open_page])

    def configure(handler):
        model = OfflineModel(handler=handler)
        extraction = Extraction()
        runtime.set_orchestrator_context(
            workspace=workspace, model=model, sub_agent_model=model,
            extraction_model=extraction,
        )
        return workspace, model, extraction

    yield configure
    search_state._source_scope_var.reset(token)


@pytest.fixture(params=[False, True], ids=["search", "explore"])
def retrieval_mode(setup, request, monkeypatch):
    from searchos.agents import explore

    original_tools = explore.get_tools
    # 保留真实 pipeline 和工具集合，只把原文获取替换为本文件的离线页面。
    def offline_tools(*args, **kwargs):
        original_open = next(t for t in search.get_tools() if t.name == "open")
        return [original_open if t.name == "open" else t for t in original_tools(*args, **kwargs)]

    monkeypatch.setattr(explore, "get_tools", offline_tools)
    monkeypatch.setattr(settings, "enable_explore", request.param)
    yield request.param


async def run(workspace, **kwargs):
    return await run_simple_search(
        workspace=workspace, query="When was Widget released?",
        evidence_obligations=["Verify the release year from the original publication"],
        remaining_time_s=kwargs.pop("remaining_time_s", 10), **kwargs,
    )


@pytest.mark.asyncio
async def test_simple_path_uses_real_extraction_and_preserves_original_url(setup):
    async def handler(count, messages):
        return (call("open", {"url": URL}) if count == 1
                else AIMessage(content=ANSWER))

    workspace, model, extraction = setup(handler)
    before_agent = search_state._current_agent_var.get()
    outcome = await run(workspace)
    assert not outcome.escalate, outcome.reason
    assert outcome.answer == ANSWER
    assert len(model.calls) == 2 and extraction.calls
    assert "escalate_to_research" in model.tool_names
    assert not {"enqueue_tasks", "create_schema", "explore_web"} & set(model.tool_names)
    state = workspace.load_state()
    assert not state.coverage_map.tables
    task = state.frontier.questions[0]
    assert task.status.value == "completed" and task.result_mode == "findings"
    nodes = state.evidence_graph.nodes
    assert any(node.source == URL and node.source_excerpt == FACT for node in nodes)
    assert any(o.source == URL for o in state.evidence_graph.observations)
    assert any(b.task_id == task.id for b in state.evidence_graph.task_bindings)
    info = next(iter(runtime._ctx.agent_graphs.values()))
    budget = next(m.budget for m in info["graph"].middleware if isinstance(m, BudgetMiddleware))
    assert (budget.max_queries, budget.max_iterations, budget.max_time_s) == (15, 0, 10)
    assert not runtime._ctx.task_pool
    assert search_state._current_agent_var.get() == before_agent
    assert not (workspace.path / "output" / "report.md").exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("answer", [
    ANSWER,
    "I could not establish the release year.",
    FACT,
    ANSWER + " The required date remains unverified.",
    "Fact [source](https://invented.example/article)",
])
async def test_answer_format_and_citations_do_not_trigger_research(setup, answer):
    async def handler(count, messages):
        return call("open", {"url": URL}) if count == 1 else AIMessage(content=answer)

    workspace, _, _ = setup(handler)
    outcome = await run(workspace)
    assert not outcome.escalate and not outcome.reason
    assert outcome.answer == answer
    state = workspace.load_state()
    assert state.evidence_graph.nodes and state.frontier.questions[0].status.value == "completed"
    assert not runtime._ctx.task_pool


@pytest.mark.asyncio
async def test_missing_committed_evidence_does_not_automatically_escalate(setup):
    async def handler(count, messages):
        return AIMessage(content=ANSWER)

    workspace, _, _ = setup(handler)
    # Even when the normal summary extractor accepts this text, it must not
    # create original-source support out of an unread source.
    outcome = await run(workspace)
    assert not outcome.escalate
    assert not any(o.source == URL for o in workspace.load_state().evidence_graph.observations)


@pytest.mark.asyncio
async def test_explicit_upgrade_after_deadline_preserves_evidence_and_runtime(
    setup, retrieval_mode,
):
    async def handler(count, messages):
        if count == 1:
            return call("open", {"url": URL})
        if count == 2:
            await asyncio.sleep(.2)
            return call("escalate_to_research", {"reason": "Need all related releases"}, number=2)
        return AIMessage(content=ANSWER + " Need to enumerate the other releases.")

    workspace, _, _ = setup(handler)
    registry = runtime._ctx.agent_graphs
    counter = runtime._session_search_count_var.get()
    outcome = await run(workspace, remaining_time_s=.15)
    assert outcome.escalate and outcome.reason == "Need all related releases"
    assert runtime._ctx.agent_graphs is registry
    assert runtime._session_search_count_var.get() is counter
    assert workspace.load_state().evidence_graph.observations
    assert not runtime._ctx.task_pool


@pytest.mark.asyncio
@pytest.mark.parametrize("handoff", [False, True], ids=["answer", "handoff"])
async def test_late_retrieval_is_blocked_without_replacing_agent_decision(
    setup, retrieval_mode, handoff,
):
    async def handler(count, messages):
        if count == 1:
            return call("open", {"url": URL})
        if count == 2:
            await asyncio.sleep(.2)
            # The real tool rejects this URL if the expired request reaches it.
            return call("open", {"url": "https://example.org/must-not-fetch"}, number=2)
        if count == 3:
            assert any(getattr(message, "tool_call_id", "") == "call-2"
                       and "blocked" in message.content for message in messages)
            if handoff:
                return call("escalate_to_research", {"reason": "Need release month"}, number=3)
        return AIMessage(content=ANSWER)

    workspace, model, _ = setup(handler)
    outcome = await run(workspace, remaining_time_s=.15)
    assert outcome.answer == ANSWER
    assert outcome.escalate is handoff
    assert outcome.reason == ("Need release month" if handoff else "")
    assert len(model.calls) == (4 if handoff else 3)
    assert not runtime._ctx.task_pool


@pytest.mark.asyncio
async def test_early_handoff_is_rejected_without_starting_research(setup, retrieval_mode):
    async def handler(count, messages):
        if count == 1:
            return call("escalate_to_research", {"reason": "Need another source"})
        assert any(getattr(message, "name", "") == "escalate_to_research"
                   and "Search time remains" in message.content for message in messages)
        return AIMessage(content=ANSWER)

    workspace, _, _ = setup(handler)
    outcome = await run(workspace)
    assert not outcome.escalate and outcome.answer == ANSWER


@pytest.mark.asyncio
async def test_complete_answer_after_deadline_does_not_escalate(setup, retrieval_mode):
    async def handler(count, messages):
        if count == 1:
            return call("open", {"url": URL})
        await asyncio.sleep(.2)
        return AIMessage(content=ANSWER)

    workspace, _, _ = setup(handler)
    outcome = await run(workspace, remaining_time_s=.15)
    assert not outcome.escalate and outcome.answer == ANSWER


@pytest.mark.asyncio
async def test_extraction_retry_buffer_does_not_escalate(setup, monkeypatch):
    async def handler(count, messages):
        return call("open", {"url": URL}) if count == 1 else AIMessage(content=ANSWER)

    workspace, _, extraction = setup(handler)

    async def malformed(_):
        return SimpleNamespace(content="invalid extraction output")

    monkeypatch.setattr(extraction, "ainvoke", malformed)
    outcome = await run(workspace)
    assert not outcome.escalate and outcome.answer == ANSWER
    resources = next(iter(runtime._ctx.agent_graphs.values()))["extractions"]
    assert any(resource.summary().buffered for resource in resources)


@pytest.mark.asyncio
async def test_worker_error_is_reported_without_starting_research(setup):
    async def handler(count, messages):
        raise RuntimeError("offline model failed")

    workspace, _, _ = setup(handler)
    with pytest.raises(RuntimeError, match="failed to return an answer"):
        await run(workspace)
    assert not runtime._ctx.task_pool


@pytest.mark.asyncio
async def test_active_conflict_does_not_automatically_escalate(setup):
    async def handler(count, messages):
        if count == 1:
            return call("open", {"url": URL})
        await next(iter(runtime._ctx.agent_graphs.values()))["extraction"].flush()
        state = workspace.load_state()
        node = state.evidence_graph.nodes[0]
        peer = node.model_copy(update={"id": "other", "finding": "Widget released in 2025.",
                                       "source": "https://example.org/correction"})
        state.evidence_graph.add_node(peer)
        state.evidence_graph.add_edge(EvidenceEdge(
            from_id=node.id, to_id=peer.id, relation=EvidenceRelation.CONFLICT,
        ))
        workspace.save_state(state)
        return AIMessage(content=ANSWER)

    workspace, _, _ = setup(handler)
    outcome = await run(workspace)
    assert not outcome.escalate


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["immediate", "after_tool"])
async def test_live_follow_up_is_consumed_once_without_automatic_upgrade(
    setup, mode, retrieval_mode,
):
    inbox = SteeringQueue()
    entered = asyncio.Event()
    release = asyncio.Event()
    delivered = []

    async def handler(count, messages):
        if count == 1:
            return call("open", {"url": URL})
        if count == 2:
            entered.set()
            await release.wait()
        return AIMessage(content=ANSWER)

    workspace, model, _ = setup(handler)
    pending = asyncio.create_task(run(workspace, steer_queue=inbox,
                                     on_steer_delivery=delivered.append))
    await asyncio.wait_for(entered.wait(), timeout=5)
    follow_up = SteeringMessage("List every release", mode=mode)
    inbox.put_nowait(follow_up)
    release.set()
    outcome = await asyncio.wait_for(pending, timeout=5)
    assert not outcome.escalate
    assert outcome.delivered == ["List every release"]
    assert inbox.empty()
    assert len(delivered) == 1
    assert delivered[0].id == f"steer-{follow_up.id}"
    assert delivered[0].additional_kwargs == {
        "sf_steer_id": follow_up.id, "sf_steer_mode": mode, "sf_steer_text": follow_up.text,
    }
    assert sum("List every release" in str(message.content)
               for message in model.calls[-1] if message.type == "human") == 1


@pytest.mark.asyncio
async def test_steering_callback_is_ready_before_worker_starts(setup, retrieval_mode):
    from searchos.harness.telemetry.conversation import langchain_msg_to_conversation_msgs

    inbox = SteeringQueue()
    follow_up = SteeringMessage("Keep the original source", mode="after_tool")
    inbox.put_nowait(follow_up)
    conversation = []

    def record(message):
        conversation.extend(langchain_msg_to_conversation_msgs(message))

    async def handler(count, messages):
        assert len(conversation) == 1, "Queued input must be recorded before the first model call"
        return call("open", {"url": URL}) if count == 1 else AIMessage(content=ANSWER)

    workspace, _, _ = setup(handler)
    outcome = await run(workspace, steer_queue=inbox, on_steer_delivery=record)
    assert not outcome.escalate
    assert outcome.delivered == [follow_up.text]
    assert conversation[0].metadata["steer_id"] == follow_up.id
    assert conversation[0].metadata["steer_mode"] == follow_up.mode
    assert conversation[0].metadata["steer_text"] == follow_up.text


@pytest.mark.asyncio
@pytest.mark.parametrize("stop", ["cancel", "timeout"])
async def test_cancel_and_timeout_cleanup_worker_without_erasing_evidence(
    setup, stop, retrieval_mode,
):
    entered = asyncio.Event()

    async def handler(count, messages):
        if count == 1:
            return call("open", {"url": URL})
        entered.set()
        await asyncio.Event().wait()

    workspace, _, _ = setup(handler)
    pending = asyncio.create_task(run(workspace, remaining_time_s=.2 if stop == "timeout" else 10))
    await asyncio.wait_for(entered.wait(), timeout=5)
    if stop == "cancel":
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending
    else:
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(pending, timeout=5)
    assert workspace.load_state().evidence_graph.nodes
    assert workspace.load_state().frontier.questions[0].status.value == "cancelled"
    assert not runtime._ctx.task_pool


@pytest.mark.parametrize("pipeline_name", ["web_search", "explore", "local_search"])
def test_optional_worker_steering_survives_middleware_customization(
    setup, monkeypatch, pipeline_name,
):
    from searchos.harness.middleware import pipelines
    from searchos.harness.middleware.models import TaskContext

    web_search_pipeline = getattr(pipelines, pipeline_name + "_pipeline")

    async def handler(count, messages):
        return AIMessage(content="done")

    workspace, model, _ = setup(handler)
    monkeypatch.setattr(settings, "middleware_pipelines", {pipeline_name: []})
    graph = web_search_pipeline(model, [], workspace=workspace, task=TaskContext("direct"),
                                steer_queue=SteeringQueue(), enforce_budget=True)
    assert sum(isinstance(m, SteeringMiddleware) for m in graph.middleware) == 1
    assert sum(isinstance(m, BudgetMiddleware) for m in graph.middleware) == 1
    ordinary = web_search_pipeline(model, [], workspace=workspace, task=TaskContext("research"))
    assert not any(isinstance(m, SteeringMiddleware) for m in ordinary.middleware)


@pytest.mark.asyncio
async def test_direct_worker_has_no_separate_eight_turn_limit(setup, monkeypatch):
    executed = []

    @tool("open")
    async def open_page(url: str) -> str:
        """Read the next page."""
        executed.append(url)
        return "A page without useful evidence."

    async def handler(count, messages):
        return (call("open", {"url": f"https://example.org/{count}"}, number=count)
                if count <= 9 else AIMessage(content="The requested search is complete."))

    workspace, model, _ = setup(handler)
    monkeypatch.setattr(search, "get_tools", lambda *args: [open_page])
    monkeypatch.setattr(settings, "middleware_pipelines", {"web_search": ["BudgetMiddleware"]})
    outcome = await run(workspace)
    assert not outcome.escalate
    assert len(executed) == 9
    assert len(model.calls) == 10
