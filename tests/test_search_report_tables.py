"""子 Agent 尚未提交表格证据时，返回报告也必须保留候选与范围。"""

from searchos.agents.orchestrator.lifecycle import _compute_agent_report
from searchos.agents.runtime import set_orchestrator_context
from searchos.socm import SearchState
from searchos.socm.workspace import WorkspaceManager


def test_search_report_preserves_uncommitted_table(tmp_path):
    workspace = WorkspaceManager(tmp_path, "report-table")
    workspace.create()
    workspace.save_state(SearchState(intent="Find the second smallest municipality"))
    set_orchestrator_context(workspace=workspace, model=object())
    brief = (
        "Candidates requiring verification:\n\n"
        "| Statewide rank | Municipality |\n"
        "|---|---|\n"
        "| 1 | Anhanguera |\n"
        "| 2 | Palmelo |\n\n"
        "Do not confuse this with a ranking among four sampled cities."
    )
    report = _compute_agent_report(
        agent_id="search_agent", thread_id="search_agent",
        pre_snapshot={"evidence_ids": set(), "filled_keys": set()},
        started_at=0, status="completed", result="Completed", last_ai_text=brief,
    )
    assert report.evidence_nodes_added == 0
    assert report.last_message == brief
