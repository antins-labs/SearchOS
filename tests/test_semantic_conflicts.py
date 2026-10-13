"""冲突判定区分表述差异、缺失信息和同口径互斥断言。"""

import json

import pytest

from searchos.harness.middleware.extraction.core.commit import ingest_rows
from searchos.harness.middleware.extraction.core.store import InMemoryEvidenceStore
from searchos.socm import ColumnDesc, EvidenceNode, SearchState
from searchos.socm.coverage import commit_evidence


def state_with_values(*values, description="概念的定义与核心特征"):
    state = SearchState()
    state.coverage_map.initialize(
        ["RSI"],
        ["Name", "Definition"],
        primary_key=["Name"],
        table_id="concepts",
        column_desc={"Definition": ColumnDesc(desc=description)},
    )
    commit_evidence(
        state,
        [
            EvidenceNode(
                id=f"f{i}",
                table_id="concepts",
                entity="RSI",
                attribute="Definition",
                value=value,
                source=f"https://example.org/{i}",
                source_excerpt=value,
                span=(0, len(value)),
                alignment="full",
            )
            for i, value in enumerate(values)
        ],
    )
    return state


KEY = "concepts/RSI.Definition"


def test_rewording_does_not_set_conflict_before_semantic_review():
    state = state_with_values(
        "AI improves its own capabilities.",
        "人工智能改进自身能力。",
    )
    assert not state.coverage_map.cells[KEY].has_conflict


@pytest.mark.parametrize(
    "value",
    [
        [],
        {},
        "[]",
        "{}",
        None,
        "The provided page does not contain information about this concept.",
    ],
)
def test_missing_extraction_values_are_not_facts(value):
    state = state_with_values()
    nodes, _ = ingest_rows(
        [
            (
                {"Name": "RSI", "Definition": value},
                "RSI is described here.",
                "https://example.org",
                "fill",
            )
        ],
        "concepts",
        state,
    )
    assert nodes == []
    assert state.coverage_map.cells[KEY].status.value == "missing"


class ComparisonJudge:
    def __init__(self, verdict="compatible", review_verdict=None, mutate=None):
        self.verdict = verdict
        self.review_verdict = review_verdict or verdict
        self.mutate = mutate
        self.prompts = []
        self.payloads = []

    async def __call__(self, prompt):
        self.prompts.append(prompt)
        pairs = json.loads(prompt.split("INPUT_JSON:\n", 1)[1])
        self.payloads.append(pairs)
        if self.mutate:
            self.mutate()
        verdict = self.review_verdict if "这是独立复核" in prompt else self.verdict
        return json.dumps(
            [
                {
                    "id": p["id"],
                    "verdict": verdict,
                    "reason": "核对目标属性及来源",
                    "supported_a": True,
                    "supported_b": True,
                    "same_scope": True,
                    "scope": "相同条件下的方法表现",
                    "quote_a": p["a"]["excerpt"],
                    "quote_b": p["b"]["excerpt"],
                }
                for p in pairs
            ]
        )


async def review(store, judge, **kwargs):
    from searchos.harness.middleware.extraction.core.conflicts import ConflictReviewer

    return await ConflictReviewer(store, judge, **kwargs).review({KEY})


@pytest.mark.asyncio
async def test_compatible_rewording_is_batched_and_persistently_cached():
    store = InMemoryEvidenceStore(
        state_with_values(
            "AI improves itself.",
            "人工智能改进自身能力。",
            "AI enhances its own capabilities.",
        )
    )
    judge = ComparisonJudge()
    result = await review(store, judge)
    assert result == {"pairs": 3, "calls": 1, "applied": 3}
    assert store.state.coverage_map.cells[KEY].conflict_status == "clear"
    assert not store.state.coverage_map.cells[KEY].has_conflict
    reloaded = InMemoryEvidenceStore(SearchState.model_validate_json(store.state.model_dump_json()))
    assert (await review(reloaded, judge))["calls"] == 0
    assert len(judge.prompts) == 1


