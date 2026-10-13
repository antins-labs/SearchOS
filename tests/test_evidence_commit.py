"""行生命周期与证据挂载的回归契约。"""

import json
from types import SimpleNamespace

import pytest

from searchos.harness.middleware.extraction import ExtractionCoordinator
from searchos.harness.middleware.extraction.core.commit import ingest_rows
from searchos.socm import ColumnCheck, ColumnDesc, EvidenceStatus, SearchState
from searchos.socm.workspace import WorkspaceManager
from searchos.tools import schema as schema_tools


def make_state():
    state = SearchState()
    state.coverage_map.initialize(
        entities=["Acme", "Acme Labs"],
        attributes=["Name", "Value"],
        primary_key=["Name"],
        table_id="items",
    )
    return state


def ingest(state, entity="Acme", value="100"):
    return ingest_rows(
        [
            (
                {"Name": entity, "Value": value},
                f"{entity} value {value}",
                "https://example.com",
                "discover",
            )
        ],
        "items",
        state,
    )


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    workspace = WorkspaceManager(tmp_path, "evidence-commit")
    workspace.create()
    workspace.atomic_update_state(lambda _: make_state())
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


async def add(entity="Acme", value="Alpha"):
    return await schema_tools.add_entities.ainvoke(
        {
            "table_id": "items",
            "entities_json": json.dumps([entity]),
            "attributes_json": json.dumps({entity: {"Value": value}}),
        }
    )


def test_discover_cannot_attach_excluded_row_to_similar_entity():
    state = make_state()
    state.coverage_map.remove_entity("Acme", table_id="items", reason="out of scope")
    nodes, rejected = ingest(state)
    assert nodes == []
    assert rejected and rejected[0]["reason"] == "excluded_entity"
    assert state.evidence_graph.nodes == []
    assert state.coverage_map.cells["items/Acme Labs.Value"].supporting_evidence_ids == []


@pytest.mark.asyncio
async def test_duplicate_assertion_reuses_persisted_evidence(workspace):
    await add(value="Alpha")
    await add(value="alpha")
    state = workspace.load_state()
    ids = {node.id for node in state.evidence_graph.nodes}
    cell = state.coverage_map.cells["items/Acme.Value"]
    assert len(ids) == 1
    assert set(cell.supporting_evidence_ids) == ids


@pytest.mark.asyncio
async def test_add_remove_restore_share_normalized_identity(workspace):
    await add("ACME")
    assert workspace.load_state().coverage_map.tables["items"].entities == ["Acme", "Acme Labs"]
    await schema_tools.remove_entities.ainvoke(
        {
            "table_id": "items",
            "entities_json": '["acme"]',
            "reason": "excluded",
        }
    )
    result = await add("ACME")
    state = workspace.load_state()
    assert "Revived 1" in result
    assert set(state.coverage_map.tables["items"].entities) == {"Acme", "Acme Labs"}
    assert state.coverage_map.cells["items/Acme.Value"].supporting_evidence_ids


@pytest.mark.asyncio
async def test_assertions_obey_column_checks(workspace):
    def constrain(state):
        state.coverage_map.tables["items"].column_desc["Value"] = ColumnDesc(
            type="int",
            check=ColumnCheck(min=0),
        )
        return state

    workspace.atomic_update_state(constrain)
    result = await add(value="-10")
    state = workspace.load_state()
    assert "reject" in result.lower()
    assert state.evidence_graph.nodes == []
    assert not state.coverage_map.cells["items/Acme.Value"].supporting_evidence_ids
    assert ingest(state, value="-10")[0] == []


@pytest.mark.asyncio
async def test_ordinary_assertion_does_not_reactivate_rejected_evidence(workspace):
    await add()
    await schema_tools.edit_entities.ainvoke(
        {
            "table_id": "items",
            "edits_json": '[{"entity":"Acme","set":{"Value":null}}]',
        }
    )
    await add()
    state = workspace.load_state()
    assert state.evidence_graph.nodes[0].status == EvidenceStatus.REJECTED
    assert state.coverage_map.cells["items/Acme.Value"].status.value == "missing"


