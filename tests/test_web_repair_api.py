"""Targeted coverage-cell repair API regression tests."""

# ruff: noqa: E402, I001

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

_REPO = Path(__file__).resolve().parent.parent
for path in (str(_REPO), str(_REPO / "web")):
    if path not in sys.path:
        sys.path.insert(0, path)

from api.routes import search
from searchos.agents.orchestrator.scheduler import Scheduler
from searchos.socm import CellStatus, FrontierTask, FrontierTaskStatus, SearchState
from searchos.socm.workspace import WorkspaceManager


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


def test_repair_request_accepts_repair_all_selection():
    cells = [_cell(f"Entity {index}", "revenue") for index in range(42)]

    request = search.RepairRequest(cells=cells)

    assert len(request.cells) == 42


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


def test_repair_endpoint_delegates_exact_cell_allowlist_to_orchestrator(monkeypatch):
    state = _state()
    captured: dict[str, object] = {}

    async def fake_launch(**kwargs):
        captured.update(kwargs)
        return search.SearchResponse(session_id="session", status="running")

    monkeypatch.setattr(search, "_load_prior_state", lambda _session_id: state)
    monkeypatch.setattr(search, "_launch_search", fake_launch)
    monkeypatch.setattr(search, "init_search_provider", lambda _provider: None)
    search.sessions.clear()

    response = asyncio.run(search.repair_cells(
        "session",
        search.RepairRequest(cells=[_cell("Acme", "revenue"), _cell("Beta", "employees")]),
    ))

    assert response.status == "running"
    assert response.planner == "orchestrator"
    assert response.planning_latency_ms == 0
    assert response.task_ids == []
    assert "targeted_repair_task_ids" not in captured
    assert captured["targeted_repair_cells"] == [
        "_default/Acme.revenue",
        "_default/Beta.employees",
    ]
    assert captured["follow_up"] is True
    assert not any(task.created_by == "user" for task in state.frontier.questions)


def test_orchestrator_repair_enqueue_is_scope_checked_and_dynamically_allowed(
    tmp_path,
    monkeypatch,
):
    from searchos.agents.runtime import set_orchestrator_context
    from searchos.tools import tasks as task_tools

    workspace = WorkspaceManager(tmp_path, "orchestrator-repair")
    workspace.create()
    workspace.save_state(_state())
    set_orchestrator_context(
        workspace=workspace,
        model=cast(Any, object()),
        repair_target_allowlist={"_default/Acme.revenue"},
    )

    class FakeScheduler:
        def __init__(self):
            self.allowed: list[str] = []

        def allow_tasks(self, task_ids):
            self.allowed.extend(task_ids)

        async def tick(self):
            return {}

    scheduler = FakeScheduler()
    monkeypatch.setattr(task_tools, "_scheduler", lambda: scheduler)
    payload = [{
        "agent_type": "search_agent",
        "task": "Repair Acme revenue from an authoritative source",
        "target_table": "_default",
        "target_cells": ["_default/Acme.revenue"],
    }, {
        "agent_type": "search_agent",
        "task": "Also investigate an unselected cell",
        "target_table": "_default",
        "target_cells": ["Beta.employees"],
    }]

    result = json.loads(asyncio.run(task_tools.enqueue_tasks.ainvoke({
        "items_json": json.dumps(payload),
    })))

    assert len(result["queued"]) == 1
    assert len(result["rejected"]) == 1
    assert "outside repair allowlist" in result["rejected"][0]["reason"]
    assert scheduler.allowed == result["queued"]
    queued = next(
        task
        for task in workspace.load_state().frontier.questions
        if task.id in result["queued"]
    )
    assert queued.target_cells == ["Acme.revenue"]
    assert queued.planner == "orchestrator"


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


def test_looped_repair_agent_does_not_leave_frontier_task_running(tmp_path):
    from searchos.agents.orchestrator.lifecycle import _compute_agent_report
    from searchos.agents.runtime import _ctx, set_orchestrator_context

    workspace = WorkspaceManager(tmp_path, "repair-session")
    workspace.create()
    state = _state()
    state.frontier.add(FrontierTask(
        id="repair-task",
        question="Repair Acme revenue",
        status=FrontierTaskStatus.RUNNING,
        assigned_agent_id="search_agent",
        attempts=1,
        target_cells=["Acme.revenue"],
        table_id="_default",
        created_by="user",
    ))
    state.agent_status["search-agent-thread"] = "looped"
    workspace.save_state(state)

    set_orchestrator_context(
        workspace=workspace,
        model=cast(Any, object()),
        scheduler_task_allowlist={"repair-task"},
    )
    _ctx.agent_graphs["search_agent"] = {
        "agent_type": "search_agent",
        "assigned_task_id": "repair-task",
        "extraction_mw": None,
    }

    report = _compute_agent_report(
        agent_id="search_agent",
        thread_id="search-agent-thread",
        pre_snapshot={"evidence_ids": set(), "filled_keys": set()},
        started_at=0,
        status="completed",
        result="Completed",
        last_ai_text="Found an answer but produced no new evidence.",
    )

    repair = next(
        task for task in workspace.load_state().frontier.questions
        if task.id == "repair-task"
    )
    assert report.status == "looped"
    assert repair.status == FrontierTaskStatus.PENDING
    assert repair.assigned_agent_id == ""


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
