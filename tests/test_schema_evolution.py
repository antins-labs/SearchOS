"""增列的原子性、历史证据保留与新增目标取证。"""

import json
from types import SimpleNamespace

import pytest

from searchos.socm import ColumnDesc, EvidenceNode, SearchState
from searchos.socm.coverage import commit_evidence
from searchos.socm.evidence import bind_task_evidence
from searchos.socm.frontier import FrontierTask
from searchos.socm.workspace import WorkspaceManager
from searchos.tools import schema as schema_tools


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    workspace = WorkspaceManager(tmp_path, "schema-evolution")
    workspace.create()
    state = SearchState(
        intent="Compare programmes",
        research_mode="findings",
        source_scope={"mode": "hybrid", "documents": []},
    )
    state.coverage_map.add_table(
        "programmes", ["Name", "Credits"], primary_key=["Name"], entities=["Alpha", "Excluded"]
    )
    state.frontier.add(FrontierTask(id="previous", question="Check credits", result_mode="table"))
    node = EvidenceNode(
        id="credits",
        source="https://example.org/alpha",
        finding="Alpha requires 120 credits.",
        value="120",
        source_excerpt="Alpha requires 120 credits.",
        entity="Alpha",
        attribute="Credits",
        table_id="programmes",
        alignment="full",
    )
    commit_evidence(state, [node])
    bind_task_evidence(state, "previous", ["credits"])
    state.coverage_map.remove_entity("Excluded", table_id="programmes", reason="Outside scope")
    workspace.save_state(state)
    monkeypatch.setattr(schema_tools, "_orch_ctx", lambda: SimpleNamespace(workspace=workspace))
    return workspace


@pytest.mark.asyncio
async def test_add_columns_preserves_existing_evidence_and_excluded_rows(workspace):
    before = workspace.load_state()
    args = {
        "table_id": "programmes",
        "columns_json": json.dumps(
            [
                {"name": "Duration", "type": "int", "desc": "Years", "check": {"min": 1}},
                {"name": "Mode"},
            ]
        ),
    }
    result = json.loads(await schema_tools.add_columns.ainvoke(args))
    state = workspace.load_state()
    assert result["added_columns"] == ["Duration", "Mode"] and result["new_missing_cells"] == 2
    assert state.evidence_graph == before.evidence_graph
    assert all(
        state.coverage_map.cells[key] == value for key, value in before.coverage_map.cells.items()
    )
    assert state.coverage_map.removed_cells == before.coverage_map.removed_cells
    assert state.coverage_map.tables["programmes"].primary_key == ["Name"]
    assert state.coverage_map.cells["programmes/Alpha.Duration"].status.value == "missing"
    assert not state.coverage_map.cells["programmes/Alpha.Duration"].supporting_evidence_ids
    assert "programmes/Excluded.Duration" not in state.coverage_map.cells
    assert json.loads(await schema_tools.add_columns.ainvoke(args))["added_columns"] == []
    assert workspace.load_state() == state
    state.coverage_map.restore_entity("Excluded", table_id="programmes")
    assert state.coverage_map.cells["programmes/Excluded.Duration"].status.value == "missing"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "columns",
    [
        [],
        {},
        [None],
        [{"name": ""}],
        [{"name": 2}],
        [{"name": " Rate "}],
        [{"name": "Fresh"}, {"name": "Credits", "desc": "New meaning"}],
        [{"name": "Fresh"}, {"name": "credits"}],
        [{"name": "Fresh"}, {"name": "Fresh"}],
        [{"name": "Fresh"}, {"name": "fresh"}],
        [{"name": "Fresh", "primary_key": True}],
        [{"name": "Fresh", "check": {"min": 9, "max": 1}}],
        [{"name": "Fresh", "check": {"min": float("inf")}}],
        [{"name": "Fresh", "check": {"typo": 1}}],
        [{"name": "Fresh", "check": {"enum": "ABC"}}],
        [{"name": "营收", "desc": "亿美元（USD Billion）"}],
    ],
)
async def test_add_columns_rejects_invalid_batch_without_partial_writes(workspace, columns):
    before = workspace.load_state().model_dump_json()
    result = await schema_tools.add_columns.ainvoke(
        {"table_id": "programmes", "columns_json": json.dumps(columns)}
    )
    assert result.startswith("Error:"), result
    assert workspace.load_state().model_dump_json() == before


@pytest.mark.asyncio
async def test_add_columns_rejects_unknown_table_and_alias_collision(workspace):
    before = workspace.load_state()
    result = await schema_tools.add_columns.ainvoke(
        {"table_id": "absent", "columns_json": '[{"name":"Duration"}]'}
    )
    assert result.startswith("Error:") and workspace.load_state() == before
    before.coverage_map.tables["programmes"].attribute_aliases["Study load"] = "Credits"
    workspace.save_state(before)
    result = await schema_tools.add_columns.ainvoke(
        {"table_id": "programmes", "columns_json": '[{"name":"Fresh"},{"name":"study_load"}]'}
    )
    assert result.startswith("Error:") and workspace.load_state() == before


def test_cell_key_collision_does_not_change_schema():
    state = SearchState()
    state.coverage_map.add_table(
        "items", ["Name", "B.C"], primary_key=["Name"], entities=["A", "A.B"]
    )
    before = state.model_dump_json()
    with pytest.raises(ValueError, match="Ambiguous cell key"):
        state.coverage_map.add_columns("items", {"Fresh": ColumnDesc(), "C": ColumnDesc()})
    assert state.model_dump_json() == before