@pytest.mark.asyncio
async def test_long_claims_are_compared_in_full_and_conflict_needs_reverse_review():
    prefix = "This is the same setup and experimental condition. " * 6
    store = InMemoryEvidenceStore(
        state_with_values(prefix + "Always works.", prefix + "Never works.")
    )
    judge = ComparisonJudge("contradictory")
    await review(store, judge)
    cell = store.state.coverage_map.cells[KEY]
    assert cell.has_conflict and cell.conflict_status == "confirmed"
    assert set(cell.conflict_evidence_ids) == {"f0", "f1"}
    assert len(judge.prompts) == 2
    assert judge.payloads[0][0]["a"] == judge.payloads[1][0]["b"]
    assert judge.payloads[0][0]["a"]["value"].endswith("Always works.")
    record = next(iter(store.state.coverage_map.evidence_comparisons[KEY].values()))
    assert record.verified and record.left_quote and record.right_quote and record.scope


@pytest.mark.asyncio
async def test_failed_reverse_review_keeps_uncertain_without_conflict():
    store = InMemoryEvidenceStore(state_with_values("Works.", "Does not work."))
    await review(store, ComparisonJudge("contradictory", "compatible"))
    assert not store.state.coverage_map.cells[KEY].has_conflict
    assert store.state.coverage_map.cells[KEY].conflict_status == "uncertain"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field,value",
    [
        ("quote_a", "fabricated quotation"),
        ("same_scope", False),
        ("supported_b", False),
        ("scope", ""),
    ],
)
async def test_unsupported_conflict_cannot_pass(field, value):
    store = InMemoryEvidenceStore(state_with_values("Works.", "Does not work."))
    base = ComparisonJudge("contradictory")

    async def judge(prompt):
        rows = json.loads(await base(prompt))
        rows[0][field] = value
        return json.dumps(rows)

    await review(store, judge)
    assert not store.state.coverage_map.cells[KEY].has_conflict
    assert len(base.prompts) == 1
    assert store.state.coverage_map.cells[KEY].conflict_status == "uncertain"


@pytest.mark.asyncio
@pytest.mark.parametrize("raw", ["OK", "[]", '{"verdict":"contradictory"}'])
async def test_malformed_or_missing_response_is_unknown_and_not_retried_each_refresh(raw):
    store = InMemoryEvidenceStore(state_with_values("Works.", "Does not work."))
    calls = 0

    async def judge(prompt):
        nonlocal calls
        calls += 1
        return raw

    await review(store, judge)
    await review(store, judge)
    assert calls == 1
    assert store.state.coverage_map.cells[KEY].conflict_status == "uncertain"
    record = next(iter(store.state.coverage_map.evidence_comparisons[KEY].values()))
    assert record.retry_after > 0


@pytest.mark.asyncio
async def test_budget_never_truncates_evidence_to_make_a_decision():
    store = InMemoryEvidenceStore(state_with_values("x" * 2000 + "yes", "x" * 2000 + "no"))
    judge = ComparisonJudge("contradictory")
    await review(store, judge, batch_chars=1000)
    assert not judge.prompts
    assert store.state.coverage_map.cells[KEY].conflict_status == "uncertain"


@pytest.mark.asyncio
async def test_schema_and_source_changes_invalidate_comparison_cache():
    store = InMemoryEvidenceStore(state_with_values("Works.", "Does not work."))
    judge = ComparisonJudge()
    await review(store, judge)
    store.state.coverage_map.tables["concepts"].column_desc["Definition"].desc = "新口径"
    await review(store, judge)
    store.state.evidence_graph.nodes[0].source_excerpt = "A different source excerpt."
    await review(store, judge)
    assert len(judge.prompts) == 3


@pytest.mark.asyncio
async def test_concurrent_change_discards_stale_model_result():
    store = InMemoryEvidenceStore(state_with_values("Works.", "Does not work."))

    def change():
        store.state.evidence_graph.nodes[1].value = "Works."

    result = await review(store, ComparisonJudge("contradictory", mutate=change))
    assert result["applied"] == 0
    assert not store.state.coverage_map.cells[KEY].has_conflict
    assert not store.state.coverage_map.evidence_comparisons


