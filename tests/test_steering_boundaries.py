"""真实图上的追问边界：生成、并发工具、收尾和取消。"""

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import tool

from searchos.agents import runtime
from searchos.harness.middleware.context.steering_middleware import SteeringMiddleware
from searchos.harness.steering import SteeringMessage, SteeringQueue
from searchos.socm import SearchState, WorkspaceManager
from searchos.tools import tasks


class ScriptModel(BaseChatModel):
    respond: object

    @property
    def _llm_type(self):
        return "steering-boundary-probe"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, **kwargs):
        raise AssertionError("Expected async model invocation")

    async def _agenerate(self, messages, **kwargs):
        response = await self.respond(messages)
        return ChatResult(generations=[ChatGeneration(message=response)])


def graph_for(respond, inbox, tools=(), events=None):
    recorder = SimpleNamespace(_append_raw=events.append) if events is not None else None
    return runtime.create_search_agent_graph(
        ScriptModel(respond=respond), tools,
        middleware=[SteeringMiddleware(inbox, trajectory_logger=recorder)],
    )


def user_texts(messages):
    return [m.content for m in messages if isinstance(m, HumanMessage)]


@pytest.mark.asyncio
@pytest.mark.parametrize("with_tool", [False, True])
async def test_deferred_during_generation_waits_and_survives_final_response(with_tool):
    inbox = SteeringQueue()
    entered, release = asyncio.Event(), asyncio.Event()
    calls, executed = [], []

    @tool
    async def lookup() -> str:
        """Read the requested source."""
        executed.append(True)
        return "source read"

    async def respond(messages):
        calls.append(messages)
        if len(calls) == 1:
            entered.set()
            await release.wait()
            return AIMessage(content="旧回复", tool_calls=[{
                "name": "lookup", "args": {}, "id": "read",
            }] if with_tool else [])
        assert user_texts(messages) == ["原问题", "[用户追问 — 实时插入]\n补充论文"]
        assert bool(executed) is with_tool
        return AIMessage(content="已包含论文")

    graph = graph_for(respond, inbox, [lookup])
    run = asyncio.create_task(graph.ainvoke({"messages": [("user", "原问题")]},
                                          {"configurable": {"thread_id": "deferred"}}))
    try:
        await asyncio.wait_for(entered.wait(), 2)
        inbox.put_nowait(SteeringMessage("补充论文", "after_tool"))
        await asyncio.sleep(0.03)
        assert len(calls) == 1 and not run.done()
        release.set()
        result = await asyncio.wait_for(run, 2)
        assert result["messages"][-1].content == "已包含论文"
        assert len(calls) == 2 and inbox.empty()
    finally:
        run.cancel()
        await asyncio.gather(run, return_exceptions=True)
    assert not inbox._waiters


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["immediate", "after_tool"])
async def test_follow_up_waits_for_entire_parallel_tool_batch(mode):
    inbox = SteeringQueue()
    started = [asyncio.Event(), asyncio.Event()]
    release = [asyncio.Event(), asyncio.Event()]
    finished = []
    calls = []

    @tool
    async def lookup(index: int) -> str:
        """Read one source."""
        started[index].set()
        await release[index].wait()
        finished.append(index)
        return f"source {index}"

    async def respond(messages):
        calls.append(messages)
        if len(calls) == 1:
            return AIMessage(content="", tool_calls=[
                {"name": "lookup", "args": {"index": i}, "id": f"read-{i}"} for i in range(2)
            ])
        assert sorted(finished) == [0, 1]
        assert len([m for m in messages if isinstance(m, ToolMessage)]) == 2
        assert user_texts(messages) == ["原问题", "[用户追问 — 实时插入]\n调整方向"]
        return AIMessage(content="完成")

    graph = graph_for(respond, inbox, [lookup])
    config = {"configurable": {"thread_id": mode}}
    run = asyncio.create_task(graph.ainvoke({"messages": [("user", "原问题")]}, config))
    try:
        await asyncio.wait_for(asyncio.gather(*(e.wait() for e in started)), 2)
        inbox.put_nowait(SteeringMessage("调整方向", mode))
        release[0].set()
        await asyncio.sleep(0.03)
        assert len(calls) == 1
        release[1].set()
        result = await asyncio.wait_for(run, 2)
        saved = (await graph.aget_state(config)).values["messages"]
        assert user_texts(saved) == user_texts(result["messages"])
        steer_index = next(i for i, m in enumerate(saved) if m.content.endswith("调整方向"))
        assert all(i < steer_index for i, m in enumerate(saved) if isinstance(m, ToolMessage))
    finally:
        run.cancel()
        await asyncio.gather(run, return_exceptions=True)


