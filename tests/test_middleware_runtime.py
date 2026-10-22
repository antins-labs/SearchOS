"""通过公开图入口验证组件资源，不要求调用方装配生命周期。"""

import asyncio
from contextlib import aclosing

import pytest
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage
from langchain_core.tools import tool

from searchos.agents.execution import _ManagedGraph, _run_resources
from searchos.agents.runtime import create_search_agent_graph
from searchos.harness.middleware import (
    BudgetMiddleware,
    BudgetState,
    ControlState,
    DynamicTrimMiddleware,
    FinalSummaryEvidenceMiddleware,
    LocalEvidenceMiddleware,
    SOCMContextMiddleware,
    TaskContext,
    WebEvidenceMiddleware,
)
from searchos.harness.middleware.extraction import ExtractionReceipt, InMemoryEvidenceStore
from searchos.socm import SearchState


class Model(FakeMessagesListChatModel):
    def bind_tools(self, tools, **kwargs):
        return self


class Extraction:
    def __init__(self):
        self.task = TaskContext(agent_id="reader")
        self.observations = []
        self.finalizations = 0
        self.waits = 0

    async def submit(self, observation, **kwargs):
        self.observations.append(observation)
        return ExtractionReceipt(accepted=True)

    async def drain_before_model(self):
        self.waits += 1

    async def finalize(self, *, timeout):
        await asyncio.sleep(0)
        self.finalizations += 1


@tool
def open() -> str:
    """Read a web source."""
    return (
        "[Now viewing] Report\nURL: https://example.org/report\n\n"
        "Alpha requires 120 credits. This is the complete programme record."
    )


def make_graph(extraction, *, middleware=None, responses=None, tools=None, **runtime_options):
    return create_search_agent_graph(
        model=Model(responses=responses or [AIMessage(content="Completed reading " * 5)]),
        tools=[open] if tools is None else tools,
        middleware=middleware if middleware is not None else [WebEvidenceMiddleware(extraction)],
        **runtime_options,
    )


@pytest.mark.asyncio
async def test_components_run_with_runtime_control():
    extraction = Extraction()
    control = ControlState()
    state = SearchState()
    state.coverage_map.add_table("t", ["Name", "Credits"], primary_key=["Name"], entities=["Alpha"])
    graph = make_graph(
        extraction,
        middleware=[
            BudgetMiddleware(BudgetState(), control=control),
            WebEvidenceMiddleware(extraction),
            SOCMContextMiddleware(InMemoryEvidenceStore(state), task=extraction.task),
            DynamicTrimMiddleware(max_tokens=6000),
        ],
        responses=[
            AIMessage(content="", tool_calls=[{"name": "open", "args": {}, "id": "read"}]),
            AIMessage(content="Alpha requires 120 credits."),
        ],
    )
    result = await graph.ainvoke(
        {"messages": [("user", "Read credits")]},
        {"configurable": {"thread_id": "five"}},
    )
    assert result["messages"][-1].content == "Alpha requires 120 credits."
    assert len(extraction.observations) == 1
    assert extraction.waits == 2
    assert extraction.finalizations == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["ainvoke", "astream", "astream_events"])
async def test_shared_extraction_finalizes_once_with_config_binding(method):
    extraction = Extraction()
    graph = make_graph(
        extraction,
        middleware=[
            WebEvidenceMiddleware(extraction),
            LocalEvidenceMiddleware(extraction),
            FinalSummaryEvidenceMiddleware(extraction),
        ],
    ).with_config({"configurable": {"thread_id": method}})
    if method == "ainvoke":
        await graph.ainvoke({"messages": [("user", "Read")]})
    else:
        kwargs = {"version": "v2"} if method == "astream_events" else {}
        async for _ in getattr(graph, method)({"messages": [("user", "Read")]}, **kwargs):
            pass
    assert extraction.finalizations == 1
    assert len(extraction.observations) == 1
    assert extraction.observations[0].source_kind.value == "agent_summary"


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["error", "cancel"])
async def test_real_graph_finalizes_on_failed_model(outcome):
    extraction = Extraction()
    started = asyncio.Event()

    class FailingModel(Model):
        async def _agenerate(self, *args, **kwargs):
            started.set()
            if outcome == "error":
                raise RuntimeError("model failed")
            await asyncio.Event().wait()

    graph = create_search_agent_graph(
        model=FailingModel(responses=[AIMessage(content="unused")]),
        tools=[open],
        middleware=[WebEvidenceMiddleware(extraction), FinalSummaryEvidenceMiddleware(extraction)],
    )
    task = asyncio.create_task(
        graph.ainvoke(
            {"messages": [("user", "Read")]},
            {"configurable": {"thread_id": outcome}},
        )
    )
    await asyncio.wait_for(started.wait(), timeout=5)
    if outcome == "cancel":
        task.cancel()
    with pytest.raises(RuntimeError if outcome == "error" else asyncio.CancelledError):
        await task
    assert extraction.finalizations == 1
    assert extraction.observations == []


