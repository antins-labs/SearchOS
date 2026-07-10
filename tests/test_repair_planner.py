"""Scope-safe LLM Repair Planner regression tests."""

# ruff: noqa: E402, I001

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from searchos.harness.repair_planner import (
    RepairTarget,
    RepairTaskPlan,
    plan_repair_tasks,
    render_repair_task_prompt,
    validate_repair_plan,
)
from searchos.socm import CellStatus, SearchState


def _state() -> SearchState:
    state = SearchState(intent="Compare theme parks")
    state.coverage_map.initialize(
        ["Universal Beijing"],
        ["rating", "heritage", "ticket_price"],
    )
    state.coverage_map.cells["_default/Universal Beijing.rating"].status = CellStatus.UNCERTAIN
    return state


def _targets() -> list[RepairTarget]:
    return [
        RepairTarget(table_id="_default", entity="Universal Beijing", attribute="rating"),
        RepairTarget(table_id="_default", entity="Universal Beijing", attribute="heritage"),
    ]


class FakeModel:
    def __init__(self, payload):
        self.payload = payload

    async def ainvoke(self, _messages):
        if isinstance(self.payload, Exception):
            raise self.payload
        return SimpleNamespace(content=json.dumps(self.payload, ensure_ascii=False))


@pytest.mark.asyncio
async def test_llm_plan_is_accepted_when_it_exactly_covers_targets():
    outcome = await plan_repair_tasks(
        _state(),
        _targets(),
        model=FakeModel({
            "tasks": [{
                "table_id": "_default",
                "entity": "Universal Beijing",
                "attributes": ["heritage", "rating"],
                "title": "Verify official classifications",
                "search_queries": ["Universal Beijing official scenic rating"],
                "preferred_sources": ["Beijing culture and tourism authority"],
                "acceptance_criteria": "Use a direct official listing for each classification.",
            }],
        }),
    )

    assert outcome.planner == "llm"
    assert outcome.warning is None
    assert outcome.tasks[0].attributes == ["rating", "heritage"]
    assert outcome.tasks[0].search_queries == ["Universal Beijing official scenic rating"]


@pytest.mark.asyncio
async def test_llm_plan_with_hallucinated_cell_uses_fallback():
    outcome = await plan_repair_tasks(
        _state(),
        _targets(),
        model=FakeModel({
            "tasks": [{
                "table_id": "_default",
                "entity": "Universal Beijing",
                "attributes": ["rating", "opening_hours"],
            }],
        }),
    )

    assert outcome.planner == "deterministic"
    assert outcome.warning
    assert outcome.tasks[0].attributes == ["rating", "heritage"]


@pytest.mark.asyncio
async def test_llm_failure_uses_fallback_without_losing_targets():
    outcome = await plan_repair_tasks(
        _state(),
        _targets(),
        model=FakeModel(RuntimeError("provider unavailable")),
    )

    assert outcome.planner == "deterministic"
    assert {
        (task.table_id, task.entity, attribute)
        for task in outcome.tasks
        for attribute in task.attributes
    } == {
        ("_default", "Universal Beijing", "rating"),
        ("_default", "Universal Beijing", "heritage"),
    }


def test_plan_validation_rejects_duplicate_or_missing_targets():
    with pytest.raises(ValueError, match="repeated"):
        validate_repair_plan([
            RepairTaskPlan(
                table_id="_default",
                entity="Universal Beijing",
                attributes=["rating", "rating"],
            ),
        ], _targets())

    with pytest.raises(ValueError, match="cover every"):
        validate_repair_plan([
            RepairTaskPlan(
                table_id="_default",
                entity="Universal Beijing",
                attributes=["rating"],
            ),
        ], _targets())


def test_rendered_prompt_keeps_strategy_and_hard_scope():
    prompt = render_repair_task_prompt(RepairTaskPlan(
        table_id="_default",
        entity="Universal Beijing",
        attributes=["rating"],
        search_queries=["official rating registry"],
        preferred_sources=["Government registry"],
        acceptance_criteria="Direct official evidence",
    ))

    assert "official rating registry" in prompt
    assert "Government registry" in prompt
    assert "Direct official evidence" in prompt
    assert "do not add entities, columns, tables" in prompt
