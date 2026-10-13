"""无进展停止必须经过本 Agent 的实际提取结算。"""

import asyncio
import json
from dataclasses import dataclass
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from middleware_utils import model_call

from searchos.config.settings import settings
from searchos.harness.middleware.sensor.core.models import ControlState
from searchos.harness.middleware.sensor.progress_middleware import ProgressGuardMiddleware
from searchos.agents.execution import ControlExecutor, _ExecutionHooks
from searchos.harness.middleware.extraction import (
    EvidenceObservation,
    ExtractionConfig,
    ExtractionCoordinator,
    InMemoryEvidenceStore,
)
from searchos.agents.execution import _BeforeModel
from searchos.socm import SearchState


@dataclass
class Request:
    messages: list
    system_message: object = None


def setup(monkeypatch, judge, batch_n=5, *, dual_mode=False):
    monkeypatch.setattr(settings, "search_agent_no_progress_tool_limit", 3)
    s = SearchState()
    s.coverage_map.add_table("t", ["Name", "Revenue"], primary_key=["Name"], entities=["Acme"])
    store = InMemoryEvidenceStore(s)
    coordinator = ExtractionCoordinator(judge, store, batch_n=batch_n, config=ExtractionConfig(dual_mode=dual_mode))
    harness = ProgressGuardMiddleware(coordinator, ControlState(), limit=3)
    return coordinator, harness


async def read(coordinator, harness, i, *, unrelated_gain=False):
    content = (
        "[Now viewing] Report\nURL: https://example.org/report\n\n"
        f"L{i}: Acme reported revenue of 1234 million in 2025. Window {i}."
    )
    await coordinator.submit(
        EvidenceObservation(
            content=content, source_url="https://example.org/report", target_table="t"
        )
    )
    if unrelated_gain:
        from searchos.socm import EvidenceNode

        coordinator._store.state.evidence_graph.add_node(EvidenceNode(
            id=f"unrelated-{i}", finding="Sibling progress", source="https://sibling.example",
        ))



class Judge:
    def __init__(self, useful=False):
        self.useful = useful
        self.calls = 0

    async def ainvoke(self, prompt):
        self.calls += 1
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
                if self.useful
                else []
            )
        )


async def model_turn(harness):
    async def handler(request):
        if harness.control.stopped:
            assert "HARD STOP" in request.system_message.content
        return AIMessage(content="done")

    return await model_call([
        _BeforeModel((harness.coordinator,)), harness,
        _ExecutionHooks(ControlExecutor(harness.control)),
    ], Request([HumanMessage(content="continue")]), handler)


@pytest.mark.asyncio
async def test_partial_buffer_and_repeated_model_turns_do_not_count(monkeypatch):
    judge = Judge()
    coordinator, harness = setup(monkeypatch, judge)
    for i in range(3):
        await read(coordinator, harness, i)
        await model_turn(harness)
    assert judge.calls == 0
    assert coordinator.summary().buffered == 3
    assert coordinator.progress.settled_batches == 0
    assert coordinator.progress.consecutive_empty_batches == 0
    assert not harness.control.stopped


@pytest.mark.asyncio
@pytest.mark.parametrize("dual_mode", [False, True])
async def test_only_third_empty_batch_stops_even_with_unrelated_global_gain(monkeypatch, dual_mode):
    coordinator, harness = setup(monkeypatch, Judge(), batch_n=3, dual_mode=dual_mode)
    for batch in range(3):
        for i in range(3):
            await read(coordinator, harness, batch * 3 + i, unrelated_gain=True)
        await model_turn(harness)
        assert coordinator.progress.consecutive_empty_batches == batch + 1
        assert harness.control.stopped is (batch == 2)
        # 同一结算结果不会因再次读取快照或再次调用模型而重复计数。
        await model_turn(harness)
        assert coordinator.progress.settled_batches == batch + 1
    assert harness.control.reason == "no_progress_batches_x3"


@pytest.mark.asyncio
async def test_productive_batch_resets_streak_and_repeated_fact_does_not(monkeypatch):
    judge = Judge()
    coordinator, harness = setup(monkeypatch, judge, batch_n=1)
    for i in range(2):
        await read(coordinator, harness, i)
        await model_turn(harness)
    assert coordinator.progress.consecutive_empty_batches == 2
    judge.useful = True
    await read(coordinator, harness, 2)
    await model_turn(harness)
    assert coordinator.progress.consecutive_empty_batches == 0
    assert coordinator.committed_node_ids
    # 同一事实再次提交，未新增证据或投影，应计为无产出。
    await read(coordinator, harness, 3)
    await model_turn(harness)
    assert coordinator.progress.consecutive_empty_batches == 1
    assert not harness.control.stopped


@pytest.mark.asyncio
async def test_several_completed_batches_in_one_model_turn_are_all_counted(monkeypatch):
    coordinator, harness = setup(monkeypatch, Judge(), batch_n=1)
    for i in range(3):
        await read(coordinator, harness, i)
    await model_turn(harness)
    assert coordinator.progress.settled_batches == 3
    assert coordinator.progress.consecutive_empty_batches == 3
    assert harness.control.stopped


@pytest.mark.asyncio
async def test_background_commit_is_awaited_before_decision(monkeypatch):
    started, release = asyncio.Event(), asyncio.Event()

    class SlowJudge(Judge):
        async def ainvoke(self, prompt):
            started.set()
            await release.wait()
            return await super().ainvoke(prompt)

    coordinator, harness = setup(monkeypatch, SlowJudge(True), batch_n=3)
    for i in range(3):
        await read(coordinator, harness, i)
    pending = asyncio.create_task(model_turn(harness))
    try:
        await asyncio.wait_for(started.wait(), timeout=1)
        assert not pending.done()
        assert coordinator.progress.settled_batches == 0
    finally:
        release.set()
        await pending
    assert coordinator.progress.settled_batches == 1
    assert coordinator.progress.consecutive_empty_batches == 0


@pytest.mark.asyncio
async def test_settlement_failure_does_not_become_no_progress(monkeypatch):
    coordinator, harness = setup(monkeypatch, Judge())

    async def failed():
        raise RuntimeError("settlement failed")

    harness.coordinator.drain_before_model = failed
    with pytest.raises(RuntimeError, match="settlement failed"):
        await model_turn(harness)
    assert coordinator.progress.settled_batches == 0
    assert not harness.control.stopped


@pytest.mark.asyncio
async def test_parse_failure_and_empty_flush_do_not_count_as_empty_batch(monkeypatch):
    class InvalidJudge:
        async def ainvoke(self, prompt):
            return SimpleNamespace(content="invalid json")

    coordinator, harness = setup(monkeypatch, InvalidJudge(), batch_n=1)
    await coordinator.flush()
    assert coordinator.progress.settled_batches == 0
    await read(coordinator, harness, 0)
    await model_turn(harness)
    assert coordinator.progress.settled_batches == 0
    assert not harness.control.stopped
