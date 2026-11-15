"""逐实体目标投影、角色指引与完整缺口。"""

from dataclasses import dataclass
from types import SimpleNamespace

import pytest
from langchain.agents.middleware.types import ModelResponse
from langchain_core.messages import AIMessage, HumanMessage

from searchos.agents.orchestrator.lifecycle import _build_sub_agent_context
from searchos.harness.middleware.context.socm_middleware import SOCMContextMiddleware
from searchos.harness.middleware.models import TaskContext
from searchos.socm.refs import cell_key, row_key, row_values
from searchos.socm import CellStatus, ColumnDesc, FrontierTask, SearchState
from searchos.socm.views.render import render_orchestrator_view, render_search_agent_view
from searchos.socm.views.snapshot import SearchStateSnapshot


def state_with_rows(rows):
    state = SearchState()
    state.coverage_map.add_table(
        "t", ["Name", "Revenue", "Other"], primary_key=["Name"], entities=[row_key([name]) for name in rows]
    )
    return state


@pytest.mark.asyncio
@pytest.mark.parametrize("view", ["task", "overview", "writing"])
@pytest.mark.parametrize("has_schema", [False, True])
async def test_snapshot_date_requires_research_state(monkeypatch, view, has_schema):
    from datetime import date

    from searchos.harness.middleware.context import socm_middleware

    @dataclass
    class Request:
        messages: list

    state = state_with_rows(["Acme"]) if has_schema else SearchState()
    mw = SOCMContextMiddleware(
        SimpleNamespace(load_state=lambda: state),
        task=TaskContext(),
        view=view,
    )
    captured = []

    async def handler(request):
        captured.append(request.messages[-1].content)
        return ModelResponse(result=[AIMessage(content="Done")])

    # 日期来自运行环境，不采用模型写进任务的错误年份。
    for day in [12, 13]:
        monkeypatch.setattr(
            socm_middleware,
            "date",
            SimpleNamespace(
                today=lambda: date(2026, 10, day),
            ),
        )
        await mw.awrap_model_call(Request([HumanMessage(content="当前是2025年")]), handler)
        if not has_schema:
            assert captured[-1] == "当前是2025年"
            continue
        assert f"Current date (runtime local date): 2026-10-{day}" in captured[-1]
        assert "Current date (runtime local date)" in captured[-1]
        assert "AUTOMATED HARNESS" not in captured[-1]
    assert "2026-10-12" not in captured[-1]


def test_only_assigned_unfinished_columns_and_definitions():
    state = state_with_rows(["Acme", "Unrelated"])
    state.coverage_map.tables["t"].column_desc["Revenue"] = ColumnDesc(
        desc="USD millions, fiscal 2025"
    )
    keys = {cell_key("t", row_key(["Acme"]), "Revenue")}
    view = render_search_agent_view(SearchStateSnapshot.from_state(state), {row_key(["Acme"])}, "t", keys)
    assert '["Acme", null, null]' in view
    assert 'Assigned targets [row index, column indices] (zero-based): [[0, [1]]]' in view
    assert "USD millions, fiscal 2025" in view
    assert 'Columns: ["Name", "Revenue", "Other"]' in view and "Unrelated" not in view
    state.coverage_map.cells[cell_key("t", row_key(["Acme"]), "Revenue")].status = CellStatus.FILLED
    view = render_search_agent_view(SearchStateSnapshot.from_state(state), {row_key(["Acme"])}, "t", keys)
    assert "Assigned cells: 1; filled: 1; actionable gaps: 0; unavailable: 0" in view
    assert "Verify the assigned entity set" not in view
    assert "t/Acme.Revenue:" not in view


