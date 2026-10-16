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
        "edits_json": json.dumps([{
            "entity": "alpha", "set": {"value": "new"},
            "source": "https://example.org/update", "source_excerpt": "alpha value is new",
        }]),
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


@pytest.mark.asyncio
@pytest.mark.parametrize("provenance", [
    {},
    {"source": "https://example.org/medalists"},
    {"source_excerpt": "Vladimir Voevodsky | Institute for Advanced Study, US"},
    {"source": "agent://orchestrator/edit", "source_excerpt": "translated"},
])
async def test_translate_after_rename_requires_original_source(workspace, provenance):
    """复现真实 case：先重命名，再翻译值，不能替换为无源 edit 节点。"""
    from searchos.socm import EvidenceNode
    from searchos.socm.coverage import commit_evidence

    await _create_table(workspace)
    await schema_tools.add_entities.ainvoke({
        "entities_json": '["Vladimir Voevodsky"]', "table_id": "items",
    })
    source = "https://example.org/medalists"
    excerpt = "Vladimir Voevodsky | Institute for Advanced Study, US"

    def seed(state):
        commit_evidence(state, [EvidenceNode(
            id="original", finding=excerpt, value="Institute for Advanced Study",
            entity="Vladimir Voevodsky", attribute="value", table_id="items",
            source=source, source_excerpt=excerpt, confidence=0.9, alignment="full",
        )])
        return state

    workspace.atomic_update_state(seed)
    entity = "弗拉基米尔·沃沃斯基(Vladimir Voevodsky)"
    await schema_tools.edit_entities.ainvoke({
        "table_id": "items",
        "edits_json": json.dumps([{"entity": "Vladimir Voevodsky", "rename": entity}]),
    })
    edit = {"entity": entity, "set": {"value": "高等研究院（美国）"}}
    rejected = await schema_tools.edit_entities.ainvoke({
        "table_id": "items", "edits_json": json.dumps([{**edit, **provenance}]),
    })
    assert "Errors:" in rejected
    state = workspace.load_state()
    cell = state.coverage_map.cells[f"items/{entity}.value"]
    assert cell.primary_evidence_id == "original"
    assert cell.display_hint == "Institute for Advanced Study"
    assert state.evidence_graph.get_node("original").status == EvidenceStatus.ACTIVE
    assert len(state.evidence_graph.nodes) == 1

    accepted = await schema_tools.edit_entities.ainvoke({
        "table_id": "items",
        "edits_json": json.dumps([{**edit, "source": source, "source_excerpt": excerpt}]),
    })
    assert "Set 1 cell value(s)" in accepted
    state = workspace.load_state()
    cell = state.coverage_map.cells[f"items/{entity}.value"]
    current = state.evidence_graph.get_node(cell.primary_evidence_id)
    assert cell.display_hint == "高等研究院（美国）"
    assert current.source == source
    assert current.source_excerpt == excerpt
    assert state.evidence_graph.get_node("original").status == EvidenceStatus.SUPERSEDED