@pytest.mark.asyncio
async def test_close_stream_finalizes_before_return():
    extraction = Extraction()
    graph = make_graph(extraction)
    async with aclosing(
        graph.astream(
            {"messages": [("user", "Read")]},
            {"configurable": {"thread_id": "close"}},
            stream_mode="values",
        )
    ) as stream:
        await anext(stream)
    assert extraction.finalizations == 1


@pytest.mark.asyncio
async def test_all_resources_finalize_even_if_one_fails_and_cancellation_repeats():
    started, release = asyncio.Event(), asyncio.Event()
    completed = []

    class FailedResource:
        async def finalize(self, *, timeout):
            raise RuntimeError("first failed")

    class SlowResource:
        async def finalize(self, *, timeout):
            started.set()
            await release.wait()
            completed.append(True)

    async def run():
        async with _run_resources([FailedResource(), SlowResource()], 1):
            pass

    task = asyncio.create_task(run())
    await started.wait()
    task.cancel()
    await asyncio.sleep(0)
    task.cancel()
    release.set()
    with pytest.raises(asyncio.CancelledError) as failure:
        await task
    assert completed == [True]
    assert "first failed" in " ".join(failure.value.__notes__)


def test_empty_list_does_not_install_resource_manager():
    assert not isinstance(make_graph(None, middleware=[]), _ManagedGraph)


@pytest.mark.asyncio
async def test_direct_list_shares_stop_state_with_socm_without_callback():
    control = ControlState(forced=True, reason="budget_exhausted")
    state = SearchState()
    state.coverage_map.add_table("t", ["Name", "Credits"], primary_key=["Name"], entities=["Alpha"])
    socm = SOCMContextMiddleware(InMemoryEvidenceStore(state), task=TaskContext("reader"))
    graph = make_graph(None, middleware=[socm], control=control)
    result = await graph.ainvoke(
        {"messages": [("user", "Read")]},
        {"configurable": {"thread_id": "stopped"}},
    )
    assert socm.control is control
    snapshots = [
        m.content for m in result["messages"] if m.additional_kwargs.get("sf_kind") == "socm_update"
    ]
    assert len(snapshots) == 1
    assert control.context_snapshot
    assert "Continue your assigned task" not in snapshots[0]


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["web", "local", "orchestrator"])
async def test_default_pipelines_run_through_same_graph_entry(mode, monkeypatch):
    from searchos.config.settings import settings
    from searchos.harness.middleware import (
        local_search_pipeline,
        orchestrator_pipeline,
        web_search_pipeline,
    )
    from tests.test_middleware_composition import FindingsJudge

    monkeypatch.setattr(settings, "use_layered_context", False)
    workspace = InMemoryEvidenceStore(SearchState(research_mode="findings"))
    from searchos.socm import FrontierTask

    workspace.state.frontier.add(
        FrontierTask(id="task", question="Credits?", result_mode="findings")
    )
    kwargs = dict(
        model=Model(
            responses=[
                AIMessage(content="Alpha requires 120 credits. The programme takes four years.")
            ]
        ),
        tools=[open],
        workspace=workspace,
    )
    if mode == "orchestrator":
        graph = orchestrator_pipeline(**kwargs)
        assert not isinstance(graph, _ManagedGraph)
    else:
        pipeline = web_search_pipeline if mode == "web" else local_search_pipeline
        graph = pipeline(
            **kwargs,
            task=TaskContext(agent_id=mode, task_id="task"),
            extraction_model=FindingsJudge(),
            final_summary=True,
        )
    await graph.ainvoke({"messages": [("user", "Credits?")]}, {"configurable": {"thread_id": mode}})
    if mode != "orchestrator":
        assert len(workspace.state.evidence_graph.nodes) == 1
        assert workspace.state.evidence_graph.nodes[0].source == f"agent://{mode}/final_summary"
        assert not any(workspace.pending_by_owner.values())


