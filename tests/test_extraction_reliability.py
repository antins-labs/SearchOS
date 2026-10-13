"""抽取保留互补事实、约束真实调用，以及恢复待处理观测。"""

import asyncio
from types import SimpleNamespace

import pytest

from searchos.harness.middleware.extraction import (
    DeliveryMode,
    EvidenceObservation,
    ExtractionConfig,
    ExtractionCoordinator,
    InMemoryEvidenceStore,
)
from searchos.harness.middleware.extraction.core.judge import RowExtractor
from searchos.harness.middleware.models import TaskContext
from searchos.socm import SearchState
from searchos.socm.workspace import WorkspaceManager


def state():
    result = SearchState(intent="Company facts")
    result.coverage_map.initialize(
        entities=["Acme"],
        attributes=["Company", "Revenue", "Employees"],
        table_id="companies",
        primary_key=["Company"],
    )
    return result


def observation():
    return EvidenceObservation(
        content="Acme reported revenue of 100 million. Acme employed 50 people in 2025.",
        source_url="https://example.com/acme",
        target_table="companies",
    )


class Judge:
    def __init__(self):
        self.active = self.peak = self.calls = 0

    async def ainvoke(self, prompt):
        self.calls += 1
        self.active += 1
        self.peak = max(self.peak, self.active)
        try:
            await asyncio.sleep(0.01)
            return SimpleNamespace(content="[]")
        finally:
            self.active -= 1


def test_complementary_and_conflicting_rows_keep_their_own_quotes():
    rows = [
        {
            "Company": "Acme",
            "Revenue": "100",
            "_source_page": 1,
            "_source_excerpt": "revenue of 100",
        },
        {"Company": "Acme", "Employees": "50", "_source_page": 1, "_source_excerpt": "employed 50"},
        {
            "Company": "Acme",
            "Revenue": "200",
            "_source_page": 1,
            "_source_excerpt": "revenue of 200",
        },
    ]
    assert RowExtractor.dedup_rows(rows, state().coverage_map.tables["companies"]) == rows


@pytest.mark.asyncio
async def test_judge_concurrency_applies_inside_a_multichunk_batch():
    judge = Judge()
    coordinator = ExtractionCoordinator(
        judge,
        InMemoryEvidenceStore(state()),
        config=ExtractionConfig(flush_concurrency=2, dual_mode=False),
    )
    coordinator._preparer.chunk_items = lambda items: [[dict(items[0])] for _ in range(8)]
    await coordinator.submit(observation(), delivery=DeliveryMode.SYNC)
    assert judge.calls == 8
    assert judge.peak == 2


@pytest.mark.asyncio
async def test_sync_failure_is_reported_and_can_be_retried():
    coordinator = ExtractionCoordinator(
        Judge(), InMemoryEvidenceStore(state()), config=ExtractionConfig(dual_mode=False)
    )
    original = coordinator._flush_snapshot

    async def fail(*args, **kwargs):
        raise OSError("storage unavailable")

    coordinator._flush_snapshot = fail
    receipt = await coordinator.submit(observation(), delivery=DeliveryMode.SYNC)
    assert receipt.extraction_reports
    assert receipt.extraction_reports[0].succeeded is False
    assert receipt.extraction_reports[0].status == "failed"
    coordinator._flush_snapshot = original
    retried = await coordinator.submit(observation(), delivery=DeliveryMode.SYNC)
    assert retried.accepted and not retried.duplicate
    assert retried.extraction_reports[0].succeeded


@pytest.mark.asyncio
async def test_workspace_pending_observation_survives_coordinator_recreation(tmp_path):
    workspace = WorkspaceManager(tmp_path, "recovery")
    workspace.create()
    workspace.save_state(state())
    config = ExtractionConfig(dual_mode=False)
    first = ExtractionCoordinator(
        Judge(), workspace=workspace, config=config, task=TaskContext(agent_id="worker")
    )
    await first.submit(observation())
    judge = Judge()
    second = ExtractionCoordinator(
        judge, workspace=workspace, config=config, task=TaskContext(agent_id="worker")
    )
    await second.drain_before_model()
    assert judge.calls == 1
    third = ExtractionCoordinator(
        Judge(), workspace=workspace, config=config, task=TaskContext(agent_id="worker")
    )
    duplicate = await third.submit(observation(), delivery=DeliveryMode.SYNC)
    assert duplicate.duplicate


@pytest.mark.asyncio
async def test_commit_before_done_record_replays_without_duplicate_facts(tmp_path):
    import json

    class FactJudge(Judge):
        async def ainvoke(self, prompt):
            return SimpleNamespace(
                content=json.dumps(
                    [
                        {
                            "Company": "Acme",
                            "Revenue": "100",
                            "_source_excerpt": "Acme reported revenue of 100 million.",
                            "_source_page": 1,
                        }
                    ]
                )
            )

    workspace = WorkspaceManager(tmp_path, "commit-recovery")
    workspace.create()
    workspace.save_state(state())
    config = ExtractionConfig(dual_mode=False)
    task = TaskContext(agent_id="worker")
    first = ExtractionCoordinator(FactJudge(), workspace=workspace, config=config, task=task)
    write = first._journal.write

    def fail_done(item, status, **kwargs):
        if status == "done":
            raise OSError("crash after evidence commit")
        return write(item, status, **kwargs)

    first._journal.write = fail_done
    receipt = await first.submit(observation(), delivery=DeliveryMode.SYNC)
    assert not receipt.extraction_reports[0].succeeded
    before = workspace.load_state().evidence_graph.nodes
    assert before
    second = ExtractionCoordinator(FactJudge(), workspace=workspace, config=config, task=task)
    await second.drain_before_model()
    after = workspace.load_state().evidence_graph.nodes
    assert [node.id for node in after] == [node.id for node in before]


