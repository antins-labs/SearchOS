"""证据抽取协调器的端到端契约。"""

from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from types import SimpleNamespace

import pytest

from searchos.harness.middleware.extraction import (
    DeliveryMode,
    EvidenceObservation,
    ExtractionConfig,
    ExtractionCoordinator,
    InMemoryEvidenceStore,
)
from searchos.harness.middleware.extraction.core.preparation import ObservationPreparer
from searchos.socm import FrontierTask, SearchState


class ScriptedJudge:
    def __init__(self, rows: list[dict]) -> None:
        self.rows = rows
        self.calls = 0

    async def ainvoke(self, _prompt: str) -> SimpleNamespace:
        self.calls += 1
        return SimpleNamespace(content=json.dumps(self.rows, ensure_ascii=False))


class SequenceJudge:
    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.calls = 0

    async def ainvoke(self, _prompt: str) -> SimpleNamespace:
        response = self.responses[min(self.calls, len(self.responses) - 1)]
        self.calls += 1
        return SimpleNamespace(content=response)


class ConcurrentJudge(ScriptedJudge):
    def __init__(self, rows: list[dict]) -> None:
        super().__init__(rows)
        self.active = 0
        self.max_active = 0

    async def ainvoke(self, prompt: str) -> SimpleNamespace:
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            await asyncio.sleep(0.03)
            return await super().ainvoke(prompt)
        finally:
            self.active -= 1


class PhaseOrderJudge:
    def __init__(self, store: InMemoryEvidenceStore) -> None:
        self.store = store
        self.events: list[str] = []
        self.discover_saw_fill_commit = False

    async def ainvoke(self, prompt: str) -> SimpleNamespace:
        if "FILL MODE" in prompt:
            self.events.append("fill_start")
            await asyncio.sleep(0.03)
            self.events.append("fill_end")
            return SimpleNamespace(content=json.dumps([_row()]))
        self.events.append("discover_start")
        cell = self.store.state.coverage_map.cells["companies/Acme.Revenue"]
        self.discover_saw_fill_commit = cell.status.value == "filled"
        return SimpleNamespace(
            content=json.dumps(
                [
                    {
                        "Company": "Beta",
                        "Revenue": "5678",
                        "_source_page": 1,
                        "_source_excerpt": "Beta reported revenue of 5678 million in 2025.",
                        "_alignment": "full",
                        "_confidence": "high",
                    }
                ]
            )
        )


class PromptCaptureJudge:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    async def ainvoke(self, prompt: str) -> SimpleNamespace:
        self.prompts.append(prompt)
        return SimpleNamespace(content="[]")


def _state() -> SearchState:
    state = SearchState(intent="Collect company revenue")
    state.coverage_map.initialize(
        entities=["Acme"],
        attributes=["Company", "Revenue"],
        table_id="companies",
        primary_key=["Company"],
    )
    return state


def _row() -> dict:
    return {
        "Company": "Acme",
        "Revenue": "1234",
        "_source_page": 1,
        "_source_excerpt": "Acme reported revenue of 1234 million in 2025.",
        "_alignment": "full",
        "_confidence": "high",
    }


def _observation() -> EvidenceObservation:
    return EvidenceObservation(
        content=(
            "Acme annual report. Acme reported revenue of 1234 million in 2025. "
            "The figure was audited and published with the annual results."
        ),
        source_url="https://example.com/acme-results",
        target_table="companies",
    )


def _mixed_observation() -> EvidenceObservation:
    return EvidenceObservation(
        content=(
            "Acme reported revenue of 1234 million in 2025. "
            "Beta reported revenue of 5678 million in 2025. "
            "Both figures were published in audited annual results."
        ),
        source_url="skill://company-results",
        target_table="companies",
    )


def test_middleware_is_only_an_extraction_adapter() -> None:
    from searchos.harness.middleware.extraction import WebEvidenceMiddleware

    assert not hasattr(WebEvidenceMiddleware, "_flush_snapshot")
    assert not hasattr(WebEvidenceMiddleware, "_run_row_judge")
    assert not hasattr(WebEvidenceMiddleware, "_ingest_rows")