def test_conflicts_remain_actionable_and_unavailable_not_filled():
    state = state_with_rows(["Acme"])
    state.coverage_map.cells[cell_key("t", row_key(["Acme"]), "Revenue")].status = CellStatus.FILLED
    state.coverage_map.cells[cell_key("t", row_key(["Acme"]), "Revenue")].has_conflict = True
    state.coverage_map.cells[cell_key("t", row_key(["Acme"]), "Other")].status = CellStatus.HARD_CELL
    view = render_search_agent_view(SearchStateSnapshot.from_state(state), {row_key(["Acme"])}, "t")
    assert '{"value": null, "status": "conflict"}' in view
    assert "verification" not in view.lower()
    assert "filled: 0; actionable gaps: 1; unavailable: 1" in view


def test_exact_keys_preserve_punctuation_and_multiple_tables():
    state = state_with_rows(["Acme.Inc/US"])
    state.coverage_map.add_table("b", ["Name", "Value"], primary_key=["Name"], entities=[row_key(["Beta"])])
    state.frontier.add(
        FrontierTask(
            id="f",
            question="search",
            assigned_agent_id="search_agent_test",
            target_cells=[cell_key("t", row_key(["Acme.Inc/US"]), "Revenue"), cell_key("b", row_key(["Beta"]), "Value")],
        )
    )
    mw = SOCMContextMiddleware(
        SimpleNamespace(load_state=lambda: state), task=TaskContext(agent_id="search_agent_test")
    )
    view = mw.render()
    assert '["Acme.Inc/US", null, null]' in view
    assert '["Beta", null]' in view
    assert 'Columns: ["Name", "Revenue", "Other"]' in view


def test_large_tables_preserve_every_entity_attribute_gap():
    state = state_with_rows([f"Entity{i:04d}" for i in range(1500)])
    keys = {cell_key("t", e, "Revenue") for e in state.coverage_map.tables["t"].entities}
    view = render_search_agent_view(SearchStateSnapshot.from_state(state), set(), "t", keys)
    assert len(view) > 12_000
    assert view.count(', null, null]') == 1500
    for entity in state.coverage_map.tables["t"].entities:
        assert f'["{row_values(entity)[0]}", null, null]' in view
    assert "omitted" not in view and "truncated" not in view
    for i in range(100):
        state.coverage_map.cells[cell_key("t", row_key([f"Entity{i:04d}"]), "Revenue")].status = CellStatus.FILLED
    updated = render_search_agent_view(SearchStateSnapshot.from_state(state), set(), "t", keys)
    assert "Entity0100" in updated and "Entity1499" in updated
    assert '["Entity0000", {"status": "filled"}, null]' in updated
    assert '["Entity0000", null, null]' not in updated
    orch = render_orchestrator_view(SearchStateSnapshot.from_state(state))
    assert "Entity0000" in orch and "Entity1499" not in orch
    assert "Gap rows shown: 30/1500" in orch
    assert '["Entity0000", {"status": "filled"}, null]' in orch
    startup = _build_sub_agent_context(state, agent_type="search_agent")
    assert "Entity0000" not in startup
    assert "orchestrator maps" not in startup


def test_filled_known_rows_keep_counts_without_explanatory_text():
    state = state_with_rows(["Acme"])
    for cell in state.coverage_map.cells.values():
        cell.status = CellStatus.FILLED

    view = render_orchestrator_view(SearchStateSnapshot.from_state(state))

    assert "Known rows: 1, 0 with unresolved columns" in view
    assert "mode=seeded" in view
    assert "Coverage describes" not in view
    assert "add_entities" not in view


def test_snapshot_contains_state_without_procedural_guidance():
    mw = SOCMContextMiddleware(
        SimpleNamespace(load_state=lambda: state_with_rows(["A"])),
        task=TaskContext(),
        view="overview",
    )
    text = mw.render()
    assert "missing" in text
    assert "set_research_plan" not in text
    assert "read_evidence" not in text
    assert "edit_entities" not in text
    assert "Continue" not in text


