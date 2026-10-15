"""证据已提交后的核验延迟不应把整个检索任务回收重跑。"""

import asyncio
import json
from types import SimpleNamespace

import pytest

from searchos.harness.middleware.extraction import (
    EvidenceObservation,
    ExtractionConfig,
    ExtractionCoordinator,
)
from searchos.harness.middleware.models import TaskContext
from searchos.socm.workspace import WorkspaceManager
from tests.test_semantic_conflicts import KEY, state_with_values


class Judge:
    def __init__(self, *, block_extraction=False):
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.block_extraction = block_extraction
        self.active = 0

    async def ainvoke(self, prompt):
        if "INPUT_JSON:" in prompt or self.block_extraction:
            self.active += 1
            self.started.set()
            try:
                await self.release.wait()
                return SimpleNamespace(content="[]")
            finally:
                self.active -= 1
        return SimpleNamespace(content=json.dumps([{
            "Name": "RSI", "Definition": "AI enhances its own capabilities.",
            "_source_page": 1, "_source_excerpt": "AI enhances its own capabilities.",
        }]))


def setup(tmp_path, judge, *, batch_n=5):
    workspace = WorkspaceManager(tmp_path, "final-review")
    workspace.create()
    workspace.save_state(state_with_values("AI improves itself."))
    coordinator = ExtractionCoordinator(
        judge, workspace=workspace, batch_n=batch_n,
        config=ExtractionConfig(dual_mode=False, cross_table_backfill=False),
        task=TaskContext(agent_id="reader"),
    )
    return workspace, coordinator


def observation():
    return EvidenceObservation(
        content="RSI definition in this source: AI enhances its own capabilities.",
        source_url="https://example.org/new",
        target_table="concepts",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("background", [False, True])
async def test_slow_conflict_review_keeps_committed_facts_and_finishes(tmp_path, background):
    judge = Judge()
    workspace, coordinator = setup(tmp_path, judge, batch_n=1 if background else 5)
    assert (await coordinator.submit(observation())).accepted
    if background:
        await asyncio.wait_for(judge.started.wait(), 2)
    summary = await coordinator.finalize(timeout=0.15)
    assert judge.started.is_set()
    assert judge.active == 0
    assert summary.buffered == summary.in_flight == 0
    assert summary.committed_node_ids
    state = workspace.load_state()
    assert len(state.evidence_graph.nodes) == 2
    assert state.coverage_map.cells[KEY].conflict_status == "pending"
    assert all(record["status"] == "done" for record in coordinator._journal.load())
    # 以后可直接核验已提交证据，无需重读网页或重跑检索。
    judge.release.set()
    await coordinator.finalize(timeout=1)
    assert workspace.load_state().coverage_map.cells[KEY].conflict_status != "pending"
    assert len(workspace.load_state().evidence_graph.nodes) == 2


@pytest.mark.asyncio
async def test_extraction_timeout_defers_observation_without_failing_agent(tmp_path):
    judge = Judge(block_extraction=True)
    _, coordinator = setup(tmp_path, judge)
    assert (await coordinator.submit(observation())).accepted
    await coordinator.finalize(timeout=0.05)
    assert coordinator.summary().buffered == 1
    assert not coordinator.committed_node_ids
    assert judge.active == 0


@pytest.mark.asyncio
async def test_external_cancellation_during_review_is_not_swallowed(tmp_path):
    judge = Judge()
    _, coordinator = setup(tmp_path, judge)
    assert (await coordinator.submit(observation())).accepted
    task = asyncio.create_task(coordinator.finalize(timeout=2))
    await asyncio.wait_for(judge.started.wait(), 1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert judge.active == 0