@pytest.mark.asyncio
async def test_cancelled_sync_observation_is_retained_for_flush():
    started = asyncio.Event()

    class WaitingJudge(Judge):
        async def ainvoke(self, prompt):
            started.set()
            await asyncio.Event().wait()

    coordinator = ExtractionCoordinator(
        WaitingJudge(), InMemoryEvidenceStore(state()), config=ExtractionConfig(dual_mode=False)
    )
    running = asyncio.create_task(coordinator.submit(observation(), delivery=DeliveryMode.SYNC))
    await started.wait()
    running.cancel()
    with pytest.raises(asyncio.CancelledError):
        await running
    assert coordinator.summary().buffered == 1
    coordinator._extractor._judge = Judge()
    summary = await coordinator.flush()
    assert summary.buffered == 0
    duplicate = await coordinator.submit(observation())
    assert duplicate.duplicate


@pytest.mark.asyncio
async def test_workspace_recovery_does_not_take_another_agents_batch(tmp_path):
    workspace = WorkspaceManager(tmp_path, "isolated")
    workspace.create()
    workspace.save_state(state())
    first = ExtractionCoordinator(Judge(), workspace=workspace, task=TaskContext(agent_id="first"))
    await first.submit(observation())
    judge = Judge()
    second = ExtractionCoordinator(judge, workspace=workspace, task=TaskContext(agent_id="second"))
    await second.drain_before_model()
    assert judge.calls == 0
    assert second.summary().buffered == 0


@pytest.mark.asyncio
async def test_cross_chunk_candidates_keep_values_and_sources():
    import json

    class ChunkJudge(Judge):
        async def ainvoke(self, prompt):
            if "employed" in prompt:
                row = {
                    "Company": "Acme",
                    "Employees": "50",
                    "_source_excerpt": "Acme employed 50 people.",
                }
            else:
                row = {
                    "Company": "Acme",
                    "Revenue": "100",
                    "_source_excerpt": "Acme reported revenue of 100 million.",
                }
            return SimpleNamespace(content=json.dumps([{**row, "_source_page": 1}]))

    store = InMemoryEvidenceStore(state())
    coordinator = ExtractionCoordinator(
        ChunkJudge(), store, config=ExtractionConfig(dual_mode=False)
    )
    coordinator._preparer.chunk_items = lambda items: [
        [
            {
                **items[0],
                "content": "Acme reported revenue of 100 million.",
                "source_url": "https://example.com/revenue",
            }
        ],
        [
            {
                **items[0],
                "content": "Acme employed 50 people.",
                "source_url": "https://example.com/employees",
            }
        ],
    ]
    await coordinator.submit(observation(), delivery=DeliveryMode.SYNC)
    nodes = store.load_state().evidence_graph.nodes
    assert any(
        n.attribute == "Revenue" and n.source == "https://example.com/revenue" for n in nodes
    )
    assert any(
        n.attribute == "Employees" and n.source == "https://example.com/employees" for n in nodes
    )


@pytest.mark.asyncio
async def test_missing_page_tags_do_not_drop_corroboration_from_another_source():
    import json

    class UntaggedJudge:
        async def ainvoke(self, prompt):
            return SimpleNamespace(
                content=json.dumps(
                    [
                        {"Company": "Acme", "Revenue": "100"},
                        {"Company": "Acme", "Revenue": "100", "Employees": "50"},
                    ]
                )
            )

    current = state()
    extractor = RowExtractor(UntaggedJudge(), ExtractionConfig())
    bundles, ok = await extractor.extract_rows(
        [
            {"content": "Acme revenue 100", "source_url": "https://example.com/one"},
            {"content": "Acme revenue 100 employees 50", "source_url": "https://example.com/two"},
        ],
        current.coverage_map.tables["companies"],
        "",
        current,
        mode="merged",
    )
    assert ok
    assert {bundle[2] for bundle in bundles} == {
        "https://example.com/one",
        "https://example.com/two",
    }


@pytest.mark.asyncio
async def test_final_flush_counts_pending_work_during_judge_call():
    store = InMemoryEvidenceStore(state())

    class PendingJudge(Judge):
        async def ainvoke(self, prompt):
            assert sum(store.pending_by_owner.values()) > 0
            return await super().ainvoke(prompt)

    coordinator = ExtractionCoordinator(
        PendingJudge(), store, config=ExtractionConfig(dual_mode=False)
    )
    await coordinator.submit(observation())
    await coordinator.finalize()
    assert sum(store.pending_by_owner.values()) == 0
