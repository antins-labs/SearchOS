"""Targeted coverage-cell repair API regression tests."""

# ruff: noqa: E402, I001

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

_REPO = Path(__file__).resolve().parent.parent
for path in (str(_REPO), str(_REPO / "web")):
    if path not in sys.path:
        sys.path.insert(0, path)

from api.routes import search
from searchos.agents.orchestrator.scheduler import Scheduler
from searchos.socm import CellStatus, FrontierTask, SearchState


def _state() -> SearchState:
    state = SearchState(intent="Compare companies")
    state.coverage_map.initialize(
        ["Acme", "Beta"],
        ["company_id", "revenue", "employees"],
        primary_key=["company_id"],
    )
    state.coverage_map.cells["_default/Acme.revenue"].status = CellStatus.UNCERTAIN
    state.coverage_map.cells["_default/Beta.employees"].status = CellStatus.HARD_CELL
    return state


def _cell(entity: str, attribute: str) -> search.RepairCellRequest:
    return search.RepairCellRequest(
        table_id="_default",
        entity=entity,
        attribute=attribute,
    )


def test_prepare_repair_tasks_groups_by_table_and_entity_and_keeps_scope():
    state = _state()
    state.frontier.add(FrontierTask(
        id="unrelated",
        question="Find something else",
        target_cells=["Beta.revenue"],
        table_id="_default",
    ))

    task_ids, targets = search._prepare_repair_tasks(
        state,
        [_cell("Acme", "revenue"), _cell("Acme", "employees"), _cell("Acme", "revenue")],
    )

    assert len(task_ids) == 1
    assert targets == ["_default/Acme.revenue", "_default/Acme.employees"]
    repair = next(task for task in state.frontier.questions if task.id == task_ids[0])
    assert repair.target_cells == ["Acme.revenue", "Acme.employees"]
    assert repair.created_by == "user"
    assert repair.planner == "deterministic"
    assert "unrelated" not in task_ids
    unrelated = next(task for task in state.frontier.questions if task.id == "unrelated")
    assert unrelated.status.value == "pending"


def test_prepare_repair_tasks_supersedes_legacy_task_without_table_id():
    state = _state()
    state.frontier.add(FrontierTask(
        id="legacy",
        question="Find revenue",
        target_cells=["Acme.revenue"],
    ))

    search._prepare_repair_tasks(state, [_cell("Acme", "revenue")])

    legacy = next(task for task in state.frontier.questions if task.id == "legacy")
    assert legacy.status.value == "cancelled"
    assert legacy.resolution == "superseded by user targeted repair"


def test_prepare_repair_tasks_does_not_dedup_against_another_table():
    state = _state()
    state.coverage_map.add_table("financials", ["revenue"], entities=["Acme"])
    state.frontier.add(FrontierTask(
        id="other-table",
        question="Find financial revenue",
        target_cells=["Acme.revenue"],
        table_id="financials",
    ))

    task_ids, _ = search._prepare_repair_tasks(state, [_cell("Acme", "revenue")])

    assert task_ids != ["other-table"]
    other_table = next(task for task in state.frontier.questions if task.id == "other-table")
    assert other_table.status.value == "pending"
    repair = next(task for task in state.frontier.questions if task.id == task_ids[0])
    assert repair.table_id == "_default"


def test_prepare_repair_tasks_rejects_filled_and_unknown_cells():
    state = _state()
    state.coverage_map.cells["_default/Acme.revenue"].status = CellStatus.FILLED

    with pytest.raises(HTTPException) as exc:
        search._prepare_repair_tasks(
            state,
            [_cell("Acme", "revenue"), _cell("Unknown", "employees")],
        )

    assert exc.value.status_code == 422
    assert any("already filled" in message for message in exc.value.detail)
    assert any("Unknown entity" in message for message in exc.value.detail)
    assert not any(task.created_by == "user" for task in state.frontier.questions)