def test_renamed_alias_stays_excluded():
    state = make_state()
    state.coverage_map.edit_entity("Acme", "Acme Corp", table_id="items")
    state.coverage_map.remove_entity("Acme Corp", table_id="items", reason="excluded")
    assert ingest(state, entity="Acme")[0] == []
    assert "Acme" not in state.coverage_map.tables["items"].entities


def test_rename_rejects_normalized_collision_and_keeps_aliases_acyclic():
    cmap = make_state().coverage_map
    assert cmap.edit_entity("Acme", "ACME LABS", table_id="items")[0] is False
    assert cmap.edit_entity("Acme", "Acme Corp", table_id="items")[0] is True
    assert cmap.edit_entity("Acme Corp", "Acme", table_id="items")[0] is True
    assert cmap.resolve_entity("Acme Corp", table_id="items") == "Acme"
    assert cmap.resolve_entity("ACME", table_id="items") == "Acme"


@pytest.mark.asyncio
async def test_list_column_checks_validate_typed_values(workspace):
    def constrain(state):
        state.coverage_map.tables["items"].column_desc["Value"] = ColumnDesc(
            type="list[str]",
            check=ColumnCheck(enum=["x", "y"]),
        )
        return state

    workspace.atomic_update_state(constrain)
    await add(value=["x", "y"])
    state = workspace.load_state()
    assert state.coverage_map.cells["items/Acme.Value"].display_hint == "x; y"
    assert len(ingest(state, value=["x", "y"])[0]) == 1
    assert ingest(state, value=["x", "invalid"])[0] == []


@pytest.mark.asyncio
async def test_overwrite_recomputes_winner_and_explicitly_restores_prior_value(workspace):
    def extract(state):
        ingest(state)
        return state

    workspace.atomic_update_state(extract)
    for value in ["200", "300", "200"]:
        result = await schema_tools.edit_entities.ainvoke(
            {
                "table_id": "items",
                "edits_json": json.dumps(
                    [
                        {"entity": "Acme", "set": {"Value": value}},
                    ]
                ),
            }
        )
        assert "Set 1" in result
        state = workspace.load_state()
        cell = state.coverage_map.cells["items/Acme.Value"]
        assert cell.display_hint == value
        assert cell.has_conflict is False
        assert len(cell.supporting_evidence_ids) == 1
        winner = state.evidence_graph.get_node(cell.primary_evidence_id)
        assert winner.value == value and winner.status == EvidenceStatus.ACTIVE


def test_commit_reports_distinct_node_link_and_cell_counts():
    from searchos.socm import EvidenceNode
    from searchos.socm.coverage import commit_evidence

    state = make_state()
    nodes = [
        EvidenceNode(
            id=f"n{i}",
            entity="Acme",
            attribute="Value",
            table_id="items",
            source=f"https://source{i}.example",
            value="100",
        )
        for i in range(2)
    ]
    first = commit_evidence(state, nodes)
    assert (len(first.added_nodes), first.associations_added, first.cells_filled) == (2, 2, 1)
    second = commit_evidence(state, nodes)
    assert (len(second.added_nodes), second.associations_added, second.cells_filled) == (0, 0, 0)


def test_projection_keeps_dotted_entity_and_column_names():
    from searchos.socm import EvidenceNode
    from searchos.socm.coverage import audit_evidence_links, commit_evidence

    state = SearchState()
    state.coverage_map.initialize(entities=["Acme Inc."], attributes=["Revenue.2025"], table_id="t")
    result = commit_evidence(
        state,
        [
            EvidenceNode(
                id="dotted",
                table_id="t",
                entity="Acme Inc.",
                attribute="Revenue.2025",
                value="100",
            )
        ],
    )
    assert result.cells_filled == 1
    assert state.coverage_map.cells["t/Acme Inc..Revenue.2025"].primary_evidence_id == "dotted"
    assert audit_evidence_links(state) == []