def test_explore_replay_uses_the_extraction_model_without_a_judge_model() -> None:
    from searchos.tools.schema import _select_replay_model

    extraction_model = object()
    context = SimpleNamespace(extraction_model=extraction_model, judge_model=None)

    assert _select_replay_model(context) is extraction_model


@pytest.mark.asyncio
async def test_sync_submit_commits_evidence_and_coverage_atomically() -> None:
    store = InMemoryEvidenceStore(_state())
    coordinator = ExtractionCoordinator(
        ScriptedJudge([_row()]),
        store,
        batch_n=10,
        config=ExtractionConfig(dual_mode=False),
    )

    receipt = await coordinator.submit(_observation(), delivery=DeliveryMode.SYNC)

    assert receipt.accepted is True
    assert len(receipt.committed_node_ids) == 1
    assert receipt.committed_node_ids == tuple(coordinator.committed_node_ids)
    assert store.state.evidence_graph.node_count == 1
    cell = store.state.coverage_map.cells["companies/Acme.Revenue"]
    assert cell.status.value == "filled"
    assert cell.display_hint == "1234"


@pytest.mark.asyncio
async def test_read_visual_page_observation_commits_and_binds_in_web_scope() -> None:
    state = _state()
    state.source_scope = {"mode": "web", "documents": []}
    state.frontier.add(
        FrontierTask(
            id="read-chart",
            question="Read the chart",
            table_id="companies",
            result_mode="table",
        )
    )
    store = InMemoryEvidenceStore(state)
    coordinator = ExtractionCoordinator(
        ScriptedJudge([_row()]),
        store,
        config=ExtractionConfig(dual_mode=False),
    )
    observation = replace(
        _observation(),
        content=(
            "来源：https://example.com/chart.png\n读取方式：local_vision\n\n"
            "原始内容 OCR 转录：Acme reported revenue of 1234 million in 2025."
        ),
        source_url="https://example.com/chart.png",
        task_id="read-chart",
    )

    receipt = await coordinator.submit(observation, delivery=DeliveryMode.SYNC)

    assert len(receipt.committed_node_ids) == 1
    node = store.state.evidence_graph.get_node(receipt.committed_node_ids[0])
    assert node is not None and node.source == "https://example.com/chart.png"
    assert node.local_source_metadata is None
    assert [(item.task_id, item.evidence_id) for item in store.state.evidence_graph.task_bindings] == [
        ("read-chart", node.id)
    ]


@pytest.mark.asyncio
async def test_fill_commits_before_discover_reads_the_refreshed_table() -> None:
    store = InMemoryEvidenceStore(_state())
    judge = PhaseOrderJudge(store)
    coordinator = ExtractionCoordinator(
        judge,
        store,
        config=ExtractionConfig(dual_mode=True),
    )

    receipt = await coordinator.submit(_mixed_observation(), delivery=DeliveryMode.SYNC)

    assert judge.events == ["fill_start", "fill_end", "discover_start"]
    assert judge.discover_saw_fill_commit is True
    assert len(receipt.committed_node_ids) == 2
    assert "Beta" in store.state.coverage_map.tables["companies"].entities


@pytest.mark.asyncio
async def test_long_skill_json_is_batched_by_record_count_in_each_phase() -> None:
    judge = PromptCaptureJudge()
    coordinator = ExtractionCoordinator(
        judge,
        InMemoryEvidenceStore(_state()),
        config=ExtractionConfig(
            dual_mode=True,
            chunk_char_budget=100_000,
            chunk_max_records=2,
        ),
    )
    payload = json.dumps(
        {
            "success": True,
            "data": [
                {"record_id": index, "name": f"Company {index}", "revenue": index * 100}
                for index in range(5)
            ],
        }
    )

    await coordinator.submit(
        EvidenceObservation(
            content=payload,
            source_url="skill://bulk-companies",
            target_table="companies",
        ),
        delivery=DeliveryMode.SYNC,
    )

    fill_prompts = [prompt for prompt in judge.prompts if "FILL MODE" in prompt]
    discover_prompts = [prompt for prompt in judge.prompts if "DISCOVER MODE" in prompt]
    assert len(fill_prompts) == 3
    assert len(discover_prompts) == 3
    assert sum(prompt.count('"record_id"') for prompt in fill_prompts) == 5
    assert sum(prompt.count('"record_id"') for prompt in discover_prompts) == 5
    assert all(prompt.count('"record_id"') <= 2 for prompt in judge.prompts)