@pytest.mark.asyncio
async def test_consecutive_immediate_inputs_cancel_only_generation_and_persist_once():
    inbox = SteeringQueue()
    entered = [asyncio.Event(), asyncio.Event()]
    cancelled, calls, events = [], [], []

    @tool
    async def lookup() -> str:
        """Read a source after steering."""
        return "结果"

    async def respond(messages):
        index = len(calls)
        calls.append(messages)
        if index < 2:
            entered[index].set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancelled.append(index)
                raise
        assert user_texts(messages) == ["原问题", "[用户追问 — 实时插入]\n追问一",
                                      "[用户追问 — 实时插入]\n追问二"]
        if index == 2:
            return AIMessage(content="按新范围查询", tool_calls=[{
                "name": "lookup", "args": {}, "id": "read",
            }])
        assert any(isinstance(m, ToolMessage) and m.content == "结果" for m in messages)
        assert any(m.content == "按新范围查询" for m in messages)
        return AIMessage(content="最终回答")

    graph = graph_for(respond, inbox, [lookup], events)
    config = {"configurable": {"thread_id": "consecutive"}}
    run = asyncio.create_task(graph.ainvoke({"messages": [("user", "原问题")]}, config))
    try:
        for i, text in enumerate(["追问一", "追问二"]):
            await asyncio.wait_for(entered[i].wait(), 2)
            await asyncio.to_thread(inbox.put_nowait, SteeringMessage(text))
        result = await asyncio.wait_for(run, 2)
        assert cancelled == [0, 1] and len(calls) == 4
        saved = (await graph.aget_state(config)).values["messages"]
        assert user_texts(saved) == user_texts(result["messages"])
        assert len(user_texts(saved)) == 3
        assert [e["text"] for e in events] == ["追问一", "追问二"]
        assert len({e["message_id"] for e in events}) == 2
    finally:
        run.cancel()
        await asyncio.gather(run, return_exceptions=True)
    assert inbox.empty() and not inbox._waiters


@pytest.mark.asyncio
async def test_after_tool_does_not_wake_check_agents(tmp_path, monkeypatch):
    inbox = SteeringQueue()
    ws = WorkspaceManager(tmp_path, "wait")
    ws.create()
    ws.save_state(SearchState(intent="research", research_mode="findings"))
    runtime.set_orchestrator_context(workspace=ws, model=object(), steer_queue=inbox)
    scheduler = SimpleNamespace(tick=AsyncMock(return_value={}))
    monkeypatch.setattr(tasks, "_scheduler", lambda: scheduler)
    release = asyncio.Event()
    worker = asyncio.create_task(release.wait())
    runtime._ctx.task_pool["worker"] = worker
    check = asyncio.create_task(tasks.check_agents.ainvoke({}))
    try:
        inbox.put_nowait(SteeringMessage("稍后加入", "after_tool"))
        await asyncio.sleep(0.03)
        assert not check.done() and not worker.done()
        release.set()
        result = json.loads(await asyncio.wait_for(check, 2))
        assert result["remaining"] == 0
        assert "interrupted_by" not in result
        assert inbox.get_nowait().text == "稍后加入"
    finally:
        check.cancel()
        worker.cancel()
        await asyncio.gather(check, worker, return_exceptions=True)
    assert not inbox._waiters


