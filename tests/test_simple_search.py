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


@pytest.fixture(params=[False, True], ids=["explore-disabled", "explore-enabled"])
def retrieval_mode(setup, request, monkeypatch):
    monkeypatch.setattr(settings, "enable_explore", request.param)
    yield request.param


async def run(workspace, **kwargs):
    return await run_simple_search(
        workspace=workspace, query="When was Widget released?",
        evidence_obligations=["Verify the release year from the original publication"],
        remaining_time_s=kwargs.pop("remaining_time_s", 10), **kwargs,
    )


@pytest.mark.asyncio
async def test_simple_path_uses_real_extraction_and_preserves_original_url(setup, retrieval_mode):
    async def handler(count, messages):
        return (call("open", {"url": URL}) if count == 1
                else AIMessage(content=ANSWER))

    workspace, model, extraction = setup(handler)
    before_agent = search_state._current_agent_var.get()
    outcome = await run(workspace)
    assert outcome.answer == ANSWER
    assert len(model.calls) == 2 and extraction.calls
    assert "escalate_to_research" not in model.tool_names
    assert not {"enqueue_tasks", "create_schema", "explore_web"} & set(model.tool_names)
    state = workspace.load_state()
    assert not state.coverage_map.tables
    task = state.frontier.questions[0]
    assert task.agent_type == "search_agent"
    assert task.status.value == "completed"
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
async def test_quick_search_collects_failure_and_projects_it_on_next_model_call(
    setup, retrieval_mode, monkeypatch,
):
    from searchos.tools.simple_browser import tools as browser_tools

    query = "Widget release year exact phrase"

    class EmptyProvider:
        name = "offline-empty"

        async def search(self, query, max_results):
            return []

    monkeypatch.setattr(settings, "enable_failure_memory", True)
    monkeypatch.setattr(settings, "enable_socm_projection", True)
    monkeypatch.setattr(settings, "enable_explore_batch", False)
    monkeypatch.setattr(browser_tools, "get_provider", lambda: EmptyProvider())
    original_open = next(tool for tool in search.get_tools() if tool.name == "open")
    monkeypatch.setattr(search, "get_tools", lambda *args: [browser_tools.search, original_open])

    async def handler(count, messages):
        assert messages[0].type == "system"
        context = "\n".join(message.content for message in messages if message.type == "system")
        if count == 1:
            assert "Failure memory:" not in context
            return call("search", {"query": query})
        assert context.count("Failure memory:") == 1
        assert query in context and "offline-empty" in context
        return call("open", {"url": URL}, number=2) if count == 2 else AIMessage(content=ANSWER)

    workspace, model, _ = setup(handler)
    outcome = await run(workspace)
    assert outcome.answer == ANSWER and len(model.calls) == 3
    state = workspace.load_state()
    assert state.evidence_graph.observations
    assert len(state.failure_memory.records) == 1
    memory = state.failure_memory.records[0]
    task = state.frontier.questions[0]
    assert memory.kind.value == "query" and memory.target == query
    assert memory.scope.task_id == task.id and memory.observation_ids == [f"{task.id}:{task.attempts}:call-1"]
    info = next(iter(runtime._ctx.agent_graphs.values()))
    checkpoint = await info["graph"].aget_state({"configurable": {"thread_id": info["thread_id"]}})
    snapshots = [message for message in checkpoint.values["messages"]
                 if message.additional_kwargs.get("sf_kind") == "socm_update"]
    assert len(snapshots) == 1 and snapshots[0].id == "socm-current"
    assert query in snapshots[0].content


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
    assert outcome.answer == ANSWER
    assert not any(o.source == URL for o in workspace.load_state().evidence_graph.observations)


