"""失败回收与重派不能切断任务证据，已有发现的循环任务交回主 Agent。"""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from searchos.agents.orchestrator.lifecycle import _compute_agent_report
from searchos.agents.runtime import _ctx, set_orchestrator_context
from searchos.socm import SearchState
from searchos.socm.evidence import EvidenceNode, EvidenceStatus, bind_task_evidence
from searchos.socm.frontier import FrontierTask, FrontierTaskStatus
from searchos.socm.workspace import WorkspaceManager
from searchos.tools import tasks


@pytest.mark.asyncio
@pytest.mark.parametrize("status,active,reassigned", [
    ("looped", True, False),
    ("looped", False, False),
    ("error", True, True),
])
async def test_recycled_report_retains_task_evidence(
    tmp_path, monkeypatch, status, active, reassigned,
):
    workspace = WorkspaceManager(tmp_path, "partial")
    workspace.create()
    state = SearchState(intent="research", research_mode="findings",
                        source_scope={"mode": "hybrid", "documents": []})
    state.frontier.add(FrontierTask(id="task", question="research", attempts=1,
        status=FrontierTaskStatus.RUNNING, assigned_agent_id="search_agent"))
    state.evidence_graph.add_node(EvidenceNode(id="fact", finding="supported fact",
                                             source="https://example.org"))
    bind_task_evidence(state, "task", ["fact"])
    if not active:
        state.evidence_graph.nodes[0].status = EvidenceStatus.REJECTED
    workspace.save_state(state)
    set_orchestrator_context(workspace=workspace, model=object())
    _ctx.agent_graphs["search_agent"] = {
        "agent_type": "search_agent", "assigned_task_id": "task",
    }
    report = _compute_agent_report(agent_id="search_agent", thread_id="search_agent",
        pre_snapshot={"evidence_ids": set(), "filled_keys": set()}, started_at=0,
        status=status, result="Stopped", last_ai_text="partial report")
    assert report.task_ids == ["task"]
    current = workspace.load_state()
    task = current.frontier.questions[0]
    needs_review = status == "looped" and active
    expected = FrontierTaskStatus.CANCELLED if needs_review else FrontierTaskStatus.PENDING
    assert task.status == expected
    assert task.assigned_agent_id == ""
    if needs_review:
        assert current.frontier.next() is None
    if reassigned:
        task.assigned_agent_id = "search_agent_2"
        task.status = FrontierTaskStatus.RUNNING
        workspace.save_state(current)

    # Collect after recycling/reassignment and after runtime graph cleanup.
    _ctx.agent_graphs.clear()
    _ctx.completed["search_agent"] = report
    done = asyncio.create_task(asyncio.sleep(0))
    await done
    _ctx.task_pool["search_agent"] = done
    scheduler = SimpleNamespace(tick=AsyncMock(return_value={}))
    monkeypatch.setattr(tasks, "_scheduler", lambda: scheduler)
    payload = json.loads(await tasks.check_agents.ainvoke({}))
    received = payload["reports"][0]
    assert received["task_ids"] == ["task"]
    assert received["grounded_findings_total"] == int(active)
    if active:
        assert received["grounded_findings"][0]["citation"] == "evidence:fact"
    if needs_review:
        assert "concrete unresolved gaps" in received["next_step_hint"]
