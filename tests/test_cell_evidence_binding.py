"""共享事实的单元格投影与任务用途各自独立。"""

import json
from types import SimpleNamespace

import pytest

from searchos.harness.middleware.extraction.core.commit import ingest_facts
from searchos.socm import (
    CellEvidenceBinding,
    ColumnCheck,
    ColumnDesc,
    EvidenceNode,
    EvidenceStatus,
    FrontierTask,
    SearchState,
)
from searchos.socm.coverage import (
    answer_evidence,
    audit_evidence_links,
    bind_cell_evidence,
    clear_cell_evidence,
    commit_evidence,
    refresh_cells,
)
from searchos.socm.evidence import bind_task_evidence
from searchos.socm.workspace import WorkspaceManager


def make_state():
    state = SearchState(
        intent="Compare population",
        research_mode="findings",
        source_scope={"mode": "hybrid", "documents": []},
    )
    for tid in ["a", "b"]:
        state.coverage_map.add_table(
            tid, ["Name", "Residents"], primary_key=["Name"], entities=["Alpha"]
        )
    state.coverage_map.tables["b"].column_desc["Residents"] = ColumnDesc(
        desc="Thousands of residents"
    )
    state.frontier.add(FrontierTask(id="compare", question="Compare population"))
    state.evidence_graph.add_node(
        EvidenceNode(
            id="fact",
            finding="Alpha has 120000 residents.",
            source_excerpt="Alpha has 120000 residents.",
            source="https://example.org/alpha",
        )
    )
    bind_task_evidence(state, "compare", ["fact"])
    return state


def binding(eid="fact", value="120000"):
    return CellEvidenceBinding(evidence_id=eid, value=value)


def test_web_commit_rejects_out_of_scope_local_evidence():
    state = make_state()
    state.source_scope = {"mode": "web", "documents": []}
    state.evidence_graph.nodes.clear()
    state.evidence_graph.invalidate_index()
    state.evidence_graph.task_bindings.clear()

    result = commit_evidence(
        state,
        [
            EvidenceNode(
                id="local-fact",
                finding="Alpha has 120000 residents.",
                value="120000",
                source="local://library/document/page/1",
                local_source_metadata={"document_id": "document"},
                entity="Alpha",
                attribute="Residents",
                table_id="a",
            )
        ],
    )

    assert result.nodes == []
    assert result.rejected == [
        {"row": "Alpha", "column": "Residents", "reason": "source_out_of_scope"}
    ]
    assert state.evidence_graph.nodes == []


def test_one_fact_can_have_distinct_cell_values_without_copying_source():
    state = make_state()
    original = state.evidence_graph.model_dump_json()
    assert (
        bind_cell_evidence(
            state, [("a/Alpha.Residents", binding()), ("b/Alpha.Residents", binding(value="120"))]
        )
        == 2
    )
    assert state.evidence_graph.model_dump_json() == original
    assert state.coverage_map.cells["a/Alpha.Residents"].value == "120000"
    assert state.coverage_map.cells["b/Alpha.Residents"].value == "120"
    assert not audit_evidence_links(state)
    assert (
        SearchState.model_validate_json(state.model_dump_json()).model_dump() == state.model_dump()
    )
    assert bind_cell_evidence(state, [("a/Alpha.Residents", binding())]) == 0


