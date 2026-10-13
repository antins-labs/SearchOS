"""论文检索失败后的恢复与证据汇报回归。"""

from types import SimpleNamespace

import pytest

from searchos.harness.middleware.sensor.core.models import ControlState
from searchos.harness.middleware.sensor.progress_middleware import ToolProgressMiddleware


@pytest.mark.asyncio
async def test_empty_skill_results_disable_execution_in_current_session(tmp_path, monkeypatch):
    from searchos.agents import runtime
    from searchos.harness.middleware.extraction import InMemoryEvidenceStore
    from searchos.skills.runtime.legacy import executor_runtime
    from searchos.socm import SearchState
    from searchos.tools import search_state, skill_catalog

    store = InMemoryEvidenceStore(SearchState())
    orch_token = runtime._workspace_var.set(store)
    token = search_state._workspace_var.set(store)
    calls = []

    async def execute(*args, **kwargs):
        calls.append(kwargs)
        return {"papers": [], "status": "empty"}

    monkeypatch.setattr(executor_runtime, "run_executor", execute)
    try:
        tool = skill_catalog._make_typed_tool(
            skill_name="academic_paper",
            skill_dir=tmp_path,
            description="papers",
            params_schema={"query": {"type": "string", "required": True}},
        )
        for query in ["agent training", "data science", "reasoning"]:
            result = await tool.ainvoke({"query": query})
        assert len(calls) == 2
        assert "banned" in result
        assert "academic_paper" in skill_catalog._banned_skills_from_state()
    finally:
        search_state._workspace_var.reset(token)
        runtime._workspace_var.reset(orch_token)


def test_search_results_allow_one_bounded_reading_recovery(monkeypatch):
    harness = ToolProgressMiddleware(ControlState(), limit=3)
    delta = SimpleNamespace(coverage_gain=0, new_evidence_count=0)
    result = (
        "[Now viewing] Search: agents\nURL: search://results\nL2: [0] https://example.org/paper"
    )
    for _ in range(3):
        feedback = harness.observe("search", delta, result)
    assert not harness.control.stopped
    assert "open" in feedback
    for _ in range(3):
        harness.observe("search", delta, result)
    assert harness.control.stopped


@pytest.mark.parametrize("scheme", ["https://example.org", "skill://fixture"])
def test_new_web_reads_without_extraction_do_not_reset_no_progress(monkeypatch, scheme):
    harness = ToolProgressMiddleware(ControlState(), limit=3)
    delta = SimpleNamespace(coverage_gain=0, new_evidence_count=0)
    for page in range(3):
        result = (
            f"[Now viewing] Paper\nURL: {scheme}/{page}\nL0: This paper studies agent training."
        )
        harness.observe("open", delta, result)

    assert harness.control.stopped


def test_hybrid_report_uses_bound_facts_instead_of_unverified_summary():
    from searchos.socm import SearchState
    from searchos.socm.evidence import EvidenceNode, bind_task_evidence
    from searchos.socm.frontier import FrontierTask
    from searchos.tools.tasks import _ground_hybrid_report

    state = SearchState(source_scope={"mode": "hybrid", "documents": []})
    state.frontier.add(FrontierTask(id="read", question="Read paper", result_mode="findings"))
    node = EvidenceNode(
        id="title",
        source="https://example.org/paper",
        finding="Title: AI-Salesman",
        source_excerpt="AI-Salesman",
    )
    state.evidence_graph.add_node(node)
    bind_task_evidence(state, "read", [node.id])
    report = {
        "last_message": "Title: Agentic Data Science Training",
        "evidence_bindings": [b.model_dump() for b in state.evidence_graph.task_bindings],
    }
    _ground_hybrid_report(report, state)
    assert "AI-Salesman" in report["last_message"]
    assert "Agentic Data Science" not in report["last_message"]
    assert report["grounded_findings"][0]["citation"] == "evidence:title"
    assert report["agent_report"]["verified"] is False
    empty = {"last_message": "Many papers found", "evidence_bindings": []}
    _ground_hybrid_report(empty, state)
    assert empty["grounded_findings"] == []
    assert "无已核验" in empty["last_message"]


@pytest.mark.parametrize(
    "result",
    [
        {"error": "missing required query", "status": "error"},
        {"error_type": "validation", "success": False},
        {"papers": [], "status": "ok"},
        {"records": [{"title": "Paper"}], "status": "ok"},
    ],
)
def test_validation_and_success_do_not_disable_skills(result):
    from searchos.tools.skill_catalog import _is_failed_result

    assert not _is_failed_result(result)
