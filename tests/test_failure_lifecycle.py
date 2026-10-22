"""任务正常结束与异常退出均把本次轨迹交给统一复盘入口。"""

from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from searchos.agents.orchestrator import lifecycle
from searchos.socm import SearchReport
from searchos.socm.failure_memory import post_mortem


def messages(goal, call_id):
    return [
        HumanMessage(content=goal),
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "search",
                    "id": call_id,
                    "args": {"query": goal},
                }
            ],
        ),
        ToolMessage(
            content="No results",
            tool_call_id=call_id,
            artifact={"outcome": {"status": "success", "result_count": 0}},
        ),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("crash", [False, True])
async def test_task_exit_uses_one_review_entry_with_actual_current_attempt(monkeypatch, crash):
    current = messages("current goal", "current-call")
    history = messages("previous goal", "old-call") + current

    class Graph:
        async def astream(self, *args, **kwargs):
            yield {"messages": history}
            if crash:
                raise RuntimeError("runtime stopped after a completed search")

    info = dict(
        graph=Graph(),
        thread_id="reader",
        wrapped_task="current goal",
        task="current goal",
        pre_snapshot={},
        missing_skills=[],
        started_at=0,
        agent_type="search_agent",
        assigned_task_id="current",
        assigned_task_attempt=2,
    )
    context = SimpleNamespace(
        agent_graphs={"reader": info},
        conversation_logger=None,
        trajectory_logger=None,
        workspace=object(),
        post_mortem_model=object(),
        completed={},
    )
    monkeypatch.setattr(lifecycle, "_ctx", context)
    monkeypatch.setattr(
        lifecycle,
        "_compute_agent_report",
        lambda **kwargs: SearchReport(
            agent_id="reader",
            status=kwargs["status"],
            result=kwargs["result"],
        ),
    )
    received = []
    monkeypatch.setattr(
        post_mortem, "schedule_post_mortem", lambda **kwargs: received.append(kwargs)
    )

    report = await lifecycle._collect_sub_agent_result("reader")

    assert report.status == ("error" if crash else "completed")
    assert context.completed["reader"] is report
    assert len(received) == 1
    assert received[0]["task_id"] == "current"
    assert received[0]["attempt"] == 2
    assert received[0]["messages"] == current
    assert received[0]["workspace"] is context.workspace


@pytest.mark.asyncio
@pytest.mark.parametrize("crash", [False, True])
async def test_continuation_reviews_without_conversation_logging(monkeypatch, crash):
    current = messages("follow-up goal", "continued-call")

    class Graph:
        async def astream(self, *args, **kwargs):
            yield {"messages": current}
            if crash:
                raise RuntimeError("continuation stopped after retrieval")

    info = dict(
        graph=Graph(),
        thread_id="reader",
        task="original goal",
        agent_type="search_agent",
        assigned_task_id="current",
        assigned_task_attempt=0,
    )
    context = SimpleNamespace(
        agent_graphs={"reader": info},
        conversation_logger=None,
        trajectory_logger=None,
        workspace=SimpleNamespace(load_state=lambda: None),
        post_mortem_model=object(),
        completed={},
    )
    monkeypatch.setattr(lifecycle, "_ctx", context)
    monkeypatch.setattr(lifecycle, "_snapshot_state_for_diff", lambda state: {})
    monkeypatch.setattr(
        lifecycle,
        "_compute_agent_report",
        lambda **kwargs: SearchReport(
            agent_id="reader",
            status=kwargs["status"],
            result=kwargs["result"],
        ),
    )
    received = []
    monkeypatch.setattr(
        post_mortem, "schedule_post_mortem", lambda **kwargs: received.append(kwargs)
    )

    report = await lifecycle._continue_sub_agent_run("reader", "follow-up goal")

    assert report.status == ("error" if crash else "completed")
    assert context.completed["reader"] is report
    assert len(received) == 1
    assert received[0]["messages"] == current
    assert received[0]["attempt"] == 0


def test_missing_current_task_anchor_never_reuses_old_trajectory(monkeypatch):
    received = []
    monkeypatch.setattr(
        post_mortem, "schedule_post_mortem", lambda **kwargs: received.append(kwargs)
    )
    lifecycle._review_search_attempt(
        {"wrapped_task": "new task", "agent_type": "search_agent"},
        "reader",
        SearchReport(agent_id="reader", status="error"),
        messages("old task", "old-call"),
    )
    assert received == []