def test_historical_link_audit_is_read_only():
    from searchos.socm.coverage import audit_evidence_links

    state = make_state()
    nodes, _ = ingest(state)
    state.coverage_map.cells["items/Acme.Value"].supporting_evidence_ids = ["missing-id"]
    state.coverage_map.cells["items/Acme Labs.Value"].supporting_evidence_ids = [nodes[0].id]
    before = state.model_dump()
    issues = audit_evidence_links(state)
    assert {issue["reason"] for issue in issues} == {
        "dangling_id",
        "invalid_binding",
        "unattached_evidence",
    }
    assert state.model_dump() == before


@pytest.mark.asyncio
async def test_manual_rows_obey_primary_key_constraints(workspace):
    def constrain(state):
        state.coverage_map.tables["items"].column_desc["Name"] = ColumnDesc(
            check=ColumnCheck(enum=["Acme", "Acme Labs"]),
        )
        return state

    workspace.atomic_update_state(constrain)
    result = await add("Other")
    state = workspace.load_state()
    assert "Rejected 1" in result
    assert "Other" not in state.coverage_map.tables["items"].entities
    assert ingest(state, entity="Other")[0] == []


@pytest.mark.asyncio
async def test_restore_keeps_original_links_without_historical_backfill(workspace):
    from searchos.socm import EvidenceNode

    await add()
    original = workspace.load_state().coverage_map.cells["items/Acme.Value"].supporting_evidence_ids
    await schema_tools.remove_entities.ainvoke(
        {
            "table_id": "items",
            "entities_json": '["Acme"]',
            "reason": "excluded",
        }
    )

    def legacy(state):
        state.evidence_graph.add_node(
            EvidenceNode(
                id="legacy-orphan",
                table_id="items",
                entity="Acme",
                attribute="Value",
                value="old",
            )
        )
        return state

    workspace.atomic_update_state(legacy)
    await schema_tools.add_entities.ainvoke({"table_id": "items", "entities_json": '["ACME"]'})
    cell = workspace.load_state().coverage_map.cells["items/Acme.Value"]
    assert cell.supporting_evidence_ids == original


@pytest.mark.asyncio
async def test_pending_replay_reports_actual_commits_without_cross_table_copy(
    workspace, monkeypatch
):
    from searchos.harness.middleware.extraction.core.models import ExtractionReport
    from searchos.harness.middleware.extraction.core.replay import replay_pending_summaries
    from searchos.socm import EvidenceNode
    from searchos.socm.coverage import commit_evidence

    def prepare(state):
        state.coverage_map.add_table(
            "other", ["Name", "Value"], primary_key=["Name"], entities=["Acme"]
        )
        state.pending_agent_summaries.append(
            {"source_url": "agent://explore/final_summary", "content": "Acme: Alpha"}
        )
        return state

    workspace.atomic_update_state(prepare)

    async def extract(coordinator, items, tid):
        if tid == "other":
            return ExtractionReport(table_id=tid)
        stats = None

        def apply(state):
            nonlocal stats
            stats = commit_evidence(
                state,
                [
                    EvidenceNode(
                        id="replayed",
                        table_id=tid,
                        entity="Acme",
                        attribute="Value",
                        value="Alpha",
                    )
                ],
            )
            return state

        coordinator._store.atomic_update_state(apply)
        return ExtractionReport(
            table_id=tid,
            committed_nodes=len(stats.added_nodes),
            evidence_links_added=stats.associations_added,
            cells_filled=stats.cells_filled,
        )

    monkeypatch.setattr(ExtractionCoordinator, "_extract_and_ingest_table", extract)
    events = []
    count = await replay_pending_summaries(
        workspace,
        object(),
        ["items", "other"],
        trajectory_logger=SimpleNamespace(_append_raw=events.append),
    )
    assert count == 1
    assert events[-1]["cells_filled"] == 1
    assert events[-1]["evidence_links_added"] == 1
    assert events[-1]["evidence_nodes_added"] == 1
    assert (
        workspace.load_state().coverage_map.cells["other/Acme.Value"].supporting_evidence_ids == []
    )
