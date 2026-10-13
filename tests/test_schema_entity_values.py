from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from searchos.socm import CellStatus, EvidenceStatus
from searchos.socm.workspace import WorkspaceManager
from searchos.tools import schema as schema_tools


async def _create_table(workspace: WorkspaceManager, *, composite: bool = False) -> None:
    primary_key = ["category", "name"] if composite else ["name"]
    attributes = [*primary_key, "value", "note"]
    result = await schema_tools.create_schema.ainvoke({
        "tables_json": json.dumps([{
            "table_id": "items",
            "attributes": attributes,
            "primary_key": primary_key,
        }]),
    })
    assert result.startswith("Schema created")


@pytest.fixture()
def workspace(tmp_path, monkeypatch) -> WorkspaceManager:
    workspace = WorkspaceManager(tmp_path, "schema-values")
    workspace.create()
    monkeypatch.setattr(
        schema_tools,
        "_orch_ctx",
        lambda: SimpleNamespace(
            workspace=workspace,
            extraction_model=None,
            judge_model=None,
        ),
    )
    return workspace


@pytest.mark.asyncio
async def test_add_entities_attributes_fill_non_pk_cells(workspace):
    await _create_table(workspace)

    result = await schema_tools.add_entities.ainvoke({
        "entities_json": '["alpha"]',
        "table_id": "items",
        "attributes_json": '{"alpha":{"value":"42","note":"verified"}}',
    })

    state = workspace.load_state()
    value = state.coverage_map.cells["items/alpha.value"]
    note = state.coverage_map.cells["items/alpha.note"]
    assert "Asserted 2 cell value(s)" in result
    assert value.status == CellStatus.FILLED
    assert value.display_hint == "42"
    assert note.status == CellStatus.FILLED
    assert note.display_hint == "verified"
    assert {node.value for node in state.evidence_graph.nodes} == {"42", "verified"}


@pytest.mark.asyncio
async def test_add_entities_attributes_apply_to_existing_duplicate(workspace):
    await _create_table(workspace)
    await schema_tools.add_entities.ainvoke({
        "entities_json": '["alpha"]',
        "table_id": "items",
    })

    result = await schema_tools.add_entities.ainvoke({
        "entities_json": '["alpha"]',
        "table_id": "items",
        "attributes_json": '{"alpha":{"value":"42"}}',
    })

    cell = workspace.load_state().coverage_map.cells["items/alpha.value"]
    assert "skipped 1 duplicates" in result
    assert cell.status == CellStatus.FILLED
    assert cell.display_hint == "42"


@pytest.mark.asyncio
async def test_add_entities_resolves_composite_attribute_key(workspace):
    await _create_table(workspace, composite=True)

    result = await schema_tools.add_entities.ainvoke({
        "entities_json": '[["visa","student"]]',
        "table_id": "items",
        "attributes_json": '{"visa,student":{"value":"required"}}',
    })

    cell = workspace.load_state().coverage_map.cells["items/visa|student.value"]
    assert "Asserted 1 cell value(s)" in result
    assert cell.status == CellStatus.FILLED
    assert cell.display_hint == "required"


@pytest.mark.asyncio
async def test_edit_entities_overwrites_and_clears_through_shared_path(workspace):
    await _create_table(workspace)
    await schema_tools.add_entities.ainvoke({
        "entities_json": '["alpha"]',
        "table_id": "items",
        "attributes_json": '{"alpha":{"value":"old"}}',
    })

    result = await schema_tools.edit_entities.ainvoke({
        "table_id": "items",
        "edits_json": '[{"entity":"alpha","set":{"value":"new"}}]',
    })
    state = workspace.load_state()
    cell = state.coverage_map.cells["items/alpha.value"]
    assert "Set 1 cell value(s)" in result
    assert cell.status == CellStatus.FILLED
    assert cell.display_hint == "new"
    assert any(node.value == "old" and node.status == EvidenceStatus.SUPERSEDED
               for node in state.evidence_graph.nodes)

    result = await schema_tools.edit_entities.ainvoke({
        "table_id": "items",
        "edits_json": '[{"entity":"alpha","set":{"value":null}}]',
    })
    state = workspace.load_state()
    cell = state.coverage_map.cells["items/alpha.value"]
    assert "Cleared 1 cell(s)" in result
    assert cell.status == CellStatus.MISSING
    assert cell.display_hint == ""
    assert any(node.value == "new" and node.status == EvidenceStatus.REJECTED
               for node in state.evidence_graph.nodes)
