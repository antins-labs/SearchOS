"""模型调用只等待已由满批次或 URL 切换触发的抽取。"""

import asyncio
import json
from dataclasses import dataclass
from types import SimpleNamespace

import pytest
from langchain.agents.middleware.types import ModelResponse
from langchain_core.messages import AIMessage, HumanMessage

from searchos.agents.execution import _BeforeModel
from searchos.harness.middleware.context.socm_middleware import SOCMContextMiddleware
from searchos.harness.middleware.extraction import (
    DeliveryMode,
    EvidenceObservation,
    ExtractionConfig,
    ExtractionCoordinator,
    InMemoryEvidenceStore,
)
from searchos.harness.middleware.models import TaskContext
from searchos.socm import FrontierTask, SearchState


@dataclass
class Request:
    messages: list
    system_message: object = None


async def model_with_context(middleware, request, handler):
    context = SOCMContextMiddleware(
        SimpleNamespace(load_state=lambda: middleware.resources[0]._store.load_state()),
        task=TaskContext(agent_id="search_agent_test"),
    )

    async def with_context(request):
        return await context.awrap_model_call(request, handler)

    return await middleware.awrap_model_call(request, with_context)


@pytest.mark.asyncio
async def test_model_waits_for_triggered_background_flush_commit():
    started, release = asyncio.Event(), asyncio.Event()
    state = SearchState()
    state.coverage_map.add_table("t", ["Name", "Revenue"], primary_key=["Name"], entities=["Acme"])
    state.frontier.add(
        FrontierTask(
            id="task",
            question="Acme revenue",
            table_id="t",
            target_cells=["t/Acme.Revenue"],
            assigned_agent_id="search_agent_test",
        )
    )
    store = InMemoryEvidenceStore(state)

    class Judge:
        async def ainvoke(self, prompt):
            started.set()
            await release.wait()
            return SimpleNamespace(
                content=json.dumps(
                    [
                        {
                            "Name": "Acme",
                            "Revenue": "1234",
                            "_source_page": 1,
                            "_source_excerpt": "Acme reported revenue of 1234 million in 2025.",
                            "_alignment": "full",
                            "_confidence": "high",
                        }
                    ]
                )
            )

    coordinator = ExtractionCoordinator(
        Judge(), store, batch_n=1, config=ExtractionConfig(dual_mode=False)
    )
    mw = _BeforeModel((coordinator,))
    await coordinator.submit(
        EvidenceObservation(
            content=(
                "Acme reported revenue of 1234 million in 2025. "
                "Published in the audited annual report."
            ),
            source_url="https://example.com/report",
            target_table="t",
        ),
        delivery=DeliveryMode.BUFFERED,
    )
    calls = []

    async def handler(request):
        calls.append(request)
        assert store.state.coverage_map.cells["t/Acme.Revenue"].status.value == "filled"
        assert store.state.coverage_map.cells["t/Acme.Revenue"].display_hint == "1234"
        assert any("actionable gaps: 0" in str(m.content) for m in request.messages)
        return ModelResponse(result=[AIMessage(content="Done")])

    pending = asyncio.create_task(
        model_with_context(mw, Request([HumanMessage(content="Search")]), handler)
    )
    try:
        await asyncio.wait_for(started.wait(), timeout=1)
        assert not pending.done()
        assert not calls
        release.set()
        await asyncio.wait_for(pending, timeout=2)
        assert len(calls) == 1
        assert not coordinator._pending_buffer
        assert not coordinator._flush_tasks
    finally:
        release.set()
        if not pending.done():
            pending.cancel()
        await asyncio.gather(pending, return_exceptions=True)
        await coordinator.await_idle()


@pytest.mark.asyncio
async def test_model_does_not_flush_partial_same_url_batch():
    state = SearchState()
    state.coverage_map.add_table("t", ["Name", "Revenue"], primary_key=["Name"], entities=["Acme"])
    store = InMemoryEvidenceStore(state)

    class Judge:
        calls = 0

        async def ainvoke(self, prompt):
            self.calls += 1
            pytest.fail("partial batch must remain buffered")

    judge = Judge()
    coordinator = ExtractionCoordinator(
        judge, store, batch_n=5, config=ExtractionConfig(dual_mode=False)
    )
    mw = _BeforeModel((coordinator,))
    await coordinator.submit(
        EvidenceObservation(
            content=(
                "Acme reported revenue of 1234 million in 2025. "
                "Published in the audited annual report."
            ),
            source_url="https://example.com/report",
            target_table="t",
        )
    )

    called = False

    async def handler(request):
        nonlocal called
        called = True
        return ModelResponse(result=[AIMessage(content="Continue reading")])

    await model_with_context(mw, Request([HumanMessage(content="Search")]), handler)

    assert called is True
    assert judge.calls == 0
    assert len(coordinator._pending_buffer) == 1