@pytest.mark.asyncio
async def test_withdrawal_clears_active_conflict_but_preserves_history():
    from searchos.socm.coverage import refresh_cells

    store = InMemoryEvidenceStore(state_with_values("Works.", "Does not work."))
    await review(store, ComparisonJudge("contradictory"))
    store.state.evidence_graph.nodes[1].status = "superseded"
    refresh_cells(store.state, {KEY})
    cell = store.state.coverage_map.cells[KEY]
    assert not cell.has_conflict
    assert cell.conflict_evidence_ids == []
    assert set(cell.conflict_history_evidence_ids) == {"f0", "f1"}


@pytest.mark.asyncio
async def test_new_evidence_compares_against_all_distinct_claims_not_only_winner():
    store = InMemoryEvidenceStore(state_with_values("A", "B"))
    judge = ComparisonJudge()
    await review(store, judge)
    commit_evidence(
        store.state,
        [
            EvidenceNode(
                id="f2",
                table_id="concepts",
                entity="RSI",
                attribute="Definition",
                value="C",
                source="https://example.org/c",
                source_excerpt="C",
                span=(0, 1),
            )
        ],
    )
    result = await review(store, judge)
    assert result["pairs"] == 2
    assert len(judge.payloads[-1]) == 2


@pytest.mark.asyncio
async def test_equal_values_with_different_provenance_need_no_model():
    store = InMemoryEvidenceStore(state_with_values("Works.", "Works."))
    judge = ComparisonJudge()
    assert (await review(store, judge))["calls"] == 0
    assert store.state.coverage_map.cells[KEY].conflict_status == "clear"


@pytest.mark.asyncio
async def test_concurrent_reviewers_share_inflight_work():
    import asyncio

    store = InMemoryEvidenceStore(state_with_values("A", "B"))
    base = ComparisonJudge()

    async def judge(prompt):
        await asyncio.sleep(0)
        return await base(prompt)

    await asyncio.gather(review(store, judge), review(store, judge))
    assert len(base.prompts) == 1


@pytest.mark.asyncio
async def test_call_cancellation_is_propagated_without_cached_decision():
    import asyncio

    store = InMemoryEvidenceStore(state_with_values("A", "B"))

    async def judge(prompt):
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await review(store, judge)
    assert not store.state.coverage_map.evidence_comparisons


@pytest.mark.asyncio
async def test_invalid_verdict_type_does_not_abort_extraction():
    store = InMemoryEvidenceStore(state_with_values("A", "B"))
    base = ComparisonJudge()

    async def judge(prompt):
        rows = json.loads(await base(prompt))
        rows[0]["verdict"] = ["contradictory"]
        return json.dumps(rows)

    await review(store, judge)
    assert store.state.coverage_map.cells[KEY].conflict_status == "uncertain"


@pytest.mark.asyncio
async def test_bound_projection_change_cannot_reuse_a_cached_conflict():
    from searchos.socm.coverage import CellEvidenceBinding, bind_cell_evidence

    state = state_with_values()
    for fid, value in [("a", "Works."), ("b", "Does not work.")]:
        state.evidence_graph.add_node(
            EvidenceNode(
                id=fid,
                finding=value,
                source=f"https://example.org/{fid}",
                source_excerpt=value,
            )
        )
        bind_cell_evidence(state, [(KEY, CellEvidenceBinding(evidence_id=fid, value=value))])
    store = InMemoryEvidenceStore(state)
    await review(store, ComparisonJudge("contradictory"))
    assert store.state.coverage_map.cells[KEY].has_conflict
    store.state.coverage_map.evidence_bindings[KEY][1].value = "Works."
    from searchos.socm.coverage import refresh_cells

    refresh_cells(store.state, {KEY})
    assert not store.state.coverage_map.cells[KEY].has_conflict


