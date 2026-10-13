"""追问在子任务未完成时唤醒主循环，并保留工具调用的完整上下文。"""

import asyncio
import json
import queue as sync_queue
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from searchos.agents import runtime
from searchos.config.settings import settings
from searchos.harness.session import SearchSession, _is_safe_steer_boundary
from searchos.harness.steering import SteeringQueue
from searchos.socm import SearchState, WorkspaceManager
from searchos.socm.frontier import FrontierTask, FrontierTaskStatus
from searchos.tools import tasks


def test_steering_waits_for_all_tool_results_even_after_context_updates():
    messages = [AIMessage(content="", tool_calls=[
        {"name": "check_agents", "args": {}, "id": "check"},
        {"name": "list_frontier", "args": {}, "id": "list"},
    ]), HumanMessage(content="SOCM update")]
    assert not _is_safe_steer_boundary({"messages": messages})
    messages.append(ToolMessage(content="{}", tool_call_id="list"))
    assert not _is_safe_steer_boundary({"messages": messages})
    messages.append(ToolMessage(content="{}", tool_call_id="check"))
    assert _is_safe_steer_boundary({"messages": messages})


@pytest.mark.asyncio
@pytest.mark.parametrize("delivery", ["web", "tui", "repeated", "legacy_async", "legacy_sync"])
async def test_follow_up_triggers_llm_before_subagent_returns(tmp_path, monkeypatch, delivery):
    from searchos.agents.orchestrator.scheduler import Scheduler

    queue = (asyncio.Queue() if delivery == "legacy_async" else
             sync_queue.Queue() if delivery == "legacy_sync" else SteeringQueue())
    waiting = asyncio.Event()
    received = asyncio.Event()
    received_again = asyncio.Event()
    workers = []
    calls = []
    message = "先核对年份" if delivery == "repeated" else "结束任务并输出最终内容"
    next_message = "现在结束并回答"

    async def tick(self):
        if not workers:
            worker = asyncio.create_task(asyncio.Event().wait())
            workers.append(worker)
            runtime._ctx.task_pool["search_one"] = worker
            runtime._ctx.agent_graphs["search_one"] = {
                "agent_type": "search_agent", "assigned_task_id": "task_one",
            }
            waiting.set()
        return {}

    class Model(BaseChatModel):
        @property
        def _llm_type(self):
            return "steering-offline"

        def bind_tools(self, tools, **kwargs):
            return self

        def _generate(self, messages, **kwargs):
            raise AssertionError("Expected async model invocation")

        async def _agenerate(self, messages, **kwargs):
            calls.append(messages)
            # Every issued tool call must have its result before another LLM request.
            pending = set()
            for msg in messages:
                pending.update(call["id"] for call in getattr(msg, "tool_calls", []))
                if isinstance(msg, ToolMessage):
                    pending.discard(msg.tool_call_id)
            assert not pending
            if len(calls) == 1:
                answer = AIMessage(content="", tool_calls=[{
                    "name": "check_agents", "args": {}, "id": "check_one",
                }])
            elif not received.is_set():
                assert any(msg.type == "human" and message in str(msg.content) for msg in messages)
                assert not workers[0].done(), "Follow-up must not wait for or cancel the sub-agent"
                received.set()
                call = ({"name": "check_agents", "args": {}, "id": "check_two"}
                        if delivery == "repeated" else {
                    "name": "stop_task", "id": "stop_one",
                    "args": {"task_ids_json": '["task_one"]', "reason": "User requested stop"},
                })
                answer = AIMessage(content="", tool_calls=[call])
            elif delivery == "repeated" and not received_again.is_set():
                assert any(msg.type == "human" and next_message in str(msg.content)
                           for msg in messages)
                assert not workers[0].done()
                received_again.set()
                answer = AIMessage(content="", tool_calls=[{
                    "name": "stop_task", "id": "stop_one",
                    "args": {"task_ids_json": '["task_one"]', "reason": "User requested stop"},
                }])
            else:
                answer = AIMessage(content="已按要求停止，尚无可报告的研究结果。")
            return ChatResult(generations=[ChatGeneration(message=answer)])

    monkeypatch.setattr(Scheduler, "tick", tick)
    for name in ("enable_skills", "enable_writer_agent", "enable_failure_memory"):
        monkeypatch.setattr(settings, name, False)
    model = Model()
    monkeypatch.setattr("searchos.config.models.get_model_for", lambda role: model)
    state = SearchState(intent="研究一个问题", research_mode="findings")
    state.frontier.add(FrontierTask(id="task_one", kind="search", question="Slow research",
        status=FrontierTaskStatus.RUNNING, assigned_agent_id="search_one"))
    session = SearchSession(workspace_root=str(tmp_path), max_time_s=0,
                            skill_library_path=str(tmp_path / "skills"))
    run = asyncio.create_task(session.run(state.intent, initial_state=state,
        session_id="steering-test", steer_queue=queue))
    try:
        await asyncio.wait_for(waiting.wait(), timeout=5)
        if delivery == "web":
            monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "web"))
            from api.routes import search

            monkeypatch.setattr(search, "WORKSPACE_ROOT", str(tmp_path))
            monkeypatch.setattr(search, "sessions", {
                "steering-test": {"status": "running", "steer_queue": queue},
            })
            await search.steer_search("steering-test", search.SteerRequest(message=message))
        elif delivery == "tui":
            await asyncio.to_thread(queue.put_nowait, message)
        else:
            queue.put_nowait(message)
        await asyncio.wait_for(received.wait(), timeout=2)
        if delivery == "repeated":
            queue.put_nowait(next_message)
            await asyncio.wait_for(received_again.wait(), timeout=2)
        result = await asyncio.wait_for(asyncio.shield(run), timeout=5)
        assert not result.execution_error
        assert workers[0].cancelled()
        assert result.search_state.frontier.questions[0].status == FrontierTaskStatus.CANCELLED
        assert len(calls) == (4 if delivery == "repeated" else 3)
        injected = [msg for msg in calls[1] if msg.type == "human" and message in str(msg.content)]
        assert len(injected) == 1
        tool_result = next(msg for msg in calls[1] if isinstance(msg, ToolMessage))
        assert json.loads(str(tool_result.content))["remaining"] == 1
    finally:
        if not run.done():
            run.cancel()
        await asyncio.gather(run, *workers, return_exceptions=True)


