"""逐实体目标投影、角色指引与完整缺口。"""

from dataclasses import dataclass
from types import SimpleNamespace

import pytest
from langchain.agents.middleware.types import ModelResponse
from langchain_core.messages import AIMessage, HumanMessage

from searchos.agents.orchestrator.lifecycle import _build_sub_agent_context
from searchos.harness.middleware.context.socm_middleware import SOCMContextMiddleware
from searchos.harness.middleware.models import TaskContext
from searchos.socm import CellStatus, ColumnDesc, FrontierTask, SearchState
from searchos.socm.views.render import render_orchestrator_view, render_search_agent_view
from searchos.socm.views.snapshot import SearchStateSnapshot


def state_with_rows(rows):
    state = SearchState()
    state.coverage_map.add_table(
        "t", ["Name", "Revenue", "Other"], primary_key=["Name"], entities=rows
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
        assert "[AUTOMATED HARNESS — state snapshot]" in captured[-1]
    assert "2026-10-12" not in captured[-1]


def test_only_assigned_unfinished_columns_and_definitions():
    state = state_with_rows(["Acme", "Unrelated"])
    state.coverage_map.tables["t"].column_desc["Revenue"] = ColumnDesc(
        desc="USD millions, fiscal 2025"
    )
    keys = {"t/Acme.Revenue"}
    view = render_search_agent_view(SearchStateSnapshot.from_state(state), {"Acme"}, "t", keys)
    assert 'missing "Revenue"' in view
    assert '- "Acme": missing "Revenue".' in view
    assert "USD millions, fiscal 2025" in view
    assert "Other" not in view and "Unrelated" not in view
    state.coverage_map.cells["t/Acme.Revenue"].status = CellStatus.FILLED
    view = render_search_agent_view(SearchStateSnapshot.from_state(state), {"Acme"}, "t", keys)
    assert "No actionable gaps are marked in the matched cells." in view
    assert "Verify the assigned entity set" not in view
    assert "t/Acme.Revenue:" not in view


def test_conflicts_remain_actionable_and_unavailable_not_filled():
    state = state_with_rows(["Acme"])
    state.coverage_map.cells["t/Acme.Revenue"].status = CellStatus.FILLED
    state.coverage_map.cells["t/Acme.Revenue"].has_conflict = True
    state.coverage_map.cells["t/Acme.Other"].status = CellStatus.HARD_CELL
    view = render_search_agent_view(SearchStateSnapshot.from_state(state), {"Acme"}, "t")
    assert '"Revenue" status=conflict' in view
    assert "verification" not in view.lower()
    assert "filled: 0; actionable gaps: 1; unavailable: 1" in view


def test_exact_keys_preserve_punctuation_and_multiple_tables():
    state = state_with_rows(["Acme.Inc/US"])
    state.coverage_map.add_table("b", ["Name", "Value"], primary_key=["Name"], entities=["Beta"])
    state.frontier.add(
        FrontierTask(
            id="f",
            question="search",
            assigned_agent_id="search_agent_test",
            target_cells=["t/Acme.Inc/US.Revenue", "b/Beta.Value"],
        )
    )
    mw = SOCMContextMiddleware(
        SimpleNamespace(load_state=lambda: state), task=TaskContext(agent_id="search_agent_test")
    )
    view = mw.render()
    assert 'missing "Revenue"' in view and "Acme.Inc/US" in view
    assert 'missing "Value"' in view and "Beta" in view
    assert "Other" not in view


def test_large_tables_preserve_every_entity_attribute_gap():
    state = state_with_rows([f"Entity{i:04d}" for i in range(1500)])
    keys = {f"t/{e}.Revenue" for e in state.coverage_map.tables["t"].entities}
    view = render_search_agent_view(SearchStateSnapshot.from_state(state), set(), "t", keys)
    assert len(view) > 12_000
    assert view.count('missing "Revenue"') == 1500
    for entity in state.coverage_map.tables["t"].entities:
        assert f'- "{entity}": missing "Revenue".' in view
    assert "omitted" not in view and "truncated" not in view
    for i in range(100):
        state.coverage_map.cells[f"t/Entity{i:04d}.Revenue"].status = CellStatus.FILLED
    updated = render_search_agent_view(SearchStateSnapshot.from_state(state), set(), "t", keys)
    assert "Entity0100" in updated and "Entity1499" in updated
    assert '- "Entity0000": recorded "Revenue"' in updated
    assert '- "Entity0000": missing' not in updated
    orch = render_orchestrator_view(SearchStateSnapshot.from_state(state))
    assert "Entity0000" in orch and "Entity1499" in orch
    assert 'missing "Other"' in orch
    startup = _build_sub_agent_context(state, agent_type="search_agent")
    assert "Entity0000" not in startup
    assert "orchestrator maps" not in startup


def test_filled_known_rows_describe_coverage_boundary():
    state = state_with_rows(["Acme"])
    for cell in state.coverage_map.cells.values():
        cell.status = CellStatus.FILLED

    view = render_orchestrator_view(SearchStateSnapshot.from_state(state))

    assert "does not describe undiscovered rows" in view
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
            target_cells=["t/Acme.Revenue"],
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
    assert 'missing "Revenue"' in views[0]
    assert views[1] == views[0]
    cell = state.coverage_map.cells["t/Acme.Revenue"]
    cell.status = CellStatus.FILLED
    await mw.awrap_model_call(Request([HumanMessage(content="task")]), handler)
    assert "No actionable gaps are marked in the matched cells." in views[-1]
    assert "Verify the assigned entity set" not in views[-1]
    cell.has_conflict = True
    cell.display_hint = "different source value"
    await mw.awrap_model_call(Request([HumanMessage(content="task")]), handler)
    assert '"Revenue" status=conflict' in views[-1]
    assert "verification" not in views[-1].lower()
    assert "different source value" in views[-1]


def test_each_entity_keeps_status_and_candidate_together():
    state = state_with_rows(["A", "B", "C", "D"])
    state.coverage_map.cells["t/C.Revenue"].status = CellStatus.UNCERTAIN
    state.coverage_map.cells["t/C.Revenue"].display_hint = "80"
    state.coverage_map.cells["t/C.Other"].status = CellStatus.HARD_CELL
    state.coverage_map.cells["t/D.Revenue"].status = CellStatus.FILLED
    state.coverage_map.cells["t/D.Revenue"].has_conflict = True
    state.coverage_map.cells["t/D.Revenue"].display_hint = "100"
    state.coverage_map.cells["t/D.Other"].status = CellStatus.FILLED
    view = render_search_agent_view(
        SearchStateSnapshot.from_state(state), {"A", "B", "C", "D"}, "t"
    )
    assert '- "A": missing "Revenue", "Other".' in view
    assert '- "B": missing "Revenue", "Other".' in view
    assert '- "C": "Revenue" status=uncertain (candidate: "80"); "Other" unavailable.' in view
    assert (
        '- "D": "Revenue" status=conflict (current value: "100"); '
        'recorded "Other" (value preview unavailable).'
        in view
    )
    assert "verification" not in view.lower()
    assert "Attributes:" not in view and "Entities:" not in view and "Candidate for" not in view


def test_fully_recorded_composite_key_targets_show_rows_and_values():
    state = SearchState()
    entities = ["Engineering|University A", "Engineering|University B", "Engineering|University C"]
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
            key = f"subject_rankings/{entity}.{attr}"
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
        assert entity in view
    assert '"Rank"="1"' in view and '"Score"="99"' in view and '"Country"="UK"' in view
    assert "Return findings and limitations; do not search unrelated columns." not in view
    assert "No actionable gaps are marked in the matched cells." in view
    assert "Verify the assigned entity set" not in view


def test_unknown_explicit_target_is_visible_alongside_recorded_targets():
    state = state_with_rows(["Acme"])
    cell = state.coverage_map.cells["t/Acme.Revenue"]
    cell.status = CellStatus.FILLED
    cell.display_hint = "100"
    state.frontier.add(
        FrontierTask(
            id="f",
            question="Collect revenue",
            assigned_agent_id="search_agent_test",
            table_id="t",
            target_cells=["t/Acme.Revenue", "t/Missing.Revenue", "absent/X.Value"],
        )
    )
    mw = SOCMContextMiddleware(
        SimpleNamespace(load_state=lambda: state), task=TaskContext(agent_id="search_agent_test")
    )
    view = mw.render()
    assert "Unmatched assigned targets" in view
    assert "t/Missing.Revenue" in view and "absent/X.Value" in view
    assert "not evidence of completion" in view


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
            target_cells=["t/Missing.Revenue"],
        )
    )
    mw = SOCMContextMiddleware(
        SimpleNamespace(load_state=lambda: state), task=TaskContext(agent_id="search_agent_test")
    )
    view = mw.render()
    assert "t/Missing.Revenue" in view
    assert "rows discovered so far" not in view