@pytest.mark.asyncio
async def test_projection_deduplicates_and_tracks_value_conflicts():
    from langchain_core.messages import AIMessage

    @dataclass
    class Request:
        messages: list
        system_message: object = None

    state = state_with_rows(["Acme"])
    state.frontier.add(
        FrontierTask(
            id="f",
            question="Acme revenue",
            table_id="t",
            assigned_agent_id="search_agent_test",
            target_cells=[cell_key("t", row_key(["Acme"]), "Revenue")],
        )
    )
    mw = SOCMContextMiddleware(
        SimpleNamespace(load_state=lambda: state), task=TaskContext(agent_id="search_agent_test")
    )
    views = []

    async def handler(request):
        views.append(request.messages[-1].content)
        return ModelResponse(result=[AIMessage(content="continue")])

    for _ in range(2):
        await mw.awrap_model_call(Request([HumanMessage(content="task")]), handler)
    assert '["Acme", null, null]' in views[0]
    assert views[1] == views[0]
    cell = state.coverage_map.cells[cell_key("t", row_key(["Acme"]), "Revenue")]
    cell.status = CellStatus.FILLED
    await mw.awrap_model_call(Request([HumanMessage(content="task")]), handler)
    assert "Assigned cells: 1; filled: 1; actionable gaps: 0; unavailable: 0" in views[-1]
    assert "Verify the assigned entity set" not in views[-1]
    cell.has_conflict = True
    cell.display_hint = "different source value"
    await mw.awrap_model_call(Request([HumanMessage(content="task")]), handler)
    assert '"status": "conflict"' in views[-1]
    assert "verification" not in views[-1].lower()
    assert "different source value" in views[-1]


def test_each_entity_keeps_status_and_candidate_together():
    state = state_with_rows(["A", "B", "C", "D"])
    state.coverage_map.cells[cell_key("t", row_key(["C"]), "Revenue")].status = CellStatus.UNCERTAIN
    state.coverage_map.cells[cell_key("t", row_key(["C"]), "Revenue")].display_hint = "80"
    state.coverage_map.cells[cell_key("t", row_key(["C"]), "Other")].status = CellStatus.HARD_CELL
    state.coverage_map.cells[cell_key("t", row_key(["D"]), "Revenue")].status = CellStatus.FILLED
    state.coverage_map.cells[cell_key("t", row_key(["D"]), "Revenue")].has_conflict = True
    state.coverage_map.cells[cell_key("t", row_key(["D"]), "Revenue")].display_hint = "100"
    state.coverage_map.cells[cell_key("t", row_key(["D"]), "Other")].status = CellStatus.FILLED
    view = render_search_agent_view(
        SearchStateSnapshot.from_state(state), {row_key([name]) for name in ("A", "B", "C", "D")}, "t"
    )
    assert '["A", null, null]' in view
    assert '["B", null, null]' in view
    assert '["C", {"value": "80", "status": "uncertain"}, {"value": null, "status": "unavailable"}]' in view
    assert (
        '["D", {"value": "100", "status": "conflict"}, {"status": "filled"}]'
        in view
    )
    assert "verification" not in view.lower()
    assert "Attributes:" not in view and "Entities:" not in view and "Candidate for" not in view


def test_fully_recorded_composite_key_targets_show_rows_and_values():
    state = SearchState()
    entities = [row_key(["Engineering", name]) for name in ("University A", "University B", "University C")]
    state.coverage_map.add_table(
        "subject_rankings",
        ["Subject", "University", "Rank", "Score", "Country"],
        primary_key=["Subject", "University"],
        entities=entities,
        table_label="QS Subject Rankings 2025 - Top 5 per Broad Subject",
    )
    keys = set()
    for i, entity in enumerate(entities, 1):
        for attr, value in [("Rank", str(i)), ("Score", str(100 - i)), ("Country", "UK")]:
            key = cell_key("subject_rankings", entity, attr)
            keys.add(key)
            cell = state.coverage_map.cells[key]
            cell.status = CellStatus.FILLED
            cell.display_hint = value
    state.frontier.add(
        FrontierTask(
            id="f",
            question="Find the top five universities",
            assigned_agent_id="search_agent_test",
            table_id="subject_rankings",
            target_cells=sorted(keys),
        )
    )
    mw = SOCMContextMiddleware(
        SimpleNamespace(load_state=lambda: state), task=TaskContext(agent_id="search_agent_test")
    )
    view = mw.render()
    assert "Assigned cells: 9; filled: 9" in view
    for entity in entities:
        assert all(part in view for part in row_values(entity))
    assert '"1", "99", "UK"' in view
    assert "Return findings and limitations; do not search unrelated columns." not in view
    assert "actionable gaps: 0; unavailable: 0" in view
    assert "Verify the assigned entity set" not in view