def test_clear_overwrite_and_exclusion_do_not_retract_other_uses():
    state = make_state()
    bind_cell_evidence(
        state, [("a/Alpha.Residents", binding()), ("b/Alpha.Residents", binding(value="120"))]
    )
    clear_cell_evidence(state, "a", "Alpha", "Residents")
    assert state.evidence_graph.get_node("fact").status == EvidenceStatus.ACTIVE
    assert state.coverage_map.cells["b/Alpha.Residents"].value == "120"
    assert (
        state.coverage_map.evidence_bindings["a/Alpha.Residents"][0].status
        == EvidenceStatus.REJECTED
    )
    with pytest.raises(ValueError, match="overwrite"):
        bind_cell_evidence(state, [("a/Alpha.Residents", binding())])
    bind_cell_evidence(state, [("a/Alpha.Residents", binding())], overwrite=True)
    state.coverage_map.remove_entity("Alpha", table_id="a")
    assert state.coverage_map.cells["b/Alpha.Residents"].supporting_evidence_ids == ["fact"]
    assert [node.id for node in answer_evidence(state)] == ["fact"]
    assert state.evidence_graph.task_bindings[0].evidence_id == "fact"


def test_legacy_cell_is_promoted_before_fact_is_shared():
    state = make_state()
    state.evidence_graph.nodes.clear()
    state.evidence_graph.invalidate_index()
    commit_evidence(
        state,
        [
            EvidenceNode(
                id="fact",
                finding="Alpha has 120000 residents.",
                value="120000",
                source="https://example.org/alpha",
                entity="Alpha",
                attribute="Residents",
                table_id="a",
                alignment="full",
            )
        ],
    )
    bind_cell_evidence(state, [("b/Alpha.Residents", binding(value="120"))])
    clear_cell_evidence(state, "a", "Alpha", "Residents")
    assert state.evidence_graph.get_node("fact").status == EvidenceStatus.ACTIVE
    assert state.coverage_map.cells["b/Alpha.Residents"].value == "120"
    state.coverage_map.remove_entity("Alpha", table_id="a")
    assert [node.id for node in answer_evidence(state)] == ["fact"]


def test_legacy_recommit_respects_rejected_cell_binding_and_explicit_restore():
    state = make_state()
    legacy = EvidenceNode(
        id="legacy",
        finding="Alpha has 120000 residents.",
        value="120000",
        source="https://example.org/legacy",
        entity="Alpha",
        attribute="Residents",
        table_id="a",
        alignment="full",
    )
    commit_evidence(state, [legacy])
    bind_cell_evidence(state, [("b/Alpha.Residents", binding("legacy", "120"))])
    clear_cell_evidence(state, "a", "Alpha", "Residents")
    result = commit_evidence(state, [legacy])
    assert not result.nodes and result.rejected[0]["reason"] == "inactive_binding"
    result = commit_evidence(state, [legacy], overwrite=True)
    assert result.nodes
    assert state.coverage_map.cells["a/Alpha.Residents"].value == "120000"
    assert state.coverage_map.cells["b/Alpha.Residents"].value == "120"
    assert state.evidence_graph.get_node("legacy").status == EvidenceStatus.ACTIVE


def test_batch_validation_is_atomic_and_obeys_source_scope():
    state = make_state()
    before = state.model_dump_json()
    for bad in [
        ("absent", binding()),
        ("b/Alpha.Residents", binding("missing")),
        ("b/Alpha.Name", binding()),
        ("b/Alpha.Residents", binding(value="")),
    ]:
        with pytest.raises(ValueError):
            bind_cell_evidence(state, [("a/Alpha.Residents", binding()), bad])
        assert state.model_dump_json() == before
    state.source_scope = {"mode": "local", "documents": []}
    with pytest.raises(ValueError, match="scope"):
        bind_cell_evidence(state, [("a/Alpha.Residents", binding())])


def test_column_checks_apply_to_projection_values():
    state = make_state()
    state.coverage_map.tables["a"].column_desc["Residents"] = ColumnDesc(check=ColumnCheck(min=0))
    with pytest.raises(ValueError):
        bind_cell_evidence(state, [("a/Alpha.Residents", binding(value="-1"))])
    assert not state.coverage_map.evidence_bindings