def test_prepare_repair_tasks_accepts_a_filled_conflicting_cell():
    state = _state()
    cell = state.coverage_map.cells["_default/Acme.revenue"]
    cell.status = CellStatus.FILLED
    cell.has_conflict = True

    task_ids, targets = search._prepare_repair_tasks(
        state,
        [_cell("Acme", "revenue")],
    )

    assert len(task_ids) == 1
    assert targets == ["_default/Acme.revenue"]


def test_repair_endpoint_passes_an_exact_scheduler_allowlist(monkeypatch):
    from searchos.harness import repair_planner

    state = _state()
    captured: dict[str, object] = {}

    async def fake_launch(**kwargs):
        captured.update(kwargs)
        return search.SearchResponse(session_id="session", status="running")

    monkeypatch.setattr(search, "_load_prior_state", lambda _session_id: state)
    monkeypatch.setattr(search, "_launch_search", fake_launch)
    monkeypatch.setattr(search, "init_search_provider", lambda _provider: None)
    monkeypatch.setattr(
        repair_planner,
        "plan_repair_tasks",
        AsyncMock(return_value=repair_planner.RepairPlanningOutcome(
            planner="llm",
            latency_ms=17,
            tasks=[
                repair_planner.RepairTaskPlan(
                    table_id="_default",
                    entity="Acme",
                    attributes=["revenue"],
                    title="Verify Acme revenue",
                    search_queries=["Acme official revenue"],
                ),
                repair_planner.RepairTaskPlan(
                    table_id="_default",
                    entity="Beta",
                    attributes=["employees"],
                    title="Verify Beta employees",
                    search_queries=["Beta official employee count"],
                ),
            ],
        )),
    )
    search.sessions.clear()

    response = asyncio.run(search.repair_cells(
        "session",
        search.RepairRequest(cells=[_cell("Acme", "revenue"), _cell("Beta", "employees")]),
    ))

    assert response.status == "running"
    assert response.planner == "llm"
    assert response.planning_latency_ms == 17
    assert len(response.task_ids) == 2
    assert captured["targeted_repair_task_ids"] == set(response.task_ids)
    assert captured["targeted_repair_cells"] == [
        "_default/Acme.revenue",
        "_default/Beta.employees",
    ]
    assert captured["follow_up"] is True
    repair_tasks = [task for task in state.frontier.questions if task.id in response.task_ids]
    assert all(task.planner == "llm" for task in repair_tasks)
    assert "Acme official revenue" in repair_tasks[0].task_prompt


def test_repair_endpoint_rejects_running_session():
    search.sessions["busy"] = {"status": "running"}
    try:
        with pytest.raises(HTTPException) as exc:
            asyncio.run(search.repair_cells(
                "busy",
                search.RepairRequest(cells=[_cell("Acme", "revenue")]),
            ))
        assert exc.value.status_code == 409
    finally:
        search.sessions.pop("busy", None)


def test_targeted_scheduler_disables_scope_expanding_stages(monkeypatch):
    scheduler = Scheduler(task_allowlist={"repair-task"})
    for method in (
        "drop_blocked_cycles",
        "unblock_ready_tasks",
        "reap_zombie_tasks",
        "drain_ready_tasks",
    ):
        monkeypatch.setattr(scheduler, method, AsyncMock(return_value={"action": method}))
    detect_conflicts = AsyncMock()
    spawn_writer = AsyncMock()
    continue_writer = AsyncMock()
    monkeypatch.setattr(scheduler, "detect_evidence_conflicts", detect_conflicts)
    monkeypatch.setattr(scheduler, "maybe_spawn_writer", spawn_writer)
    monkeypatch.setattr(scheduler, "maybe_continue_writer", continue_writer)

    result = asyncio.run(scheduler.tick())

    assert result["detect_evidence_conflicts"]["action"] == "disabled_targeted_repair"
    assert result["maybe_spawn_writer"]["action"] == "disabled_targeted_repair"
    assert result["maybe_continue_writer"]["action"] == "disabled_targeted_repair"
    detect_conflicts.assert_not_awaited()
    spawn_writer.assert_not_awaited()
    continue_writer.assert_not_awaited()