@pytest.mark.asyncio
async def test_deadline_injects_one_user_summary_and_preserves_evidence_and_runtime(
    setup, retrieval_mode, monkeypatch,
):
    import time

    async def handler(count, messages):
        if count == 1:
            return call("open", {"url": URL})
        if count == 2:
            info = next(iter(runtime._ctx.agent_graphs.values()))
            budget = next(m.budget for m in info["graph"].middleware if isinstance(m, BudgetMiddleware))
            budget._start_ts = time.time() - 61
            return AIMessage(content="I have partial findings.")
        summaries = [m for m in messages if m.additional_kwargs.get("sf_kind") == "budget_summary"]
        assert len(summaries) == 1 and summaries[0].type == "human"
        assert messages[-1] == summaries[0]
        assert any(m.type == "tool" for m in messages)
        return AIMessage(content=ANSWER + " Need to enumerate the other releases.")

    workspace, _, _ = setup(handler)
    registry = runtime._ctx.agent_graphs
    counter = runtime._session_search_count_var.get()
    outcome = await run(workspace, remaining_time_s=60)
    assert outcome.answer == ANSWER + " Need to enumerate the other releases."
    assert runtime._ctx.agent_graphs is registry
    assert runtime._session_search_count_var.get() is counter
    assert workspace.load_state().evidence_graph.observations
    assert not runtime._ctx.task_pool


@pytest.mark.asyncio
async def test_current_tool_round_finishes_before_summary(
    setup, retrieval_mode,
):
    async def handler(count, messages):
        if count == 1:
            return call("open", {"url": URL})
        if count == 2:
            await asyncio.sleep(.2)
            return call("open", {"url": URL}, number=2)
        if count == 3:
            assert any(getattr(message, "tool_call_id", "") == "call-2"
                       and FACT in message.content for message in messages)
            assert messages[-1].additional_kwargs.get("sf_kind") == "budget_summary"
        return AIMessage(content=ANSWER)

    workspace, model, _ = setup(handler)
    outcome = await run(workspace, remaining_time_s=.15)
    assert outcome.answer == ANSWER
    assert len(model.calls) == 3
    assert not runtime._ctx.task_pool


@pytest.mark.asyncio
async def test_no_handoff_tool_is_exposed(setup, retrieval_mode):
    async def handler(count, messages):
        return AIMessage(content=ANSWER)

    workspace, model, _ = setup(handler)
    outcome = await run(workspace)
    assert outcome.answer == ANSWER
    assert "escalate_to_research" not in model.tool_names


@pytest.mark.asyncio
async def test_complete_answer_after_deadline_does_not_escalate(setup, retrieval_mode):
    async def handler(count, messages):
        if count == 1:
            return call("open", {"url": URL})
        await asyncio.sleep(.2)
        return AIMessage(content=ANSWER)

    workspace, _, _ = setup(handler)
    outcome = await run(workspace, remaining_time_s=.15)
    assert outcome.answer == ANSWER


@pytest.mark.asyncio
async def test_extraction_retry_buffer_does_not_escalate(setup, monkeypatch):
    async def handler(count, messages):
        return call("open", {"url": URL}) if count == 1 else AIMessage(content=ANSWER)

    workspace, _, extraction = setup(handler)

    async def malformed(_):
        return SimpleNamespace(content="invalid extraction output")

    monkeypatch.setattr(extraction, "ainvoke", malformed)
    outcome = await run(workspace)
    assert outcome.answer == ANSWER
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
    assert outcome.answer == ANSWER


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
    assert outcome.answer == ANSWER
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
    assert outcome.answer == ANSWER
    assert outcome.delivered == [follow_up.text]
    assert conversation[0].metadata["steer_id"] == follow_up.id
    assert conversation[0].metadata["steer_mode"] == follow_up.mode
    assert conversation[0].metadata["steer_text"] == follow_up.text


@pytest.mark.asyncio
async def test_user_cancel_cleans_up_worker_without_erasing_evidence(
    setup, retrieval_mode,
):
    entered = asyncio.Event()

    async def handler(count, messages):
        if count == 1:
            return call("open", {"url": URL})
        entered.set()
        await asyncio.Event().wait()

    workspace, _, _ = setup(handler)
    pending = asyncio.create_task(run(workspace))
    await asyncio.wait_for(entered.wait(), timeout=5)
    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        await pending
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
    assert outcome.answer == "The requested search is complete."
    assert len(executed) == 9
    assert len(model.calls) == 10