def test_rename_and_restore_preserve_bindings_and_fact_identity():
    state = make_state()
    bind_cell_evidence(state, [("a/Alpha.Residents", binding())])
    state.coverage_map.edit_entity("Alpha", "Alpha City", table_id="a")
    assert "a/Alpha City.Residents" in state.coverage_map.evidence_bindings
    assert "a/Alpha.Residents" not in state.coverage_map.evidence_bindings
    state.coverage_map.remove_entity("Alpha City", table_id="a")
    state.coverage_map.restore_entity("Alpha City", table_id="a")
    refresh_cells(state, {"a/Alpha City.Residents"})
    assert state.coverage_map.cells["a/Alpha City.Residents"].value == "120000"
    assert state.evidence_graph.get_node("fact").finding == "Alpha has 120000 residents."


def test_report_and_eval_export_use_target_cell_projection():
    from searchos.harness.report import eval_table_export, synthesis

    state = make_state()
    bind_cell_evidence(state, [("b/Alpha.Residents", binding(value="120"))])
    node = state.evidence_graph.get_node("fact")
    for module in [synthesis, eval_table_export]:
        result = module._cell_findings(
            state.coverage_map.cells["b/Alpha.Residents"],
            {node.id: node},
            (state.coverage_map, "b", "Alpha", "Residents"),
        )
        assert len(result) == 1 and result[0].value == "120"
    assert node.value == "" and node.table_id == ""


def test_overwrite_multiple_supporting_bindings_keeps_every_selected_fact():
    state = make_state()
    state.evidence_graph.add_node(
        EvidenceNode(id="second", finding="Confirmed", source="https://example.org/other")
    )
    bind_cell_evidence(
        state,
        [("a/Alpha.Residents", binding()), ("a/Alpha.Residents", binding("second"))],
        overwrite=True,
    )
    assert set(state.coverage_map.cells["a/Alpha.Residents"].supporting_evidence_ids) == {
        "fact",
        "second",
    }


def test_web_conflict_choice_updates_only_the_selected_cell(monkeypatch):
    from pathlib import Path

    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "web"))
    from api.routes.search import ResolveEvidenceRequest, _resolve_evidence_choice

    state = make_state()
    state.evidence_graph.add_node(
        EvidenceNode(
            id="new", finding="Alpha now has 130000 residents.", source="https://example.org/new"
        )
    )
    bind_cell_evidence(
        state,
        [
            ("a/Alpha.Residents", binding()),
            ("a/Alpha.Residents", binding("new", "130000")),
            ("b/Alpha.Residents", binding(value="120")),
        ],
    )
    _, superseded = _resolve_evidence_choice(
        state,
        ResolveEvidenceRequest(
            table_id="a", entity="Alpha", attribute="Residents", evidence_id="new"
        ),
    )
    assert superseded == ["fact"]
    assert state.coverage_map.cells["a/Alpha.Residents"].value == "130000"
    assert state.coverage_map.cells["b/Alpha.Residents"].value == "120"
    assert state.evidence_graph.get_node("fact").status == EvidenceStatus.ACTIVE

    cell = state.coverage_map.cells["a/Alpha.Residents"]
    assert "fact" in cell.conflict_history_evidence_ids
    assert cell.conflict_evidence_ids == []
    assert not cell.has_conflict
    refresh_cells(state, {"a/Alpha.Residents"})
    assert "fact" in state.coverage_map.cells["a/Alpha.Residents"].conflict_history_evidence_ids