@pytest.mark.asyncio
async def test_queue_modes_keep_duplicates_and_immediate_can_overtake_deferred():
    inbox = SteeringQueue()
    inbox.put_nowait(SteeringMessage("延后", "after_tool"))
    waiting = asyncio.create_task(inbox.wait(immediate_only=True))
    try:
        await asyncio.sleep(0.01)
        assert not waiting.done()
        for _ in range(2):
            await asyncio.to_thread(inbox.put_nowait, SteeringMessage("相同的追问"))
        await asyncio.wait_for(waiting, 2)
        received = inbox.drain(immediate_only=True)
        assert [m.text for m in received] == ["相同的追问", "相同的追问"]
        assert received[0].id != received[1].id
        assert [m.text for m in inbox.drain()] == ["延后"]
    finally:
        waiting.cancel()
        await asyncio.gather(waiting, return_exceptions=True)


@pytest.mark.asyncio
async def test_cancel_during_generation_cleans_up_notification_waiters():
    inbox = SteeringQueue()
    entered, cancelled = asyncio.Event(), asyncio.Event()

    async def respond(messages):
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    graph = graph_for(respond, inbox)
    run = asyncio.create_task(graph.ainvoke({"messages": [("user", "原问题")]},
                                          {"configurable": {"thread_id": "cancel"}}))
    await asyncio.wait_for(entered.wait(), 2)
    run.cancel()
    await asyncio.gather(run, return_exceptions=True)
    assert cancelled.is_set() and not inbox._waiters


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["immediate", "after_tool"])
async def test_web_endpoint_preserves_delivery_mode(tmp_path, monkeypatch, mode):
    from pydantic import ValidationError

    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "web"))
    from api.routes import search

    inbox = SteeringQueue()
    monkeypatch.setattr(search, "WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr(search, "sessions", {"active": {"status": "running", "steer_queue": inbox}})
    result = await search.steer_search("active", search.SteerRequest(message="  论文  ", mode=mode))
    message = inbox.get_nowait()
    assert message.text == "论文" and message.mode == mode
    assert result["status"] == "queued" and result["mode"] == mode
    assert result["message_id"] == message.id
    assert result["queue"]["messages"][0]["id"] == message.id
    with pytest.raises(ValidationError):
        search.SteerRequest(message="论文", mode="unknown")


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["immediate", "after_tool"])
async def test_finalization_accepts_and_records_late_follow_up(tmp_path, mode):
    from searchos.harness.session import _finalize_stopped_research

    inbox = SteeringQueue()
    entered, release = asyncio.Event(), asyncio.Event()
    calls, logged, events, outputs = [], [], [], {}
    state = SearchState(intent="原问题", research_mode="findings")
    steering = SteeringMiddleware(
        inbox, trajectory_logger=SimpleNamespace(_append_raw=events.append),
    )

    async def respond(messages):
        calls.append(messages)
        if len(calls) == 1:
            entered.set()
            await release.wait()
            return AIMessage(content="旧回答")
        assert user_texts(messages)[-1] == "[用户追问 — 实时插入]\n用中文回答并保留来源"
        return AIMessage(content="尚无可核实的来源。")

    run = asyncio.create_task(_finalize_stopped_research(
        workspace=SimpleNamespace(load_state=lambda: state,
                                  write_output=lambda name, text: outputs.update({name: text})),
        state=state, query=state.intent, orchestrator_model=ScriptModel(respond=respond),
        stop_reason="budget_exhausted", steering=steering, follow_ups=steering.delivered,
        conversation_logger=SimpleNamespace(log=logged.append),
    ))
    try:
        await asyncio.wait_for(entered.wait(), 2)
        inbox.put_nowait(SteeringMessage("用中文回答并保留来源", mode))
        if mode == "after_tool":
            await asyncio.sleep(0.03)
            assert len(calls) == 1
            release.set()
        assert await asyncio.wait_for(run, 2) == "尚无可核实的来源。"
        assert len(calls) == 2 and len(events) == 1
        assert [(m.role, m.metadata.get("steer_mode")) for m in logged] == [
            ("user", mode), ("assistant", None),
        ]
    finally:
        run.cancel()
        await asyncio.gather(run, return_exceptions=True)