def school_state():
    state = SearchState()
    state.coverage_map.add_table(
        "programs",
        ["学校名称", "专业", "学费", "入学要求"],
        primary_key=["学校名称", "专业"],
        entities=[
            "香港大学|会计学硕士",
            "香港大学|金融学硕士",
            "香港中文大学|会计学硕士",
            "香港科技大学|金融学硕士",
        ],
    )
    return state


def test_school_shorthand_expands_only_that_school_and_requested_columns():
    state = school_state()
    state.frontier.add(
        FrontierTask(
            id="f",
            question="香港大学所有项目学费",
            table_id="programs",
            assigned_agent_id="search_agent_test",
            target_cells=["香港大学.学费"],
        )
    )
    mw = SOCMContextMiddleware(
        SimpleNamespace(load_state=lambda: state), task=TaskContext(agent_id="search_agent_test")
    )
    view = mw.render()
    assert "Assigned cells: 2" in view
    assert "香港大学|会计学硕士" in view and "香港大学|金融学硕士" in view
    assert "香港中文大学" not in view and "香港科技大学" not in view
    assert "入学要求" not in view


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
    assert "香港大学|会计学硕士" in view and "香港大学|金融学硕士" in view
    assert "香港中文大学" not in view and "香港科技大学" not in view
    assert "Unmatched assigned targets" not in view
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
    assert "No matching assigned cells" in view
    assert "香港大学|金融学硕士" not in view


def test_unprefixed_full_entity_key_is_resolved():
    state = school_state()
    state.frontier.add(
        FrontierTask(
            id="f",
            question="学费",
            table_id="programs",
            assigned_agent_id="search_agent_test",
            target_cells=["香港大学|金融学硕士.学费"],
        )
    )
    mw = SOCMContextMiddleware(
        SimpleNamespace(load_state=lambda: state), task=TaskContext(agent_id="search_agent_test")
    )
    view = mw.render()
    assert "Assigned cells: 1" in view and "香港大学|金融学硕士" in view
    assert "Unmatched assigned targets" not in view