@pytest.mark.asyncio
@pytest.mark.parametrize("single_table", [True, False])
async def test_read_evidence_cell_view_has_projection_and_task_fact_is_unchanged(single_table):
    from searchos.harness.middleware.extraction import InMemoryEvidenceStore
    from searchos.tools.search_state import _workspace_var
    from searchos.tools.socm_read import read_evidence

    state = make_state()
    if single_table:
        state.coverage_map.tables.pop("a")
        state.coverage_map.cells = {key: cell for key, cell in state.coverage_map.cells.items() if key.startswith("b/")}
    bind_cell_evidence(state, [("b/Alpha.Residents", binding(value="120"))])
    token = _workspace_var.set(InMemoryEvidenceStore(state))
    try:
        cell = json.loads(await read_evidence.ainvoke({"cell": "b/Alpha.Residents"}))["nodes"][0]
        assert cell["value"] == "120" and cell["table_id"] == "b"
        fact = json.loads(await read_evidence.ainvoke({"task_id": "compare"}))["nodes"][0]
        assert fact["value"] == "" and fact["table_id"] == ""
        assert fact["cell_bindings"][0]["cell"] == "b/Alpha.Residents"
    finally:
        _workspace_var.reset(token)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "outcome",
    [
        "supported",
        "unsupported",
        "bad_quote",
        "scope_changed",
        "fact_changed",
        "schema_changed",
        "task_removed",
        "malformed",
        "missing",
        "timeout",
    ],
)
async def test_projection_tool_reviews_then_commits_fact_and_task_uses(
    tmp_path, monkeypatch, outcome
):
    from searchos.tools import schema

    workspace = WorkspaceManager(tmp_path, "projection")
    workspace.create()
    workspace.save_state(make_state())
    calls = []

    class Judge:
        async def ainvoke(self, prompt):
            calls.append(prompt)
            if outcome == "timeout":
                import asyncio

                await asyncio.Future()
            if outcome in {"scope_changed", "fact_changed", "schema_changed", "task_removed"}:

                def change(state):
                    if outcome == "scope_changed":
                        state.source_scope = {"mode": "local", "documents": []}
                    elif outcome == "fact_changed":
                        state.evidence_graph.get_node("fact").finding = "Different fact"
                    elif outcome == "schema_changed":
                        state.coverage_map.tables["a"].column_desc["Residents"] = ColumnDesc(
                            desc="Another metric"
                        )
                    else:
                        state.frontier.questions.clear()
                    return state

                workspace.atomic_update_state(change)
            if outcome in {"malformed", "missing"}:
                return SimpleNamespace(content="not json" if outcome == "malformed" else "[]")
            return SimpleNamespace(
                content=json.dumps(
                    [
                        {
                            "id": "0",
                            "supported": outcome != "unsupported",
                            "quote": "Invented quote"
                            if outcome == "bad_quote"
                            else "Alpha has 120000 residents.",
                        }
                    ]
                )
            )

    monkeypatch.setattr(
        schema, "_orch_ctx", lambda: SimpleNamespace(workspace=workspace, judge_model=Judge())
    )
    if outcome == "timeout":
        from searchos.config.settings import settings

        monkeypatch.setattr(settings, "hybrid_projection_timeout_s", 0.01)
    result = await schema.project_evidence.ainvoke(
        {
            "task_id": "compare",
            "bindings_json": json.dumps(
                [
                    {"cell": "a/Alpha.Residents", "evidence_id": "fact", "value": "120000"},
                ]
            ),
        }
    )
    assert len(calls) == 1
    state = workspace.load_state()
    assert len(state.evidence_graph.nodes) == 1
    if outcome == "supported":
        assert json.loads(result)["bindings_added"] == 1
        assert state.coverage_map.cells["a/Alpha.Residents"].value == "120000"
    else:
        assert result.startswith("Error:") and not state.coverage_map.evidence_bindings


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid", ["source", "excerpt", "budget", "cancelled"])
async def test_projection_preflight_and_cancellation_never_write(tmp_path, monkeypatch, invalid):
    import asyncio

    from searchos.config.settings import settings
    from searchos.tools import schema

    workspace = WorkspaceManager(tmp_path, "preflight")
    workspace.create()
    state = make_state()
    if invalid == "source":
        state.evidence_graph.get_node("fact").source = "agent://summary"
    elif invalid == "excerpt":
        state.evidence_graph.get_node("fact").source_excerpt = ""
    elif invalid == "budget":
        monkeypatch.setattr(settings, "hybrid_projection_max_chars", 1)
    workspace.save_state(state)
    before = workspace.load_state().model_dump_json()
    calls = []

    class Judge:
        async def ainvoke(self, prompt):
            calls.append(prompt)
            raise asyncio.CancelledError()

    monkeypatch.setattr(
        schema, "_orch_ctx", lambda: SimpleNamespace(workspace=workspace, judge_model=Judge())
    )
    args = {
        "task_id": "compare",
        "bindings_json": json.dumps(
            [{"cell": "a/Alpha.Residents", "evidence_id": "fact", "value": "120000"}]
        ),
    }
    if invalid == "cancelled":
        with pytest.raises(asyncio.CancelledError):
            await schema.project_evidence.ainvoke(args)
        assert len(calls) == 1
    else:
        assert (await schema.project_evidence.ainvoke(args)).startswith("Error:")
        assert not calls
    assert workspace.load_state().model_dump_json() == before