@pytest.mark.asyncio
async def test_concurrent_sessions_wake_only_their_own_wait_and_keep_follow_ups(
    tmp_path, monkeypatch,
):
    inboxes = [SteeringQueue(), SteeringQueue()]
    entered = [asyncio.Event(), asyncio.Event()]
    workers = []
    scheduler = SimpleNamespace(tick=AsyncMock(return_value={}))
    monkeypatch.setattr(tasks, "_scheduler", lambda: scheduler)

    async def collect(index):
        ws = WorkspaceManager(tmp_path, f"session-{index}")
        ws.create()
        ws.save_state(SearchState(intent="research", research_mode="findings"))
        runtime.set_orchestrator_context(workspace=ws, model=object(), steer_queue=inboxes[index])
        worker = asyncio.create_task(asyncio.Event().wait())
        workers.append(worker)
        runtime._ctx.task_pool["worker"] = worker
        entered[index].set()
        return json.loads(await tasks.check_agents.ainvoke({}))

    checks = [asyncio.create_task(collect(index)) for index in range(2)]
    try:
        await asyncio.wait_for(asyncio.gather(*(event.wait() for event in entered)), timeout=2)
        # Repeated and consecutive messages are distinct inputs; waking must not consume them.
        for message in ["调整方向", "调整方向", "现在结束"]:
            inboxes[0].put_nowait(message)
        first = await asyncio.wait_for(asyncio.shield(checks[0]), timeout=2)
        assert first["remaining"] == 1
        assert first["interrupted_by"] == "user_follow_up"
        assert not checks[1].done()
        assert all(not worker.done() for worker in workers)
        assert [inboxes[0].get_nowait() for _ in range(3)] == ["调整方向", "调整方向", "现在结束"]
        inboxes[1].put_nowait("补充要求")
        second = await asyncio.wait_for(asyncio.shield(checks[1]), timeout=2)
        assert second["interrupted_by"] == "user_follow_up"
        assert inboxes[1].get_nowait() == "补充要求"
    finally:
        for task in checks + workers:
            task.cancel()
        await asyncio.gather(*checks, *workers, return_exceptions=True)


@pytest.mark.asyncio
async def test_timed_out_or_cancelled_wait_keeps_workers_and_next_wake_usable(
    tmp_path, monkeypatch,
):
    ws = WorkspaceManager(tmp_path, "cleanup")
    ws.create()
    ws.save_state(SearchState(intent="research", research_mode="findings"))
    inbox = SteeringQueue()
    runtime.set_orchestrator_context(workspace=ws, model=object(), steer_queue=inbox)
    scheduler = SimpleNamespace(tick=AsyncMock(return_value={}))
    monkeypatch.setattr(tasks, "_scheduler", lambda: scheduler)
    worker = asyncio.create_task(asyncio.Event().wait())
    runtime._ctx.task_pool["worker"] = worker
    check = None
    try:
        timeout = json.loads(await tasks.check_agents.ainvoke({"timeout": 0.01}))
        assert timeout["remaining"] == 1 and not timeout["reports"]
        check = asyncio.create_task(tasks.check_agents.ainvoke({}))
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(check, timeout=0.01)
        assert not worker.done() and inbox.empty()
        inbox.put_nowait("在下次等待之前到达的追问")
        tick_count = scheduler.tick.await_count
        response = json.loads(await asyncio.wait_for(tasks.check_agents.ainvoke({}), timeout=2))
        assert response["interrupted_by"] == "user_follow_up"
        assert not worker.done()
        assert scheduler.tick.await_count == tick_count
        assert inbox.get_nowait() == "在下次等待之前到达的追问"
        # A cancelled notification leaves no stale signal for the next wait.
        check = asyncio.create_task(inbox.wait())
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(check, timeout=0.01)
        await asyncio.to_thread(inbox.put_nowait, "新追问")
        await asyncio.wait_for(inbox.wait(), timeout=2)
        assert inbox.get_nowait() == "新追问"
    finally:
        worker.cancel()
        if check is not None:
            check.cancel()
        await asyncio.gather(
            worker, *([check] if check is not None else []), return_exceptions=True,
        )