def test_unknown_explicit_target_is_visible_alongside_recorded_targets():
    state = state_with_rows(["Acme"])
    cell = state.coverage_map.cells[cell_key("t", row_key(["Acme"]), "Revenue")]
    cell.status = CellStatus.FILLED
    cell.display_hint = "100"
    state.frontier.add(
        FrontierTask(
            id="f",
            question="Collect revenue",
            assigned_agent_id="search_agent_test",
            table_id="t",
            target_cells=[cell_key("t", row_key(["Acme"]), "Revenue"), cell_key("t", row_key(["Missing"]), "Revenue"), cell_key("absent", row_key(["X"]), "Value")],
        )
    )
    mw = SOCMContextMiddleware(
        SimpleNamespace(load_state=lambda: state), task=TaskContext(agent_id="search_agent_test")
    )
    view = mw.render()
    assert "Unmatched targets" in view
    assert '"key": ["Missing"]' in view and '"table_id": "absent"' in view
    assert "not evidence of completion" not in view


def test_explicit_unknown_target_does_not_switch_to_discovery():
    state = state_with_rows(["Acme"])
    table = state.coverage_map.tables["t"]
    table.schema_mode = type(table.schema_mode)("column_only")
    state.frontier.add(
        FrontierTask(
            id="f",
            question="Find Missing revenue",
            table_id="t",
            assigned_agent_id="search_agent_test",
            target_cells=[cell_key("t", row_key(["Missing"]), "Revenue")],
        )
    )
    mw = SOCMContextMiddleware(
        SimpleNamespace(load_state=lambda: state), task=TaskContext(agent_id="search_agent_test")
    )
    view = mw.render()
    assert '"key": ["Missing"]' in view
    assert "rows discovered so far" not in view


def school_state():
    state = SearchState()
    state.coverage_map.add_table(
        "programs",
        ["学校名称", "专业", "学费", "入学要求"],
        primary_key=["学校名称", "专业"],
        entities=[
            row_key(["香港大学", "会计学硕士"]),
            row_key(["香港大学", "金融学硕士"]),
            row_key(["香港中文大学", "会计学硕士"]),
            row_key(["香港科技大学", "金融学硕士"]),
        ],
    )
    return state


def test_complete_refs_select_only_that_school_and_requested_columns():
    state = school_state()
    state.frontier.add(
        FrontierTask(
            id="f",
            question="香港大学所有项目学费",
            table_id="programs",
            assigned_agent_id="search_agent_test",
            target_cells=[cell_key("programs", row_key(["香港大学", name]), "学费")
                          for name in ("会计学硕士", "金融学硕士")],
        )
    )
    mw = SOCMContextMiddleware(
        SimpleNamespace(load_state=lambda: state), task=TaskContext(agent_id="search_agent_test")
    )
    view = mw.render()
    assert "Assigned cells: 2" in view
    assert '["香港大学", "会计学硕士",' in view and '["香港大学", "金融学硕士",' in view
    assert "香港中文大学" not in view and "香港科技大学" not in view
    assert "入学要求" in view
    assert "[[0, [2]], [1, [2]]]" in view