@pytest.mark.parametrize("source_mode", ["web", "hybrid"])
def test_table_fact_commit_shares_fact_and_retains_original_window(source_mode):
    state = make_state()
    state.source_scope["mode"] = source_mode
    state.evidence_graph.nodes.clear()
    state.evidence_graph.invalidate_index()
    state.evidence_graph.task_bindings.clear()
    state.coverage_map.tables["b"].column_desc.clear()
    original = (
        "[Now viewing]\nL0: Official population statistics\nL1: Alpha has 120000 residents.\n"
    )
    cleaned = "Official population statistics\nAlpha has 120000 residents."
    row = {"Name": "Alpha", "Residents": "120000", "_source_excerpt": "Alpha has 120000 residents."}
    bundle = (row, cleaned, "https://example.org/alpha", None, "fill", original)
    first, rejected = ingest_facts([bundle], "a", state)
    assert len(first) == 1 and not rejected
    stats = {}
    second, rejected = ingest_facts([bundle], "b", state, commit_stats=stats)
    assert second == [] and not rejected and stats["accepted_ids"] == [first[0].id]
    assert stats["cells_filled"] == 1 and stats["evidence_links_added"] == 1
    assert len(state.evidence_graph.nodes) == len(state.evidence_graph.observations) == 1
    fact = state.evidence_graph.nodes[0]
    assert fact.table_id == fact.entity == fact.attribute == fact.value == ""
    observed = state.evidence_graph.observations[0]
    assert observed.text == original and observed.id == fact.observation_id
    assert original[slice(*fact.span)] == fact.source_excerpt
    bind_task_evidence(state, "compare", [fact.id])
    clear_cell_evidence(state, "a", "Alpha", "Residents")
    assert state.coverage_map.cells["b/Alpha.Residents"].value == "120000"
    assert fact.status == EvidenceStatus.ACTIVE and not audit_evidence_links(state)


def test_hybrid_table_extraction_rejects_unanchored_or_out_of_scope_sources():

    state = make_state()
    state.evidence_graph.nodes.clear()
    state.evidence_graph.invalidate_index()
    row = {"Name": "Invented", "Residents": "120000"}
    before = state.model_dump_json()
    nodes, rejected = ingest_facts(
        [(row, "Invented has 120000 residents.", "local://unknown@v1/p1")], "a", state
    )
    assert not nodes and rejected and state.model_dump_json() == before
    nodes, rejected = ingest_facts(
        [
            (
                {"Name": "Alpha", "Residents": "unknown"},
                "Nothing about the requested topic.",
                "https://example.org",
            )
        ],
        "a",
        state,
    )
    assert not nodes and rejected[0]["reason"] == "unanchored_source"
    assert not state.evidence_graph.nodes and not state.evidence_graph.observations