@pytest.mark.asyncio
async def test_scheduler_does_not_count_resolved_history_or_inactive_edges(monkeypatch):
    from types import SimpleNamespace

    from searchos.agents.orchestrator import lifecycle
    from searchos.agents.orchestrator.scheduler import Scheduler
    from searchos.socm import EvidenceEdge, EvidenceRelation, EvidenceStatus
    from searchos.socm.coverage import refresh_cells

    state = state_with_values("Works.", "Does not work.")
    state.evidence_graph.add_edge(
        EvidenceEdge(
            from_id="f0",
            to_id="f1",
            relation=EvidenceRelation.CONFLICT,
        )
    )
    state.evidence_graph.nodes[1].status = EvidenceStatus.SUPERSEDED
    refresh_cells(state, {KEY})
    state.coverage_map.cells[KEY].conflict_history_evidence_ids = ["f0", "f1"]
    monkeypatch.setattr(lifecycle, "_ctx", SimpleNamespace(workspace=InMemoryEvidenceStore(state)))
    assert await Scheduler().detect_evidence_conflicts() == {"detected": 0, "enqueued": 0}


@pytest.mark.asyncio
async def test_extraction_commits_then_reviews_outside_atomic_write():
    from types import SimpleNamespace

    from searchos.harness.middleware.extraction import (
        DeliveryMode,
        EvidenceObservation,
        ExtractionConfig,
        ExtractionCoordinator,
    )

    class Store(InMemoryEvidenceStore):
        writing = False

        def atomic_update_state(self, updater):
            self.writing = True
            try:
                return super().atomic_update_state(updater)
            finally:
                self.writing = False

    store = Store(state_with_values("RSI always converges under condition C."))
    compare = ComparisonJudge("contradictory")

    class Judge:
        async def ainvoke(self, prompt):
            assert not store.writing
            if "INPUT_JSON:\n" in prompt:
                assert len(store.state.coverage_map.cells[KEY].supporting_evidence_ids) == 2
                return SimpleNamespace(content=await compare(prompt))
            return SimpleNamespace(
                content=json.dumps(
                    [
                        {
                            "Name": "RSI",
                            "Definition": "RSI never converges under condition C.",
                            "_source_excerpt": "RSI never converges under condition C.",
                            "_source_page": 1,
                        }
                    ]
                )
            )

    coordinator = ExtractionCoordinator(Judge(), store, config=ExtractionConfig(dual_mode=False))
    await coordinator.submit(
        EvidenceObservation(
            content=(
                "RSI never converges under condition C. This is the reported experimental result."
            ),
            source_url="https://example.org/new",
            target_table="concepts",
            result_mode="table",
        ),
        delivery=DeliveryMode.SYNC,
    )
    assert store.state.coverage_map.cells[KEY].has_conflict
    assert len(compare.prompts) == 2


@pytest.mark.asyncio
async def test_read_evidence_exposes_current_comparison_reasons():
    from searchos.tools.search_state import _workspace_var
    from searchos.tools.socm_read import read_evidence

    store = InMemoryEvidenceStore(state_with_values("Works.", "Does not work."))
    await review(store, ComparisonJudge("contradictory"))
    token = _workspace_var.set(store)
    try:
        output = json.loads(await read_evidence.ainvoke({"cell": KEY}))
        assert output["comparison_count"] == 1
        assert output["comparisons"][0]["verified"]
        assert output["comparisons"][0]["reason"]
    finally:
        _workspace_var.reset(token)


@pytest.mark.asyncio
async def test_scheduler_counts_active_explicit_conflict_once(monkeypatch):
    from types import SimpleNamespace

    from searchos.agents.orchestrator import lifecycle
    from searchos.agents.orchestrator.scheduler import Scheduler
    from searchos.socm import EvidenceEdge, EvidenceRelation

    state = state_with_values("Works.", "Does not work.")
    state.evidence_graph.add_edge(
        EvidenceEdge(
            from_id="f0",
            to_id="f1",
            relation=EvidenceRelation.CONFLICT,
        )
    )
    monkeypatch.setattr(lifecycle, "_ctx", SimpleNamespace(workspace=InMemoryEvidenceStore(state)))
    assert await Scheduler().detect_evidence_conflicts() == {"detected": 1, "enqueued": 0}