def test_task_text_respects_first_composite_key_component():
    state = school_state()
    state.frontier.add(
        FrontierTask(
            id="f",
            question="验证香港大学的会计学硕士、金融学硕士列表完整性",
            table_id="programs",
            assigned_agent_id="search_agent_test",
        )
    )
    mw = SOCMContextMiddleware(
        SimpleNamespace(load_state=lambda: state), task=TaskContext(agent_id="search_agent_test")
    )
    view = mw.render()
    assert '["香港大学", "会计学硕士",' in view and '["香港大学", "金融学硕士",' in view
    assert "香港中文大学" not in view and "香港科技大学" not in view
    assert "Unmatched targets" not in view
    assert "Assigned cells: 4" in view


def test_missing_school_does_not_match_another_schools_program():
    state = school_state()
    state.frontier.add(
        FrontierTask(
            id="f",
            question="香港城市大学 金融学硕士",
            table_id="programs",
            assigned_agent_id="search_agent_test",
        )
    )
    mw = SOCMContextMiddleware(
        SimpleNamespace(load_state=lambda: state), task=TaskContext(agent_id="search_agent_test")
    )
    view = mw.render()
    assert "Target match: none." in view
    assert "香港大学|金融学硕士" not in view


def test_full_composite_ref_is_resolved():
    state = school_state()
    state.frontier.add(
        FrontierTask(
            id="f",
            question="学费",
            table_id="programs",
            assigned_agent_id="search_agent_test",
            target_cells=[cell_key("programs", row_key(["香港大学", "金融学硕士"]), "学费")],
        )
    )
    mw = SOCMContextMiddleware(
        SimpleNamespace(load_state=lambda: state), task=TaskContext(agent_id="search_agent_test")
    )
    view = mw.render()
    assert "Assigned cells: 1" in view and '["香港大学", "金融学硕士",' in view
    assert "Unmatched targets" not in view


def test_task_summary_keeps_dispatch_scope_once_and_omits_worker_prompt():
    state = state_with_rows(["Acme"])
    task = FrontierTask(
        id="collect_revenue", question="Collect Acme revenue\nDetailed source instructions.",
        status="running", assigned_agent_id="search_agent_test", table_id="t",
        target_cells=[cell_key("t", row_key(["Acme"]), "Revenue")],
    )
    state.frontier.add(task)
    before = state.model_dump()
    overview = render_orchestrator_view(SearchStateSnapshot.from_state(state))
    assert overview.count("Collect Acme revenue") == 1
    assert "Detailed source instructions" not in overview
    assert "agent=search_agent_test" in overview and "table=t" in overview
    assert 'targets=[{"table_id": "t", "key": ["Acme"], "attribute": "Revenue"}]' in overview
    assert "in-flight tasks" not in overview
    assert '["Acme", null, null]' in overview

    worker = SOCMContextMiddleware(
        SimpleNamespace(load_state=lambda: state), task=TaskContext(agent_id="search_agent_test")
    ).render()
    assert "collect_revenue (running) | evidence=0" in worker
    assert "Collect Acme revenue" not in worker and "Detailed source instructions" not in worker
    assert '["Acme", null, null]' in worker
    assert state.model_dump() == before


def test_shared_column_definitions_are_grouped_and_schema_changes_remain_visible():
    state = state_with_rows(["Acme"])
    schema = state.coverage_map.tables["t"]
    for attr in ("Revenue", "Other"):
        schema.column_desc[attr] = ColumnDesc(desc="USD millions, fiscal 2025")
    view = render_search_agent_view(SearchStateSnapshot.from_state(state), {row_key(["Acme"])}, "t")
    assert view.count("USD millions, fiscal 2025") == 1
    assert '["Other", "Revenue"]: str: USD millions, fiscal 2025' in view
    schema.column_desc["Other"] = ColumnDesc(desc="USD billions, fiscal 2026")
    updated = render_search_agent_view(SearchStateSnapshot.from_state(state), {row_key(["Acme"])}, "t")
    assert '["Revenue"]: str: USD millions, fiscal 2025' in updated
    assert '["Other"]: str: USD billions, fiscal 2026' in updated
    assert '["Acme", null, null]' in updated