def test_hybrid_table_extraction_preserves_typed_list_validation():

    state = make_state()
    state.coverage_map.tables["a"].column_desc["Residents"] = ColumnDesc(
        type="list[str]", check=ColumnCheck(enum=["x", "y"])
    )
    nodes, rejected = ingest_facts(
        [
            (
                {
                    "Name": "Alpha",
                    "Residents": ["x", "y"],
                    "_source_excerpt": "Alpha groups are x and y.",
                },
                "Alpha groups are x and y.",
                "https://example.org/groups",
            )
        ],
        "a",
        state,
    )
    assert len(nodes) == 1 and not rejected
    assert state.coverage_map.cells["a/Alpha.Residents"].supporting_evidence_ids == [nodes[0].id]


def test_agent_report_attributes_projected_cells_even_when_fact_is_reused(monkeypatch):
    import time

    from searchos.agents.orchestrator import lifecycle
    from searchos.harness.middleware.extraction import InMemoryEvidenceStore

    state = make_state()
    before = {"filled_keys": set(state.coverage_map.cells), "evidence_ids": {"fact"}}
    before["filled_keys"].difference_update({"a/Alpha.Residents", "b/Alpha.Residents"})
    state.evidence_graph.add_node(
        EvidenceNode(id="peer", finding="Peer fact", source="https://example.org/peer")
    )
    bind_cell_evidence(
        state, [("a/Alpha.Residents", binding()), ("b/Alpha.Residents", binding("peer", "130"))]
    )
    monkeypatch.setattr(
        lifecycle,
        "_ctx",
        SimpleNamespace(
            workspace=InMemoryEvidenceStore(state),
            agent_graphs={
                "worker": {
                    "agent_type": "search_agent",
                    "extraction": SimpleNamespace(committed_node_ids={"fact"}),
                }
            },
        ),
    )
    report = lifecycle._compute_agent_report(
        agent_id="worker",
        thread_id="worker",
        pre_snapshot=before,
        started_at=time.time(),
        status="completed",
        result="Read source",
    )
    assert report.cells_filled == ["a/Alpha.Residents"]
    assert report.evidence_nodes_added == 0


def test_primary_key_projection_attaches_support_without_renaming_row():
    state = make_state()
    bind_cell_evidence(state, [("a/Alpha.Name", binding(value="Alpha"))])
    assert state.coverage_map.cells["a/Alpha.Name"].supporting_evidence_ids == ["fact"]
    before = state.model_dump_json()
    with pytest.raises(ValueError, match="identity"):
        bind_cell_evidence(state, [("a/Alpha.Name", binding(value="Beta"))], overwrite=True)
    assert state.model_dump_json() == before


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [120000, 120000.0, True, float("inf")])
async def test_projection_tool_accepts_finite_numbers_only(tmp_path, monkeypatch, value):
    from searchos.tools import schema

    workspace = WorkspaceManager(tmp_path, "numeric-projection")
    workspace.create()
    workspace.save_state(make_state())
    calls = []

    class Judge:
        async def ainvoke(self, prompt):
            calls.append(prompt)
            return SimpleNamespace(
                content='[{"id":"0","supported":true,"quote":"Alpha has 120000 residents."}]'
            )

    monkeypatch.setattr(
        schema, "_orch_ctx", lambda: SimpleNamespace(workspace=workspace, judge_model=Judge())
    )
    result = await schema.project_evidence.ainvoke(
        {
            "task_id": "compare",
            "bindings_json": json.dumps(
                [{"cell": "a/Alpha.Residents", "evidence_id": "fact", "value": value}]
            ),
        }
    )
    if isinstance(value, bool) or value == float("inf"):
        assert result.startswith("Error:") and not calls
        assert not workspace.load_state().coverage_map.evidence_bindings
    else:
        assert json.loads(result)["bindings_added"] == 1 and len(calls) == 1
        assert float(workspace.load_state().coverage_map.cells["a/Alpha.Residents"].value) == 120000