@pytest.mark.asyncio
async def test_empty_table_gains_columns_without_inventing_rows(workspace):
    def create_empty(state):
        state.coverage_map.add_table("empty", ["Name"], primary_key=["Name"])
        return state

    workspace.atomic_update_state(create_empty)
    result = await schema_tools.add_columns.ainvoke(
        {"table_id": "empty", "columns_json": '[{"name":"Duration"}]'}
    )
    assert json.loads(result)["new_missing_cells"] == 0
    state = workspace.load_state()
    assert state.coverage_map.tables["empty"].attributes == ["Name", "Duration"]
    assert not state.coverage_map.tables["empty"].entities
    assert "empty" in state.coverage_map.empty_tables


@pytest.mark.asyncio
async def test_new_column_receives_original_source_evidence_in_new_task(workspace):
    from searchos.harness.middleware.extraction import (
        DeliveryMode,
        EvidenceObservation,
        ExtractionCoordinator,
    )

    calls = []

    class Extraction:
        async def ainvoke(self, prompt):
            calls.append(prompt)
            duration = "Duration" in prompt
            return SimpleNamespace(
                content=json.dumps(
                    [
                        {
                            "Name": "Alpha",
                            "Duration" if duration else "Credits": "3" if duration else "120",
                            "_source_excerpt": "Alpha lasts 3 years."
                            if duration
                            else "Alpha requires 120 credits.",
                            "_alignment": "full",
                            "_confidence": "high",
                        }
                    ]
                )
            )

    coordinator = ExtractionCoordinator(Extraction(), workspace)
    source = {
        "target_table": "programmes",
        "source_url": "https://example.org/alpha",
        "content": "Official programme requirements for 2026 entrants: Alpha requires 120 credits. Alpha lasts 3 years.",
    }
    await coordinator.submit(
        EvidenceObservation(task_id="previous", **source), delivery=DeliveryMode.SYNC
    )
    before = workspace.load_state()
    assert len(calls) == 1
    await schema_tools.add_columns.ainvoke(
        {
            "table_id": "programmes",
            "columns_json": '[{"name":"Duration","type":"int","desc":"Years"}]',
        }
    )

    def new_task(state):
        state.frontier.add(
            FrontierTask(
                id="duration",
                question="Check Alpha duration",
                table_id="programmes",
                target_cells=["programmes/Alpha.Duration"],
                result_mode="table",
            )
        )
        return state

    workspace.atomic_update_state(new_task)

    receipt = await coordinator.submit(
        EvidenceObservation(task_id="duration", **source), delivery=DeliveryMode.SYNC
    )
    state = workspace.load_state()
    assert receipt.committed_node_ids and not receipt.duplicate
    assert len(calls) > 1 and all("Duration" in prompt for prompt in calls[1:])
    assert state.coverage_map.cells["programmes/Alpha.Duration"].value == "3"
    assert state.coverage_map.cells["programmes/Alpha.Credits"].supporting_evidence_ids == [
        "credits"
    ]
    assert {
        b.evidence_id for b in state.evidence_graph.task_bindings if b.task_id == "duration"
    } == set(receipt.committed_node_ids)
    assert state.evidence_graph.get_node("credits").finding == "Alpha requires 120 credits."
    assert all(
        state.evidence_graph.get_node(node.id) == node for node in before.evidence_graph.nodes
    )


def test_orchestrator_exposes_add_columns():
    from searchos.agents.orchestrator import get_orchestrator_tools

    assert "add_columns" in {tool.name for tool in get_orchestrator_tools()}


@pytest.mark.asyncio
async def test_budget_exhaustion_blocks_column_growth(workspace):
    from searchos.harness.middleware.sensor.budget_middleware import BudgetMiddleware
    from searchos.harness.middleware.sensor.core.models import BudgetState, ControlState

    budget = BudgetState(max_iterations=1)
    budget.current_iteration = 1
    middleware = BudgetMiddleware(budget=budget, control=ControlState())

    async def handler(_):
        raise AssertionError("An exhausted run must not expand the schema")

    request = SimpleNamespace(
        tool_call={
            "id": "extend",
            "name": "add_columns",
            "args": {
                "table_id": "programmes",
                "columns_json": '[{"name":"Duration"}]',
            },
        }
    )
    await middleware.awrap_tool_call(request, handler)
    assert middleware.control.stopped
    assert workspace.load_state().coverage_map.tables["programmes"].attributes == [
        "Name",
        "Credits",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("restriction", ["none", "fixed_schema", "targeted_repair"])
async def test_session_schema_locks_hide_add_columns(workspace, tmp_path, monkeypatch, restriction):
    from searchos.agents import runtime
    from searchos.config import models
    from searchos.config.settings import settings
    from searchos.harness.session import SearchSession
    from searchos.skills.catalog.registry import SkillRegistry

    monkeypatch.setattr(models, "get_model_for", lambda role: object())
    monkeypatch.setattr(settings, "enable_skills", False)
    monkeypatch.setattr(settings, "enable_explore", False)

    class GraphCaptured(Exception):
        pass

    def capture(**kwargs):
        names = {tool.name for tool in kwargs["tools"]}
        assert ("add_columns" in names) == (restriction == "none")
        assert ("create_schema" in names) == (restriction == "none")
        raise GraphCaptured

    monkeypatch.setattr(runtime, "create_search_agent_graph", capture)
    session = SearchSession(workspace_root=str(tmp_path / "runs"), skill_registry=SkillRegistry())
    options = (
        {"fixed_schema": True}
        if restriction == "fixed_schema"
        else {"targeted_repair_cells": ["programmes/Alpha.Credits"]}
        if restriction == "targeted_repair"
        else {}
    )
    with pytest.raises(GraphCaptured):
        await session.run(
            "Extend comparison",
            initial_state=workspace.load_state(),
            session_id="tool-scope",
            **options,
        )
