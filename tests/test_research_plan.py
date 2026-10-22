"""计划持久化、完整性提示和成员复核不依赖特定领域。"""

import json
from types import SimpleNamespace

import pytest

from searchos.socm import EvidenceNode, SearchState
from searchos.socm.planning.research_plan import ResearchPlan, membership_review, render_research_plan


def plan(**overrides):
    return ResearchPlan(
        strategy=["broad"],
        evidence_obligations=["收集有来源的全部成员"],
        stop_rule="核对边界与成员；无法核实时说明缺口",
        **overrides,
    )


def test_equal_counts_do_not_hide_wrong_or_missing_members():
    state = SearchState(
        research_plan=plan(
            set_scope=[
                {
                    "boundary": "文档列举的全部服务",
                    "kind": "closed",
                    "table_id": "services",
                    "expected_members": ["A", "B"],
                    "expected_count": 2,
                    "basis_evidence_ids": ["list"],
                }
            ]
        )
    )
    state.evidence_graph.add_node(
        EvidenceNode(id="list", source="https://example.org/list", finding="A, B")
    )
    state.coverage_map.add_table("services", ["name"], primary_key=["name"], entities=["A", "C"])
    coverage = state.coverage_map.coverage_score
    review = membership_review(state)[0]
    assert review["missing_members"] == ["B"]
    assert review["unexpected_members"] == ["C"]
    assert review["count_difference_hint"] == 0
    assert review["basis_status"] == "source_linked"
    assert coverage == state.coverage_map.coverage_score == 1.0
    assert '"count_difference_hint": 0' in render_research_plan(state)
    state.evidence_graph.get_node("list").status = "rejected"
    assert membership_review(state)[0]["basis_status"] == "unverified"


def test_estimated_count_and_open_set_never_claim_complete():
    state = SearchState(
        research_plan=plan(
            set_scope=[
                {
                    "boundary": "可找到的实现",
                    "kind": "open",
                    "expected_count": 2,
                }
            ]
        )
    )
    state.coverage_map.add_table(
        "implementations", ["name"], primary_key=["name"], entities=["A", "B"]
    )
    review = membership_review(state)[0]
    assert review["comparison"] == "needs_review"
    assert review["basis_status"] == "unverified"
    assert "recall" not in review and "complete" not in review


@pytest.mark.asyncio
async def test_plan_tool_persists_and_rejects_unknown_basis(tmp_path, monkeypatch):
    from searchos.agents import runtime
    from searchos.socm.storage.workspace import WorkspaceManager
    from searchos.tools.tasks import set_research_plan

    workspace = WorkspaceManager(tmp_path, "plan")
    workspace.create()
    monkeypatch.setattr(runtime, "_ctx", SimpleNamespace(workspace=workspace))
    original = workspace.load_state()
    p = plan()
    response = json.loads(await set_research_plan.ainvoke({"plan_json": p.model_dump_json()}))
    assert response["plan"]["strategy"] == ["broad"]
    state = workspace.load_state()
    assert state.research_plan == p
    assert state.source_scope == original.source_scope
    assert state.budget == original.budget
    bad = p.model_dump()
    bad["set_scope"] = [{"boundary": "all", "basis_evidence_ids": ["unknown"]}]
    assert (await set_research_plan.ainvoke({"plan_json": json.dumps(bad)})).startswith("Error:")
    assert workspace.load_state().research_plan == p


def test_plan_appears_with_research_tasks_without_requiring_a_table(tmp_path):
    from searchos.socm import FrontierTask
    from searchos.harness.middleware.context.socm_middleware import SOCMContextMiddleware
    from searchos.harness.middleware.models import TaskContext
    from searchos.socm.storage.workspace import WorkspaceManager

    workspace = WorkspaceManager(tmp_path, "simple")
    workspace.create()
    state = workspace.load_state()
    state.research_plan = ResearchPlan(
        strategy=["simple"],
        evidence_obligations=["核验发布日期"],
        table_policy="none",
        stop_rule="取得正式发布记录",
    )
    workspace.save_state(state)
    middleware = SOCMContextMiddleware(
        workspace, task=TaskContext(agent_id="orchestrator"), view="overview"
    )
    assert not middleware.render()
    state.frontier.add(FrontierTask(id="release", question="核验发布日期", result_mode="findings"))
    workspace.save_state(state)
    rendered = middleware.render()
    assert "simple" in rendered and "正式发布记录" in rendered
    assert not workspace.load_state().coverage_map.tables


@pytest.mark.asyncio
async def test_actual_enqueue_inherits_plan_without_requiring_schema(tmp_path, monkeypatch):
    from searchos.agents import runtime
    from searchos.socm.storage.workspace import WorkspaceManager
    from searchos.tools import tasks
    from searchos.tools.search_state import _source_scope_var

    workspace = WorkspaceManager(tmp_path, "dispatch")
    workspace.create()
    state = SearchState(
        source_scope={"mode": "web", "documents": []},
        research_plan=ResearchPlan(
            strategy=["simple"],
            evidence_obligations=["核对官方数字"],
            table_policy="none",
            stop_rule="找到依据",
        ),
    )
    workspace.save_state(state)
    token = _source_scope_var.set(state.source_scope)

    class Scheduler:
        def allow_tasks(self, ids):
            pass

        async def tick(self):
            return {}

    monkeypatch.setattr(tasks.queue, "_scheduler", lambda: Scheduler())
    try:
        runtime.set_orchestrator_context(workspace=workspace, model=object())
        result = json.loads(
            await tasks.enqueue_tasks.ainvoke(
                {
                    "items": [
                        {"agent_type": "search_agent", "task": "Find the official maximum number"},
                    ],
                }
            )
        )
        assert result["queued"] and not result["errors"]
        state = workspace.load_state()
        assert not state.coverage_map.tables
        assert state.frontier.questions[0].result_mode == "findings"
        explicit = json.loads(
            await tasks.enqueue_tasks.ainvoke(
                {
                    "items": [{
                        "agent_type": "search_agent",
                        "task": "Fill a table",
                        "result_mode": "table",
                    }],
                }
            )
        )
        assert "error" in explicit
    finally:
        _source_scope_var.reset(token)


def test_explicit_table_target_wins_and_open_structure_defaults_to_findings():
    from searchos.tools.tasks.arguments import EnqueueTask
    from searchos.tools.tasks.queue import _task_result_mode

    def task(**kwargs):
        return EnqueueTask(agent_type="search_agent", task="Read the source", **kwargs)

    state = SearchState(research_plan=plan())
    assert _task_result_mode(state, task()) == "findings"
    assert _task_result_mode(state, task(target_table="items")) == "table"
    state.coverage_map.add_table("items", ["name"], primary_key=["name"])
    assert _task_result_mode(state, task()) == "table"
    assert _task_result_mode(state, task(result_mode="findings")) == "findings"


def test_table_without_set_boundary_keeps_completeness_obligation_visible():
    state = SearchState(research_plan=plan())
    state.coverage_map.add_table("items", ["name"], primary_key=["name"], entities=["A"])
    assert state.coverage_map.coverage_score == 1.0
    snapshot = render_research_plan(state)
    assert "not_declared" in snapshot
    assert '"membership_review": []' in snapshot
