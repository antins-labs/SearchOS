"""装配决定抽取行为，生命周期负责统一收尾。"""

import asyncio
import json
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage

from searchos.harness.middleware.extraction import (
    TaskContext,
    ExtractionCoordinator,
    ExtractionReceipt,
    FinalSummaryEvidenceMiddleware,
    InMemoryEvidenceStore,
    LocalEvidenceMiddleware,
    WebEvidenceMiddleware,
)
from searchos.agents.execution import _run_resources
from searchos.socm import FrontierTask, SearchState
from searchos.harness.middleware import BudgetMiddleware, ControlState


async def tool_chain(middleware, name, result):
    async def handler(_request):
        return result

    for adapter in reversed(middleware):
        inner = handler

        async def handler(request, adapter=adapter, inner=inner):
            return await adapter.awrap_tool_call(request, inner)

    return await handler(SimpleNamespace(tool_call={"name": name}))


@pytest.mark.asyncio
@pytest.mark.parametrize("sources", [(), ("web",), ("local",), ("web", "local")])
async def test_sources_only_run_when_loaded(sources):
    observations = []

    async def submit(observation, **_kwargs):
        observations.append(observation)
        return ExtractionReceipt(accepted=True)

    coordinator = SimpleNamespace(submit=submit)
    context = TaskContext("worker", "assigned-task", "target")
    adapters = {
        "web": WebEvidenceMiddleware(coordinator, context=context),
        "local": LocalEvidenceMiddleware(coordinator, context=context),
    }
    middleware = [adapters[source] for source in sources]
    web = SimpleNamespace(
        content=(
            "[Now viewing] Report\nURL: https://example.org/report\n\n"
            "Alpha requires 120 credits. The programme takes four years."
        )
    )
    local = SimpleNamespace(
        content=(
            "[LOCAL_SOURCE]\nSource: local://document@v1/p1\n\n"
            "Alpha requires 120 credits. The programme takes four years."
        )
    )
    for name, result in [("open", web), ("local_open", local), ("local_find", local)]:
        assert await tool_chain(middleware, name, result) is result
    assert len(observations) == len(sources)
    assert {obs.source_kind.value for obs in observations} == {
        {"web": "page", "local": "local_document"}[source] for source in sources
    }
    assert all(
        obs.task_id == "assigned-task" and obs.target_table == "target" for obs in observations
    )


class FindingsJudge:
    async def ainvoke(self, prompt):
        if "核验每项事实" in prompt:
            rows = [{"id": "0", "supported": True}]
        else:
            rows = [
                {
                    "finding": "Alpha requires 120 credits.",
                    "source_excerpt": "Alpha requires 120 credits.",
                    "relation": "supports",
                }
            ]
        return SimpleNamespace(content=json.dumps(rows))


@pytest.mark.asyncio
@pytest.mark.parametrize("loaded", [False, True])
async def test_summary_loading_controls_hybrid_evidence_commit(loaded):
    state = SearchState(research_mode="findings", source_scope={"mode": "hybrid"})
    state.frontier.add(FrontierTask(id="task", question="Credits?", result_mode="findings"))
    store = InMemoryEvidenceStore(state)
    coordinator = ExtractionCoordinator(FindingsJudge(), store)
    middleware = FinalSummaryEvidenceMiddleware(
        coordinator,
        context=TaskContext("worker", "task"),
    )

    async def handler(_request):
        return AIMessage(content=("Alpha requires 120 credits. The programme takes four years."))

    async with _run_resources((coordinator,), timeout=2):
        if loaded:
            await middleware.aafter_agent({"messages": [await handler(None)]}, None)
        else:
            await handler(None)
    assert len(store.state.evidence_graph.nodes) == int(loaded)
    if loaded:
        node = store.state.evidence_graph.nodes[0]
        assert node.source == "agent://worker/final_summary"
        assert node.observation_id and node.span
        assert store.state.evidence_graph.task_bindings[0].task_id == "task"


@pytest.mark.asyncio
async def test_summary_ignores_intermediate_tool_turn():
    async def submit(*_args, **_kwargs):
        pytest.fail("A tool turn is not a final summary")

    middleware = FinalSummaryEvidenceMiddleware(SimpleNamespace(submit=submit))
    response = AIMessage(
        content="Reasoning " * 20,
        tool_calls=[
            {"name": "open", "args": {}, "id": "call"},
        ],
    )

    async def handler(_request):
        return response

    assert await middleware.aafter_agent({"messages": [response]}, None) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["normal", "error", "cancelled"])