@pytest.mark.asyncio
async def test_same_url_flushes_once_when_buffer_reaches_threshold():
    state = SearchState()
    state.coverage_map.add_table("t", ["Name", "Revenue"], primary_key=["Name"], entities=["Acme"])
    store = InMemoryEvidenceStore(state)

    class Judge:
        def __init__(self):
            self.prompts = []

        async def ainvoke(self, prompt):
            self.prompts.append(str(prompt))
            return SimpleNamespace(content="[]")

    judge = Judge()
    coordinator = ExtractionCoordinator(
        judge, store, batch_n=2, config=ExtractionConfig(dual_mode=False)
    )
    await coordinator.submit(
        EvidenceObservation(
            content=(
                "WINDOW-ONE Acme revenue table header and enough source content for extraction."
            ),
            source_url="https://example.com/report",
            target_table="t",
        )
    )
    assert judge.prompts == []
    assert len(coordinator._pending_buffer) == 1

    await coordinator.submit(
        EvidenceObservation(
            content=(
                "WINDOW-TWO Acme reported revenue of 1234 million in the audited annual report."
            ),
            source_url="https://example.com/report",
            target_table="t",
        )
    )
    await coordinator.drain_before_model()

    assert len(judge.prompts) == 1
    assert "WINDOW-ONE" in judge.prompts[0]
    assert "WINDOW-TWO" in judge.prompts[0]
    assert coordinator._pending_buffer == []


@pytest.mark.asyncio
async def test_url_switch_flushes_previous_url_and_model_waits():
    started, release = asyncio.Event(), asyncio.Event()
    state = SearchState()
    state.coverage_map.add_table("t", ["Name", "Revenue"], primary_key=["Name"], entities=["Acme"])
    state.frontier.add(
        FrontierTask(
            id="task",
            question="Acme revenue",
            table_id="t",
            target_cells=["t/Acme.Revenue"],
            assigned_agent_id="search_agent_test",
        )
    )
    store = InMemoryEvidenceStore(state)

    class Judge:
        async def ainvoke(self, prompt):
            started.set()
            await release.wait()
            assert "FIRST-URL" in str(prompt)
            assert "SECOND-URL" not in str(prompt)
            return SimpleNamespace(
                content=json.dumps(
                    [
                        {
                            "Name": "Acme",
                            "Revenue": "1234",
                            "_source_page": 1,
                            "_source_excerpt": "Acme reported revenue of 1234 million in 2025.",
                            "_alignment": "full",
                            "_confidence": "high",
                        }
                    ]
                )
            )

    coordinator = ExtractionCoordinator(
        Judge(), store, batch_n=5, config=ExtractionConfig(dual_mode=False)
    )
    mw = _BeforeModel((coordinator,))
    await coordinator.submit(
        EvidenceObservation(
            content=(
                "FIRST-URL Acme reported revenue of 1234 million in 2025. Audited annual report."
            ),
            source_url="https://example.com/first",
            target_table="t",
            task_id="task",
        )
    )
    await coordinator.submit(
        EvidenceObservation(
            content=(
                "SECOND-URL Another source with enough content to remain "
                "buffered for later extraction."
            ),
            source_url="https://example.com/second",
            target_table="t",
            task_id="task",
        )
    )

    async def handler(request):
        assert store.state.coverage_map.cells["t/Acme.Revenue"].status.value == "filled"
        assert any("actionable gaps: 0" in str(m.content) for m in request.messages)
        return ModelResponse(result=[AIMessage(content="Continue")])

    pending = asyncio.create_task(
        model_with_context(mw, Request([HumanMessage(content="Search")]), handler)
    )
    try:
        await asyncio.wait_for(started.wait(), timeout=1)
        assert not pending.done()
        release.set()
        await asyncio.wait_for(pending, timeout=2)
        assert len(coordinator._pending_buffer) == 1
        assert coordinator._pending_buffer[0]["source_url"] == "https://example.com/second"
    finally:
        release.set()
        if not pending.done():
            pending.cancel()
        await asyncio.gather(pending, return_exceptions=True)


@pytest.mark.asyncio
async def test_barrier_failure_does_not_call_model():
    async def fail():
        raise RuntimeError("commit failed")

    mw = _BeforeModel((SimpleNamespace(drain_before_model=fail),))

    async def handler(request):
        pytest.fail("model must not run after barrier failure")

    with pytest.raises(RuntimeError, match="commit failed"):
        await model_with_context(mw, Request([HumanMessage(content="Search")]), handler)


@pytest.mark.asyncio
async def test_finished_background_failure_is_not_mistaken_for_idle(monkeypatch):
    coordinator = ExtractionCoordinator(None, InMemoryEvidenceStore(), batch_n=1)

    async def fail(snapshot, *, reason):
        raise RuntimeError("storage unavailable")

    monkeypatch.setattr(coordinator, "_flush_snapshot", fail)
    await coordinator.submit(
        EvidenceObservation(
            content="A sufficiently long observation to trigger background extraction and storage.",
            source_url="https://example.com/report",
        )
    )
    await coordinator.await_idle()
    assert not coordinator._flush_tasks
    with pytest.raises(RuntimeError, match="Background evidence extraction failed") as exc:
        await coordinator.drain_before_model()
    assert str(exc.value.__cause__) == "storage unavailable"


@pytest.mark.asyncio
async def test_cancelling_barrier_does_not_call_model():
    started = asyncio.Event()

    async def drain():
        started.set()
        await asyncio.Event().wait()

    mw = _BeforeModel((SimpleNamespace(drain_before_model=drain),))

    async def handler(request):
        pytest.fail("model must not run after cancellation")

    pending = asyncio.create_task(
        model_with_context(mw, Request([HumanMessage(content="Search")]), handler)
    )
    await asyncio.wait_for(started.wait(), timeout=1)
    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        await pending