@pytest.mark.asyncio
async def test_summary_observes_early_explore_completion_once():
    from searchos.agents.explore.policy import ExplorePolicy

    extraction = Extraction()
    control = ControlState()
    graph = make_graph(
        extraction,
        middleware=[
            FinalSummaryEvidenceMiddleware(extraction),
        ],
        policy=ExplorePolicy(max_waves=3, control=control),
        control=control,
        responses=[
            AIMessage(content="Supported early findings from the supplied source. " * 3),
            AIMessage(content="Unexpected second model call. " * 2),
        ],
    )
    await graph.ainvoke(
        {"messages": [("user", "Explore")]}, {"configurable": {"thread_id": "retry"}}
    )
    assert len(extraction.observations) == 1
    assert extraction.observations[0].content.startswith("Supported early")
    assert extraction.finalizations == 1


@pytest.mark.asyncio
async def test_independent_graphs_do_not_finalize_each_others_resources():
    first, second = Extraction(), Extraction()
    graphs = [make_graph(first), make_graph(second)]
    await asyncio.gather(
        *(
            graph.ainvoke(
                {"messages": [("user", "Read")]},
                {"configurable": {"thread_id": str(i)}},
            )
            for i, graph in enumerate(graphs)
        )
    )
    assert first.finalizations == second.finalizations == 1
    assert first.waits == second.waits == 1


@pytest.mark.asyncio
async def test_close_event_stream_waits_for_cleanup():
    extraction = Extraction()
    graph = make_graph(extraction)
    async with aclosing(
        graph.astream_events(
            {"messages": [("user", "Read")]},
            {"configurable": {"thread_id": "events-close"}},
            version="v2",
        )
    ) as stream:
        await anext(stream)
    assert extraction.finalizations == 1


@pytest.mark.parametrize("method", ["invoke", "stream"])
def test_sync_graph_calls_use_the_same_cleanup(method):
    extraction = Extraction()
    graph = make_graph(extraction)
    result = getattr(graph, method)(
        {"messages": [("user", "Read")]},
        {"configurable": {"thread_id": method}},
    )
    if method == "stream":
        list(result)
    assert extraction.finalizations == 1


@pytest.mark.asyncio
async def test_resource_wrapper_preserves_graph_and_schema_inspection():
    graph = make_graph(Extraction())
    assert graph.get_graph().nodes.keys() == graph.graph.get_graph().nodes.keys()
    assert (await graph.aget_graph()).nodes.keys() == (await graph.graph.aget_graph()).nodes.keys()
    assert graph.get_input_schema() is graph.graph.get_input_schema()
    # 验证无 deepagents 附加状态的图也保留输入和输出 schema。
    from langgraph.graph import END, START, StateGraph
    from typing_extensions import TypedDict

    class State(TypedDict):
        messages: list

    builder = StateGraph(State)
    builder.add_node("pass", lambda state: state)
    builder.add_edge(START, "pass")
    builder.add_edge("pass", END)
    compiled = builder.compile()
    managed = _ManagedGraph(compiled, (), 1)
    assert managed.get_input_schema() is compiled.get_input_schema()
    assert managed.get_output_schema() is compiled.get_output_schema()


@pytest.mark.asyncio
async def test_session_logger_records_tools_without_business_middleware(tmp_path):
    import json

    from searchos.harness.telemetry.episodic import TrajectoryLogger

    path = tmp_path / "trajectory.jsonl"
    logger = TrajectoryLogger(path)
    graph = make_graph(
        None,
        middleware=[],
        trajectory_logger=logger,
        agent_id="reader",
        responses=[
            AIMessage(content="", tool_calls=[{"name": "open", "args": {}, "id": "read"}]),
            AIMessage(content="Done"),
        ],
    )
    await graph.ainvoke({"messages": [("user", "Read")]}, {"configurable": {"thread_id": "logs"}})
    assert graph.middleware == []
    records = [json.loads(line) for line in path.read_text().splitlines()]
    steps = [row for row in records if row["type"] == "step"]
    assert len(steps) == 1
    assert steps[0]["agent"] == "reader"
    assert steps[0]["action"]["name"] == "open"
    assert "120 credits" in steps[0]["observation"]