@pytest.mark.asyncio
async def test_hybrid_edit_cannot_manufacture_evidence_or_replace_supported_cell(
    tmp_path, monkeypatch
):
    from searchos.tools import schema

    workspace = WorkspaceManager(tmp_path, "hybrid-edit")
    workspace.create()
    state = make_state()
    bind_cell_evidence(state, [("a/Alpha.Residents", binding())])
    workspace.save_state(state)
    before = workspace.load_state().model_dump_json()
    monkeypatch.setattr(schema, "_orch_ctx", lambda: SimpleNamespace(workspace=workspace))
    result = await schema.edit_entities.ainvoke(
        {
            "table_id": "a",
            "edits_json": json.dumps([{"entity": "Alpha", "set": {"Residents": "7200000"}}]),
        }
    )
    assert "provide original source and source_excerpt" in result
    assert workspace.load_state().model_dump_json() == before


def test_hybrid_partial_answer_excludes_rejected_agent_assertions():
    from searchos.harness.session import _write_findings_answer

    state = make_state()
    state.evidence_graph.add_node(
        EvidenceNode(
            id="manual", finding="Invented hourly quota", source="agent://orchestrator/edit",
            status=EvidenceStatus.REJECTED,
        )
    )
    outputs = {}
    workspace = SimpleNamespace(write_output=lambda name, text: outputs.update({name: text}))
    _write_findings_answer(
        workspace,
        state,
        "Check quota",
        {"messages": []},
    )
    assert outputs["report.md"] == "本次研究尚未生成回答。"
    assert "Invented hourly quota" not in outputs["report.md"]
    assert "agent://" not in outputs["report.md"]
    assert json.loads(outputs["result.json"])["evidence_count"] == 1
    with pytest.raises(ValueError):
        bind_task_evidence(state, "compare", ["manual"])


@pytest.mark.asyncio
async def test_hybrid_schema_seeds_are_structure_and_require_source_support(tmp_path, monkeypatch):
    from searchos.tools import schema

    workspace = WorkspaceManager(tmp_path, "hybrid-seeds")
    workspace.create()
    workspace.save_state(
        SearchState(source_scope={"mode": "hybrid", "documents": []}, research_mode="findings")
    )
    monkeypatch.setattr(
        schema,
        "_orch_ctx",
        lambda: SimpleNamespace(workspace=workspace, extraction_model=None, judge_model=None),
    )
    result = await schema.create_schema.ainvoke(
        {
            "tables_json": json.dumps(
                [
                    {
                        "table_id": "rates",
                        "attributes": ["Version", "Rate"],
                        "primary_key": ["Version"],
                        "seed_entities": [{"Version": "revision 1", "Rate": "120"}],
                    }
                ]
            )
        }
    )
    state = workspace.load_state()
    assert "Schema created" in result
    assert state.coverage_map.tables["rates"].entities == ["revision 1"]
    assert not state.evidence_graph.nodes
    assert state.coverage_map.cells["rates/revision 1.Rate"].status.value == "missing"
    assert not state.coverage_map.cells["rates/revision 1.Version"].supporting_evidence_ids


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "value,calculation,accepted",
    [
        (7200, {"source_value": "120", "expression": "x * 60"}, True),
        (72000, {"source_value": "120", "expression": "x * 60"}, False),
        (72000, None, False),
        (72000, {"source_value": "1200", "expression": "x * 60"}, False),
        (7200, {"source_value": "120", "expression": "7200"}, False),
        (7200, {"source_value": "120", "expression": "__import__('os')"}, False),
        (7200, {"source_value": "120", "expression": "x / 0"}, False),
        (7200, {"source_value": "120", "expression": "x ** 1000"}, False),
    ],
)
async def test_projection_checks_arithmetic_even_when_judge_approves(
    tmp_path, monkeypatch, value, calculation, accepted
):
    from searchos.tools import schema

    workspace = WorkspaceManager(tmp_path, "calculation")
    workspace.create()
    state = make_state()
    fact = state.evidence_graph.get_node("fact")
    fact.finding = fact.source_excerpt = "Alpha permits 120 requests per minute."
    state.coverage_map.tables["a"].column_desc["Residents"] = ColumnDesc(
        desc="Hourly equivalent: per-minute rate times 60, assuming continuous use."
    )
    workspace.save_state(state)
    before = workspace.load_state().model_dump_json()

    class Judge:
        async def ainvoke(self, prompt):
            return SimpleNamespace(
                content=json.dumps(
                    [
                        {
                            "id": "0",
                            "supported": True,
                            "quote": fact.source_excerpt,
                            "calculation": calculation,
                        }
                    ]
                )
            )

    monkeypatch.setattr(
        schema, "_orch_ctx", lambda: SimpleNamespace(workspace=workspace, judge_model=Judge())
    )
    result = await schema.project_evidence.ainvoke(
        {
            "task_id": "compare",
            "bindings_json": json.dumps(
                [
                    {"cell": "a/Alpha.Residents", "evidence_id": "fact", "value": value},
                ]
            ),
        }
    )
    if accepted:
        assert json.loads(result)["bindings_added"] == 1
        assert workspace.load_state().coverage_map.cells["a/Alpha.Residents"].value == "7200"
    else:
        assert result.startswith("Error:")
        assert workspace.load_state().model_dump_json() == before