@pytest.mark.asyncio
async def test_promote_pending_message_wakes_generation_without_duplicate_delivery():
    inbox = SteeringQueue()
    entered = asyncio.Event()
    calls = []
    deferred = SteeringMessage("只查论文", "after_tool")

    async def respond(messages):
        calls.append(messages)
        if len(calls) == 1:
            entered.set()
            await asyncio.Event().wait()
        assert user_texts(messages) == ["原问题", "[用户追问 — 实时插入]\n只查论文"]
        return AIMessage(content="收到")

    graph = graph_for(respond, inbox)
    run = asyncio.create_task(graph.ainvoke({"messages": [("user", "原问题")]},
                                          {"configurable": {"thread_id": "promote"}}))
    try:
        await asyncio.wait_for(entered.wait(), 2)
        inbox.put_nowait(deferred)
        await asyncio.sleep(0.02)
        assert len(calls) == 1
        assert inbox.promote(deferred.id)
        await asyncio.wait_for(run, 2)
        assert len(calls) == 2
        assert inbox.snapshot()["messages"] == [{
            "id": deferred.id, "text": deferred.text, "mode": "immediate", "status": "delivered",
        }]
        assert not inbox.promote(deferred.id) and not inbox.remove(deferred.id)
        assert inbox.empty()
    finally:
        run.cancel()
        await asyncio.gather(run, return_exceptions=True)


def test_deleting_pending_message_preserves_identical_peer_and_revision():
    inbox = SteeringQueue()
    first = SteeringMessage("相同追问", "after_tool")
    second = SteeringMessage("相同追问", "after_tool")
    inbox.put_nowait(first)
    inbox.put_nowait(second)
    previous = inbox.snapshot()
    assert inbox.remove(first.id)
    assert inbox.snapshot()["revision"] > previous["revision"]
    assert previous["messages"][0]["status"] == "queued"
    assert [item.id for item in inbox.drain()] == [second.id]
    assert [m["status"] for m in inbox.snapshot()["messages"]] == ["cancelled", "delivered"]


@pytest.mark.asyncio
async def test_web_pending_queue_promote_delete_and_consumed_race(tmp_path, monkeypatch):
    from fastapi import HTTPException

    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "web"))
    from api.routes import search

    inbox = SteeringQueue()
    monkeypatch.setattr(search, "WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr(search, "sessions", {"active": {"status": "running", "steer_queue": inbox}})
    request = search.SteerRequest(message="论文", mode="after_tool")
    first = await search.steer_search("active", request)
    second = await search.steer_search("active", request)
    assert len((await search.get_steering_queue("active"))["messages"]) == 2
    removed = await search.remove_steering_message("active", first["message_id"])
    assert removed["messages"][0]["status"] == "cancelled"
    promoted = await search.promote_steering_message("active", second["message_id"])
    assert promoted["messages"][1]["mode"] == "immediate"
    inbox.drain()
    for mutate in (search.promote_steering_message, search.remove_steering_message):
        with pytest.raises(HTTPException) as error:
            await mutate("active", second["message_id"])
        assert error.value.status_code == 409
    search.sessions["active"]["status"] = "completed"
    assert (await search.get_steering_queue("active"))["messages"][1]["status"] == "delivered"
    with pytest.raises(HTTPException) as error:
        await search.promote_steering_message("active", second["message_id"])
    assert error.value.status_code == 409


@pytest.mark.asyncio
async def test_removed_immediate_does_not_restart_running_generation():
    inbox = SteeringQueue()
    entered, release = asyncio.Event(), asyncio.Event()
    calls, cancelled = [], []

    async def respond(messages):
        calls.append(messages)
        entered.set()
        try:
            await release.wait()
        except asyncio.CancelledError:
            cancelled.append(True)
            raise
        return AIMessage(content="原回答")

    graph = graph_for(respond, inbox)
    run = asyncio.create_task(graph.ainvoke({"messages": [("user", "原问题")]},
                                          {"configurable": {"thread_id": "removed"}}))
    try:
        await asyncio.wait_for(entered.wait(), 2)
        message = SteeringMessage("撤回追问", "after_tool")
        inbox.put_nowait(message)
        assert inbox.promote(message.id)
        assert inbox.remove(message.id)
        await asyncio.sleep(0.03)
        assert not cancelled and len(calls) == 1
        release.set()
        result = await asyncio.wait_for(run, 2)
        assert user_texts(result["messages"]) == ["原问题"]
    finally:
        run.cancel()
        await asyncio.gather(run, return_exceptions=True)