@pytest.mark.asyncio
@pytest.mark.parametrize("loaded", [False, True])
async def test_runtime_enforces_only_budget_signals_from_loaded_sensor(loaded):
    calls = []

    @tool
    def read() -> str:
        """Read a source."""
        calls.append(True)
        return "Source content"

    control = ControlState()
    sensors = [BudgetMiddleware(BudgetState(max_iterations=1), control)] if loaded else []
    graph = make_graph(
        None,
        middleware=sensors,
        tools=[read],
        control=control,
        responses=[
            AIMessage(content="", tool_calls=[{"name": "read", "args": {}, "id": "r"}]),
            AIMessage(content="Done"),
        ],
    )
    result = await graph.ainvoke(
        {"messages": [("user", "Read")]}, {"configurable": {"thread_id": "budget"}}
    )
    assert bool(calls) is not loaded
    assert control.stopped is loaded
    assert not result["messages"][-1].tool_calls


@pytest.mark.asyncio
async def test_runtime_handles_image_fallback_without_business_middleware(monkeypatch):
    from langchain_core.messages import HumanMessage, ToolMessage

    from searchos.tools.simple_browser import image_reading

    calls = []
    marked = []

    class TextOnlyModel(Model):
        async def _agenerate(self, messages, **kwargs):
            calls.append(messages)
            if any(isinstance(m, ToolMessage) and isinstance(m.content, list) for m in messages):
                raise RuntimeError("unsupported")
            return await super()._agenerate(messages, **kwargs)

    async def replace_images(messages):
        return [
            m.model_copy(update={"content": "Chart text"}) if isinstance(m, ToolMessage) else m
            for m in messages
        ]

    monkeypatch.setattr(
        image_reading, "is_explicitly_unsupported", lambda exc: str(exc) == "unsupported"
    )
    monkeypatch.setattr(image_reading, "replace_native_image_tool_results", replace_images)
    monkeypatch.setattr(
        image_reading, "mark_native_unsupported", lambda model, reason: marked.append(reason)
    )
    graph = create_search_agent_graph(
        model=TextOnlyModel(responses=[AIMessage(content="Read the chart")]),
        tools=[open],
        middleware=[],
        image_fallback=True,
    )
    original = ToolMessage(
        content=[{"type": "image_url", "image_url": {"url": "data:image/png;base64,eA=="}}],
        tool_call_id="image",
    )
    await graph.ainvoke(
        {
            "messages": [
                HumanMessage(content="Read chart"),
                AIMessage(content="", tool_calls=[{"name": "open", "args": {}, "id": "image"}]),
                original,
            ]
        },
        {"configurable": {"thread_id": "image"}},
    )
    assert graph.middleware == []
    assert len(calls) == 2 and marked == ["unsupported"]
    assert isinstance(original.content, list)


@pytest.mark.asyncio
async def test_runtime_logs_socm_input_without_logger_dependency_in_socm(tmp_path):
    import json

    from searchos.harness.telemetry.episodic import TrajectoryLogger

    state = SearchState()
    state.coverage_map.add_table("t", ["Name", "Credits"], primary_key=["Name"], entities=["Alpha"])
    workspace = InMemoryEvidenceStore(state)
    logger = TrajectoryLogger(tmp_path / "socm.jsonl")
    socm = SOCMContextMiddleware(workspace, task=TaskContext(agent_id="reader"))
    graph = make_graph(None, middleware=[socm], trajectory_logger=logger, agent_id="reader")
    await graph.ainvoke(
        {"messages": [("user", "Read")]}, {"configurable": {"thread_id": "context"}}
    )
    rows = [json.loads(line) for line in (tmp_path / "socm.jsonl").read_text().splitlines()]
    assert any(row.get("kind") == "socm_inject" and row["agent"] == "reader" for row in rows)


def test_runtime_policies_are_not_business_middleware():
    from langchain.agents.middleware.types import AgentMiddleware

    import searchos.harness.middleware as middleware
    from searchos.agents.execution import ControlExecutor
    from searchos.agents.explore.policy import ExplorePolicy
    from searchos.agents.orchestrator.policy import DispatchPolicy
    from searchos.harness.telemetry.recording import AgentRecorder

    for cls in (ExplorePolicy, DispatchPolicy, AgentRecorder, ControlExecutor):
        assert not issubclass(cls, AgentMiddleware)
    assert not any(
        name in middleware.__all__
        for name in (
            "StopControlMiddleware",
            "NativeImageFallbackMiddleware",
            "TrajectoryMiddleware",
            "ExploreWavesMiddleware",
            "PoolReminderMiddleware",
        )
    )