@pytest.mark.parametrize(
    "value,source,expression,accepted",
    [
        ("0.3", "0.1", "x * 3", True),
        ("120", "120000", "x / 1000", True),
        ("32", "0", "x * 9 / 5 + 32", True),
        ("0.33", "1", "x / 3", False),
        ("1", "1", "x * 1e999999", False),
        ("1", "1", "x + 0" * 40, False),
    ],
)
def test_projection_arithmetic_preserves_decimals_and_bounds(value, source, expression, accepted):
    from searchos.harness.middleware.extraction.utils.unit_normalize import (
        validate_projection_calculation,
    )

    calculation = {"source_value": source, "expression": expression}
    if accepted:
        validate_projection_calculation(value, f"The original value is {source}.", calculation)
    else:
        with pytest.raises(ValueError):
            validate_projection_calculation(value, f"The original value is {source}.", calculation)


def test_non_numeric_projection_keeps_long_source_text():
    from searchos.harness.middleware.extraction.utils.unit_normalize import (
        validate_projection_calculation,
    )

    text = "An explanation of the source conditions. " * 20
    validate_projection_calculation(text, text, None)


@pytest.mark.asyncio
async def test_projection_keeps_supported_cells_when_peer_lacks_support(tmp_path, monkeypatch):
    from searchos.tools import schema
    workspace = WorkspaceManager(tmp_path, "partial-projection")
    workspace.create()
    workspace.save_state(make_state())
    class Judge:
        async def ainvoke(self, prompt):
            return SimpleNamespace(content=json.dumps([
                {"id": "0", "supported": True, "quote": "Alpha has 120000 residents."},
                {"id": "1", "supported": False, "quote": ""},
            ]))
    monkeypatch.setattr(schema, "_orch_ctx", lambda: SimpleNamespace(workspace=workspace, judge_model=Judge()))
    result = await schema.project_evidence.ainvoke({"task_id": "compare", "bindings_json": json.dumps([
        {"cell": "a/Alpha.Residents", "evidence_id": "fact", "value": "120000"},
        {"cell": "b/Alpha.Residents", "evidence_id": "fact", "value": "900"},
    ])})
    payload = json.loads(result)
    assert payload["projected_cells"] == ["a/Alpha.Residents"]
    assert payload["rejected"][0]["cell"] == "b/Alpha.Residents"
    state = workspace.load_state()
    assert state.coverage_map.cells["a/Alpha.Residents"].value == "120000"
    assert not state.coverage_map.cells["b/Alpha.Residents"].value