async def test_lifecycle_finalizes_once_before_exit(outcome):
    events = []

    async def finalize(*, timeout):
        await asyncio.sleep(0)
        events.append("finalized")

    async def run():
        async with _run_resources((SimpleNamespace(finalize=finalize),), timeout=1):
            events.append("running")
            if outcome == "error":
                raise ValueError("failed")
            if outcome == "cancelled":
                raise asyncio.CancelledError()
        events.append("report")

    if outcome == "normal":
        await run()
        assert events == ["running", "finalized", "report"]
    else:
        with pytest.raises(ValueError if outcome == "error" else asyncio.CancelledError):
            await run()
        assert events == ["running", "finalized"]


@pytest.mark.asyncio
async def test_finalization_failure_is_visible():
    async def finalize(*, timeout):
        raise RuntimeError("commit failed")

    with pytest.raises(RuntimeError, match="commit failed"):
        async with _run_resources((SimpleNamespace(finalize=finalize),), timeout=1):
            pass


@pytest.mark.asyncio
async def test_real_agent_graph_composes_sources_and_final_summary():
    from langchain.agents import create_agent
    from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
    from langchain_core.tools import tool

    class Model(FakeMessagesListChatModel):
        def bind_tools(self, tools, **kwargs):
            return self

    @tool
    def open() -> str:
        """Read a web page."""
        return (
            "[Now viewing] Report\nURL: https://example.org/report\n\n"
            "Alpha requires 120 credits. This is the web programme record."
        )

    @tool
    def local_open() -> str:
        """Read a local source."""
        return (
            "[LOCAL_SOURCE]\nSource: local://document@v1/p1\n\n"
            "Alpha requires 120 credits. This is the local programme record."
        )

    observations = []

    async def submit(observation, **kwargs):
        observations.append(observation)
        return ExtractionReceipt(accepted=True)

    coordinator = SimpleNamespace(submit=submit)
    model = Model(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {"name": "open", "args": {}, "id": "web"},
                    {"name": "local_open", "args": {}, "id": "local"},
                ],
            ),
            AIMessage(
                content="Alpha requires 120 credits, according to the two programme records."
            ),
        ]
    )
    graph = create_agent(
        model,
        tools=[open, local_open],
        middleware=[
            FinalSummaryEvidenceMiddleware(coordinator),
            WebEvidenceMiddleware(coordinator),
            LocalEvidenceMiddleware(coordinator),
        ],
    )
    await graph.ainvoke({"messages": [{"role": "user", "content": "Check credits."}]})
    assert sorted(obs.source_kind.value for obs in observations) == [
        "agent_summary",
        "local_document",
        "page",
    ]


@pytest.mark.asyncio
async def test_early_explore_summary_is_accepted_and_budget_counts_one_turn():
    from searchos.harness.middleware.sensor.budget_middleware import BudgetMiddleware
    from searchos.harness.middleware.sensor.core.models import BudgetState, ControlState
    from searchos.agents.explore.policy import ExplorePolicy

    observations = []

    async def submit(observation, **kwargs):
        observations.append(observation)
        return ExtractionReceipt(accepted=True)

    summary = FinalSummaryEvidenceMiddleware(SimpleNamespace(submit=submit))
    budget = BudgetState(max_iterations=10)
    harness = BudgetMiddleware(budget, ControlState())
    waves = ExplorePolicy(max_waves=3, control=ControlState())
    calls = 0

    async def model(request):
        nonlocal calls
        calls += 1
        if calls == 1:
            return AIMessage(content="Supported early findings from the supplied source. " * 3)
        return AIMessage(
            content="",
            tool_calls=[
                {"name": "explore_web", "args": {}, "id": "continue"},
            ],
        )

    async def with_waves(request):
        return await waves.call_model(request, model)

    async def with_budget(request):
        return await harness.awrap_model_call(request, with_waves)

    from dataclasses import dataclass

    @dataclass
    class Request:
        messages: tuple = ()
        system_message: object = None

    response = await with_budget(Request())
    await summary.aafter_agent({"messages": [response]}, None)
    assert not response.tool_calls and calls == 1
    assert budget.current_iteration == 1
    assert len(observations) == 1
    assert observations[0].content.startswith("Supported early")


@pytest.mark.asyncio
async def test_finalization_timeout_cancels_background_work():
    from searchos.harness.middleware.extraction import EvidenceObservation

    coordinator = ExtractionCoordinator(None, InMemoryEvidenceStore(SearchState()), batch_n=1)
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def flush(_snapshot, *, reason):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    coordinator._flush_snapshot = flush
    await coordinator.submit(
        EvidenceObservation(
            content="Alpha requires 120 credits. This is the original programme record.",
            source_url="https://example.org/report",
        )
    )
    await started.wait()
    with pytest.raises(TimeoutError):
        await coordinator.finalize(timeout=0.01)
    assert cancelled.is_set()
    assert not coordinator._flush_tasks


