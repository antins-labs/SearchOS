from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from searchos.socm.workspace import WorkspaceManager
from searchos.tools import schema as schema_tools


@pytest.fixture()
def workspace(tmp_path, monkeypatch) -> WorkspaceManager:
    workspace = WorkspaceManager(tmp_path, "add-entities-row-objects")
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


async def _create_ranking_table() -> None:
    result = await schema_tools.create_schema.ainvoke({
        "tables_json": json.dumps([{
            "table_id": "influencers",
            "attributes": ["Ranking", "Name", "TikTok_Username", "Birth"],
            "primary_key": ["Ranking"],
        }]),
    })
    assert result.startswith("Schema created")


async def _create_composite_table() -> None:
    result = await schema_tools.create_schema.ainvoke({
        "tables_json": json.dumps([{
            "table_id": "items",
            "attributes": ["category", "name", "value"],
            "primary_key": ["category", "name"],
        }]),
    })
    assert result.startswith("Schema created")


@pytest.mark.asyncio
async def test_add_entities_accepts_row_objects_without_stringifying_dicts(workspace):
    await _create_ranking_table()

    result = await schema_tools.add_entities.ainvoke({
        "entities_json": json.dumps([
            {
                "Ranking": 1,
                "Name": "IShowSpeed",
                "TikTok_Username": "speed",
                "Birth": "",
            }
        ]),
        "table_id": "influencers",
    })

    state = workspace.load_state()
    table = state.coverage_map.tables["influencers"]
    assert "Added 1" in result
    assert "Asserted 2 cell value(s)" in result
    assert table.entities == ["1"]
    assert not any("IShowSpeed" in entity for entity in table.entities)
    assert state.coverage_map.cells["influencers/1.Ranking"].display_hint == "1"
    assert state.coverage_map.cells["influencers/1.Name"].display_hint == "IShowSpeed"
    assert state.coverage_map.cells["influencers/1.TikTok_Username"].display_hint == "speed"


@pytest.mark.asyncio
async def test_create_schema_accepts_seed_row_objects_like_extraction_rows(workspace):
    result = await schema_tools.create_schema.ainvoke({
        "tables_json": json.dumps([{
            "table_id": "influencers",
            "attributes": ["Ranking", "Name", "TikTok_Username"],
            "primary_key": ["Ranking"],
            "seed_entities": [
                {
                    "Ranking": 1,
                    "Name": "IShowSpeed",
                    "TikTok_Username": "speed",
                }
            ],
        }]),
    })

    state = workspace.load_state()
    table = state.coverage_map.tables["influencers"]
    assert result.startswith("Schema created")
    assert table.entities == ["1"]
    assert state.coverage_map.cells["influencers/1.Ranking"].display_hint == "1"
    assert state.coverage_map.cells["influencers/1.Name"].display_hint == "IShowSpeed"
    assert state.coverage_map.cells["influencers/1.TikTok_Username"].display_hint == "speed"


@pytest.mark.asyncio
async def test_add_entities_rejects_row_object_missing_primary_key(workspace):
    await _create_ranking_table()

    result = await schema_tools.add_entities.ainvoke({
        "entities_json": json.dumps([{"Name": "IShowSpeed"}]),
        "table_id": "influencers",
    })

    state = workspace.load_state()
    assert result.startswith("Error:")
    assert "missing primary key" in result
    assert state.coverage_map.tables["influencers"].entities == []


@pytest.mark.asyncio
async def test_add_entities_rejects_wrong_composite_key_arity(workspace):
    await _create_composite_table()

    result = await schema_tools.add_entities.ainvoke({
        "entities_json": json.dumps([["visa"]]),
        "table_id": "items",
    })

    state = workspace.load_state()
    assert result.startswith("Error:")
    assert "primary_key has 2 column" in result
    assert state.coverage_map.tables["items"].entities == []
