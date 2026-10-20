"""Keep explicitly targeted extraction from filling unrelated requirement rows."""

import json
from types import SimpleNamespace

import pytest

from searchos.agents.orchestrator.lifecycle import _task_redundancy_reason
from searchos.harness.middleware.extraction import (
    DeliveryMode,
    EvidenceObservation,
    ExtractionConfig,
    ExtractionCoordinator,
    InMemoryEvidenceStore,
)
from searchos.socm import FrontierTask, SearchState

SOURCE = "https://docs.python.org/3.11/library/tomllib.html"
PASSAGE = "The tomllib module supports reading TOML configuration files."


async def _extract(
    *, target_cells, rows, policy="schema_facts", task_table="migration", clear_targets=False,
    extra_column=False,
):
    state = SearchState(intent="核对每个迁移需求，M1 读取 TOML，M2 使用 Self，M4 使用 TaskGroup。")
    state.coverage_map.add_table(
        "migration", ["Requirement", "API", *(["Notes"] if extra_column else [])],
        primary_key=["Requirement"],
        entities=["M1", "M2", "M4"],
    )
    state.frontier.add(FrontierTask(
        id="toml", question="核对 M1 的 TOML 读取功能。", result_mode="table",
        table_id=task_table, target_cells=target_cells,
    ))
    store = InMemoryEvidenceStore(state)

    class Judge:
        async def ainvoke(self, prompt):
            if clear_targets:
                store.state.frontier.questions[0].target_cells = []
            # 重放 H01 的错误模式：模型把同一 tomllib 页面映射到多个需求编号。
            return SimpleNamespace(content=json.dumps([
                {"Requirement": row, "API": "tomllib", "_source_excerpt": PASSAGE,
                 "_alignment": "full", "_confidence": "high",
                 **({"Notes": "reading TOML"} if extra_column else {})}
                for row in rows
            ]))

    coordinator = ExtractionCoordinator(
        Judge(), store, policy=policy,
        config=ExtractionConfig(dual_mode=False, cross_table_backfill=False),
    )
    receipt = await coordinator.submit(
        EvidenceObservation(
            task_id="toml", source_url=SOURCE, content=PASSAGE,
        ),
        delivery=DeliveryMode.SYNC,
    )
    assert receipt.accepted
    await coordinator.finalize()
    return store.state


@pytest.mark.asyncio
@pytest.mark.parametrize("policy", ["task_rows", "schema_facts"])
@pytest.mark.parametrize("qualified", [False, True])
async def test_explicit_target_cells_reject_other_rows_before_coverage(policy, qualified):
    target = "migration/M1.API" if qualified else "M1.API"
    state = await _extract(
        target_cells=[target], rows=["M1", "M2", "M4", "M5"], policy=policy,
        task_table="" if qualified and policy == "schema_facts" else "migration",
    )

    assert state.coverage_map.cells["migration/M1.API"].value == "tomllib"
    assert "M5" not in state.coverage_map.tables["migration"].entities
    for entity in ("M2", "M4"):
        cell = state.coverage_map.cells[f"migration/{entity}.API"]
        assert cell.status.value == "missing", f"M1 task contaminated {entity}: {cell.value}"
        assert not cell.supporting_evidence_ids


@pytest.mark.asyncio
async def test_off_target_candidate_cannot_make_pending_task_redundant():
    state = await _extract(target_cells=["M1.API"], rows=["M1", "M4"])

    assert _task_redundancy_reason(
        state, target_cells=["M4.API"], table_id="migration",
    ) == ""


@pytest.mark.asyncio
async def test_explicit_target_does_not_fill_other_columns_in_allowed_row():
    state = await _extract(target_cells=["M1.API"], rows=["M1"], extra_column=True)

    assert state.coverage_map.cells["migration/M1.API"].value == "tomllib"
    assert state.coverage_map.cells["migration/M1.Notes"].status.value == "missing"


@pytest.mark.asyncio
async def test_task_target_removal_during_extraction_does_not_widen_write_scope():
    state = await _extract(
        target_cells=["M1.API"], rows=["M1", "M4"], clear_targets=True,
    )

    assert state.coverage_map.cells["migration/M1.API"].value == "tomllib"
    assert state.coverage_map.cells["migration/M4.API"].status.value == "missing"


@pytest.mark.asyncio
async def test_task_without_explicit_targets_keeps_open_discovery():
    state = await _extract(target_cells=[], rows=["M1", "M2", "M4", "M5"])

    assert set(state.coverage_map.tables["migration"].entities) == {"M1", "M2", "M4", "M5"}
    assert all(
        state.coverage_map.cells[f"migration/{entity}.API"].value == "tomllib"
        for entity in ("M1", "M2", "M4", "M5")
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("target", ["not-a-cell", "missing/M1.API", "migration/M1.unknown"])
async def test_unresolvable_explicit_scope_never_becomes_open_discovery(target):
    state = await _extract(target_cells=[target], rows=["M1", "M2", "M4", "M5"])

    assert "M5" not in state.coverage_map.tables["migration"].entities
    assert all(
        state.coverage_map.cells[f"migration/{entity}.API"].status.value == "missing"
        for entity in ("M1", "M2", "M4")
    )