def test_pipelines_create_independent_resources_and_choose_sources(monkeypatch):
    from searchos.config.settings import settings
    from searchos.harness.middleware.pipelines import (
        web_search_pipeline, local_search_pipeline, explore_pipeline, writer_pipeline,
    )
    from tests.middleware_utils import capture_pipeline

    monkeypatch.setattr(settings, "use_layered_context", True)
    store = InMemoryEvidenceStore(SearchState(source_scope={"mode": "hybrid"}))
    graphs = []
    for pipeline in (web_search_pipeline, local_search_pipeline, explore_pipeline, writer_pipeline):
        options = dict(workspace=store, task=TaskContext(pipeline.__name__))
        if pipeline in (web_search_pipeline, local_search_pipeline):
            options.update(extraction_model=object(), extraction_policy="schema_facts", final_summary=False)
        graphs.append(capture_pipeline(monkeypatch, pipeline, **options))
    web, local, explore, writer = graphs
    web_evidence = next(m for m in web.middleware if isinstance(m, WebEvidenceMiddleware))
    local_evidence = next(m for m in local.middleware if isinstance(m, LocalEvidenceMiddleware))
    assert web_evidence.coordinator is not local_evidence.coordinator
    budgets = [next(m.budget for m in graph.middleware if isinstance(m, BudgetMiddleware))
               for graph in graphs]
    assert len({id(budget) for budget in budgets}) == 4
    assert not any(isinstance(m, LocalEvidenceMiddleware) for m in web.middleware)
    assert not any(isinstance(m, WebEvidenceMiddleware) for m in local.middleware)
    assert not any(getattr(m, "run_resources", ()) for graph in (explore, writer)
                   for m in graph.middleware)
    assert not any(isinstance(m, FinalSummaryEvidenceMiddleware)
                   for graph in graphs for m in graph.middleware)


@pytest.mark.asyncio
async def test_native_image_fallback_retries_once_without_mutating_history(monkeypatch):
    from dataclasses import dataclass

    from langchain_core.messages import ToolMessage

    from searchos.agents.model_call import call_model
    from searchos.tools.simple_browser import image_reading

    @dataclass
    class Request:
        messages: list
        model: object

    original = ToolMessage(
        content=[{"type": "image_url", "image_url": {"url": "data:image/png;base64,eA=="}}],
        tool_call_id="image-call",
    )
    fallback = original.model_copy(update={"content": "Recognized chart text"})
    model = object()
    marked = []
    calls = []

    async def replace_images(messages):
        assert messages == [original]
        return [fallback]

    monkeypatch.setattr(
        image_reading, "is_explicitly_unsupported", lambda exc: str(exc) == "unsupported"
    )
    monkeypatch.setattr(
        image_reading, "mark_native_unsupported", lambda m, reason: marked.append(m)
    )
    monkeypatch.setattr(image_reading, "replace_native_image_tool_results", replace_images)

    async def handler(request):
        calls.append(request)
        if len(calls) == 1:
            raise RuntimeError("unsupported")
        return AIMessage(content="Read chart")

    request = Request([original], model)
    await call_model(request, handler)
    assert len(calls) == 2 and marked == [model]
    assert calls[1].messages[0].tool_call_id == "image-call"
    assert calls[1].messages[0].content == "Recognized chart text"
    assert isinstance(request.messages[0].content, list)


@pytest.mark.asyncio
async def test_explore_stop_prevents_response_retry():
    from searchos.agents.explore.policy import ExplorePolicy

    calls = []

    async def handler(request):
        calls.append(request)
        return AIMessage(content="Partial briefing")

    middleware = ExplorePolicy(max_waves=3, control=ControlState(forced=True))
    await middleware.call_model(None, handler)
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_workspace_task_constructor_supplies_summary_context():
    from searchos.harness.middleware import TaskContext

    state = SearchState(research_mode="findings", source_scope={"mode": "hybrid"})
    state.frontier.add(FrontierTask(id="task", question="Credits?", result_mode="findings"))
    workspace = InMemoryEvidenceStore(state)
    extraction = ExtractionCoordinator(
        FindingsJudge(), workspace=workspace,
        task=TaskContext(agent_id="worker", task_id="task", task_text="Credits?"),
        policy="schema_facts",
    )
    middleware = FinalSummaryEvidenceMiddleware(extraction)

    async def handler(_):
        return AIMessage(content="Alpha requires 120 credits. The programme takes four years.")

    async with _run_resources((extraction,), timeout=2):
        await middleware.aafter_agent({"messages": [await handler(None)]}, None)
    node = workspace.state.evidence_graph.nodes[0]
    assert node.source == "agent://worker/final_summary"
    assert workspace.state.evidence_graph.task_bindings[0].task_id == "task"
