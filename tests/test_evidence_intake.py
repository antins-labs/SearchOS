"""Evidence Intake Interface 的端到端契约。"""

from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from types import SimpleNamespace

import pytest

from searchos.harness.middleware.extraction.intake import (
    DeliveryMode,
    EvidenceIntake,
    EvidenceObservation,
    InMemoryEvidenceStore,
    IntakeConfig,
)
from searchos.socm import SearchState


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


def test_middleware_is_only_an_intake_adapter() -> None:
    from searchos.harness.middleware.extraction import EvidenceExtractionMiddleware

    assert not hasattr(EvidenceExtractionMiddleware, "_flush_snapshot")
    assert not hasattr(EvidenceExtractionMiddleware, "_run_row_judge")
    assert not hasattr(EvidenceExtractionMiddleware, "_ingest_rows")


def test_long_skill_result_returns_a_bounded_agent_preview() -> None:
    from searchos.harness.middleware.extraction.context import render_skill_context

    payload = json.dumps(
        {
            "success": True,
            "title": "Bulk company results",
            "data": [
                {"record_id": index, "marker": f"UNIQUE-{index}", "value": "x" * 80}
                for index in range(20)
            ],
        }
    )

    rendered = render_skill_context(
        payload,
        source_url="skill://bulk-companies",
        committed_count=7,
        max_chars=700,
        preview_records=2,
        feedback="[Extraction feedback] 7 findings recorded this batch.",
    )

    assert len(rendered) <= 700
    assert "完整返回已完成分批 FILL → DISCOVER" in rendered
    assert "不要仅因预览截断而重复调用" in rendered
    assert "已写入 Evidence Graph：7" in rendered
    assert "7 findings recorded" in rendered
    assert "UNIQUE-0" in rendered
    assert "UNIQUE-1" in rendered
    assert "UNIQUE-2" not in rendered


def test_explore_replay_uses_the_extraction_model_without_a_judge_model() -> None:
    from searchos.tools.schema import _select_replay_model

    extraction_model = object()
    context = SimpleNamespace(extraction_model=extraction_model, judge_model=None)

    assert _select_replay_model(context) is extraction_model


@pytest.mark.asyncio
async def test_sync_submit_commits_evidence_and_coverage_atomically() -> None:
    store = InMemoryEvidenceStore(_state())
    intake = EvidenceIntake(
        ScriptedJudge([_row()]),
        store,
        batch_n=10,
        config=IntakeConfig(dual_mode=False),
    )

    receipt = await intake.submit(_observation(), delivery=DeliveryMode.SYNC)

    assert receipt.accepted is True
    assert len(receipt.committed_node_ids) == 1
    assert receipt.committed_node_ids == tuple(intake.committed_node_ids)
    assert store.state.evidence_graph.node_count == 1
    cell = store.state.coverage_map.cells["companies/Acme.Revenue"]
    assert cell.status.value == "filled"
    assert cell.display_hint == "1234"


@pytest.mark.asyncio
async def test_fill_commits_before_discover_reads_the_refreshed_table() -> None:
    store = InMemoryEvidenceStore(_state())
    judge = PhaseOrderJudge(store)
    intake = EvidenceIntake(
        judge,
        store,
        config=IntakeConfig(dual_mode=True),
    )

    receipt = await intake.submit(_mixed_observation(), delivery=DeliveryMode.SYNC)

    assert judge.events == ["fill_start", "fill_end", "discover_start"]
    assert judge.discover_saw_fill_commit is True
    assert len(receipt.committed_node_ids) == 2
    assert "Beta" in store.state.coverage_map.tables["companies"].entities


@pytest.mark.asyncio
async def test_long_skill_json_is_batched_by_record_count_in_each_phase() -> None:
    judge = PromptCaptureJudge()
    intake = EvidenceIntake(
        judge,
        InMemoryEvidenceStore(_state()),
        config=IntakeConfig(
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

    await intake.submit(
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


@pytest.mark.asyncio
async def test_top_level_skill_json_array_uses_the_same_record_batching() -> None:
    judge = PromptCaptureJudge()
    intake = EvidenceIntake(
        judge,
        InMemoryEvidenceStore(_state()),
        config=IntakeConfig(
            dual_mode=True,
            chunk_char_budget=100_000,
            chunk_max_records=2,
        ),
    )
    payload = json.dumps(
        [{"record_id": index, "revenue": index * 100} for index in range(5)]
    )

    await intake.submit(
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
    intake = EvidenceIntake(
        judge,
        store,
        batch_n=10,
        config=IntakeConfig(dual_mode=False),
    )

    receipts = await asyncio.gather(
        intake.submit(_observation()),
        intake.submit(_observation()),
    )
    summary = await intake.finalize()

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
    intake = EvidenceIntake(
        judge,
        InMemoryEvidenceStore(_state()),
        batch_n=10,
        config=IntakeConfig(dual_mode=False),
    )
    await intake.submit(_observation())

    first = await intake.finalize()
    second = await intake.finalize()

    assert first.committed_node_ids == second.committed_node_ids
    assert second.buffered == 0
    assert second.in_flight == 0
    assert judge.calls == 1


@pytest.mark.asyncio
async def test_parse_failure_releases_hash_for_one_retry() -> None:
    judge = SequenceJudge(["not-json", json.dumps([_row()])])
    intake = EvidenceIntake(
        judge,
        InMemoryEvidenceStore(_state()),
        batch_n=10,
        config=IntakeConfig(dual_mode=False),
    )

    first = await intake.submit(_observation(), delivery=DeliveryMode.SYNC)
    second = await intake.submit(_observation(), delivery=DeliveryMode.SYNC)

    assert first.accepted is True
    assert first.committed_nodes == ()
    assert second.accepted is True
    assert second.duplicate is False
    assert len(second.committed_node_ids) == 1
    assert judge.calls == 2


@pytest.mark.asyncio
async def test_same_table_flushes_serialize_snapshot_judge_commit() -> None:
    judge = ConcurrentJudge([_row()])
    intake = EvidenceIntake(
        judge,
        InMemoryEvidenceStore(_state()),
        batch_n=1,
        config=IntakeConfig(flush_concurrency=2, dual_mode=False),
    )
    first = _observation()
    second = replace(
        first,
        content=first.content + " Additional independently captured viewport.",
        source_url="https://example.com/acme-results-2",
    )

    await intake.submit(first)
    await asyncio.sleep(0)
    await intake.submit(second)
    summary = await intake.finalize()

    assert judge.calls == 2
    assert judge.max_active == 1
    assert summary.in_flight == 0