def test_skill_json_chunks_preserve_metadata_and_add_chunk_context() -> None:
    payload = json.dumps(
        {
            "success": True,
            "title": "Top 100 TV Shows",
            "items_count": 5,
            "items": [{"rank": index, "title": f"Show {index}"} for index in range(1, 6)],
        }
    )

    segs = ObservationPreparer._split_skill_json(payload, 100_000, max_records=2)

    assert segs is not None
    chunks = [json.loads(seg) for seg in segs]
    assert len(chunks) == 3
    assert all(chunk["success"] is True for chunk in chunks)
    assert all(chunk["title"] == "Top 100 TV Shows" for chunk in chunks)
    assert all(chunk["items_count"] == 5 for chunk in chunks)
    assert [chunk["_searchos_chunk"]["chunk_index"] for chunk in chunks] == [1, 2, 3]
    assert [chunk["_searchos_chunk"]["record_start_1based"] for chunk in chunks] == [1, 3, 5]
    assert [chunk["_searchos_chunk"]["record_end_1based"] for chunk in chunks] == [2, 4, 5]
    assert all(chunk["_searchos_chunk"]["chunk_count"] == 3 for chunk in chunks)
    assert all(chunk["_searchos_chunk"]["split_field"] == "items" for chunk in chunks)


def test_top_level_skill_array_chunks_are_wrapped_with_chunk_context() -> None:
    payload = json.dumps([{"rank": index} for index in range(1, 6)])

    segs = ObservationPreparer._split_skill_json(payload, 100_000, max_records=2)

    assert segs is not None
    chunks = [json.loads(seg) for seg in segs]
    assert len(chunks) == 3
    assert all(set(chunk) == {"_searchos_chunk", "records"} for chunk in chunks)
    assert [chunk["_searchos_chunk"]["record_start_1based"] for chunk in chunks] == [1, 3, 5]
    assert sum(len(chunk["records"]) for chunk in chunks) == 5


@pytest.mark.asyncio
async def test_top_level_skill_json_array_uses_the_same_record_batching() -> None:
    judge = PromptCaptureJudge()
    coordinator = ExtractionCoordinator(
        judge,
        InMemoryEvidenceStore(_state()),
        config=ExtractionConfig(
            dual_mode=True,
            chunk_char_budget=100_000,
            chunk_max_records=2,
        ),
    )
    payload = json.dumps(
        [{"record_id": index, "revenue": index * 100} for index in range(5)]
    )

    await coordinator.submit(
        EvidenceObservation(
            content=payload,
            source_url="skill://top-level-array",
            target_table="companies",
        ),
        delivery=DeliveryMode.SYNC,
    )

    assert len([p for p in judge.prompts if "FILL MODE" in p]) == 3
    assert len([p for p in judge.prompts if "DISCOVER MODE" in p]) == 3
    assert all(prompt.count('"record_id"') <= 2 for prompt in judge.prompts)


@pytest.mark.asyncio
async def test_concurrent_duplicate_observations_are_reserved_once() -> None:
    judge = ScriptedJudge([_row()])
    store = InMemoryEvidenceStore(_state())
    coordinator = ExtractionCoordinator(
        judge,
        store,
        batch_n=10,
        config=ExtractionConfig(dual_mode=False),
    )

    receipts = await asyncio.gather(
        coordinator.submit(_observation()),
        coordinator.submit(_observation()),
    )
    summary = await coordinator.finalize()

    assert sum(receipt.accepted for receipt in receipts) == 1
    assert sum(receipt.duplicate for receipt in receipts) == 1
    assert summary.accepted == 1
    assert summary.duplicates == 1
    assert summary.buffered == 0
    assert judge.calls == 1
    assert store.state.evidence_graph.node_count == 1


@pytest.mark.asyncio
async def test_finalize_is_idempotent_and_reports_no_pending_work() -> None:
    judge = ScriptedJudge([_row()])
    coordinator = ExtractionCoordinator(
        judge,
        InMemoryEvidenceStore(_state()),
        batch_n=10,
        config=ExtractionConfig(dual_mode=False),
    )
    await coordinator.submit(_observation())

    first = await coordinator.finalize()
    second = await coordinator.finalize()

    assert first.committed_node_ids == second.committed_node_ids
    assert second.buffered == 0
    assert second.in_flight == 0
    assert judge.calls == 1


@pytest.mark.asyncio
async def test_explicit_flush_reuses_only_same_agent_same_source_context() -> None:
    first_judge = PromptCaptureJudge()
    first = ExtractionCoordinator(
        first_judge,
        InMemoryEvidenceStore(_state()),
        batch_n=10,
        config=ExtractionConfig(dual_mode=False),
    )
    window_one = replace(
        _observation(),
        content=("UNIQUE-HEADER Company | Revenue. " + "header context " * 8),
    )
    window_two = replace(
        _observation(),
        content=("UNIQUE-CONTINUATION Acme | 1234. " + "continued row " * 8),
    )

    await first.submit(window_one)
    await first.flush(reason="test")
    assert len(first_judge.prompts) == 1
    assert "UNIQUE-HEADER" in first_judge.prompts[0]

    await first.submit(window_two)
    await first.flush(reason="test")
    assert len(first_judge.prompts) == 2
    assert "UNIQUE-HEADER" in first_judge.prompts[1]
    assert "UNIQUE-CONTINUATION" in first_judge.prompts[1]
    assert "retained context on same page" in first_judge.prompts[1]

    # A different ExtractionCoordinator represents a different sub-agent and must not
    # inherit the first agent's source history, even for the identical URL.
    second_judge = PromptCaptureJudge()
    second = ExtractionCoordinator(
        second_judge,
        InMemoryEvidenceStore(_state()),
        batch_n=10,
        config=ExtractionConfig(dual_mode=False),
    )
    await second.submit(window_two)
    await second.flush(reason="test")
    assert len(second_judge.prompts) == 1
    assert "UNIQUE-CONTINUATION" in second_judge.prompts[0]
    assert "UNIQUE-HEADER" not in second_judge.prompts[0]
    assert "retained context on same page" not in second_judge.prompts[0]


@pytest.mark.asyncio
async def test_parse_failure_releases_hash_for_one_retry() -> None:
    judge = SequenceJudge(["not-json", json.dumps([_row()])])
    coordinator = ExtractionCoordinator(
        judge,
        InMemoryEvidenceStore(_state()),
        batch_n=10,
        config=ExtractionConfig(dual_mode=False),
    )

    first = await coordinator.submit(_observation(), delivery=DeliveryMode.SYNC)
    second = await coordinator.submit(_observation(), delivery=DeliveryMode.SYNC)

    assert first.accepted is True
    assert first.committed_nodes == ()
    assert second.accepted is True
    assert second.duplicate is False
    assert len(second.committed_node_ids) == 1
    assert judge.calls == 2


@pytest.mark.asyncio
async def test_same_table_flushes_serialize_snapshot_judge_commit() -> None:
    judge = ConcurrentJudge([_row()])
    coordinator = ExtractionCoordinator(
        judge,
        InMemoryEvidenceStore(_state()),
        batch_n=1,
        config=ExtractionConfig(flush_concurrency=2, dual_mode=False),
    )
    first = _observation()
    second = replace(
        first,
        content=first.content + " Additional independently captured viewport.",
        source_url="https://example.com/acme-results-2",
    )

    await coordinator.submit(first)
    await asyncio.sleep(0)
    await coordinator.submit(second)
    summary = await coordinator.finalize()

    assert judge.calls == 2
    assert judge.max_active == 1
    assert summary.in_flight == 0
