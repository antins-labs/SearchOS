"""通过真实执行图验证 SOCM 的更新、保留与恢复。"""

import asyncio

import pytest
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage
from langchain_core.tools import tool
from langgraph.checkpoint.memory import MemorySaver
from pydantic import Field

from searchos.agents.runtime import create_search_agent_graph
from searchos.harness.middleware import (
    CompactionContextMiddleware,
    DynamicTrimMiddleware,
    SOCMContextMiddleware,
    TaskContext,
)
from searchos.harness.middleware.extraction import InMemoryEvidenceStore
from searchos.socm import CellStatus, FrontierTask, SearchState


class Model(FakeMessagesListChatModel):
    received: list = Field(default_factory=list)

    def bind_tools(self, tools, **kwargs):
        return self

    async def _agenerate(self, messages, **kwargs):
        self.received.append(messages)
        return await super()._agenerate(messages, **kwargs)


def snapshots(messages):
    return [m for m in messages if m.additional_kwargs.get("sf_kind") == "socm_update"]


def workspace():
    state = SearchState()
    state.coverage_map.add_table("t", ["Name", "Value"], primary_key=["Name"], entities=["A", "B"])
    state.frontier.add(
        FrontierTask(
            id="task",
            question="A value",
            assigned_agent_id="reader",
            target_cells=["t/A.Value"],
        )
    )
    return InMemoryEvidenceStore(state)


def graph_for(ws, *, view="task", checkpointer=None, model=None, extra=()):
    model = model or Model(responses=[AIMessage(content="A recorded finding.")])
    graph = create_search_agent_graph(
        model=model,
        tools=[],
        checkpointer=checkpointer,
        middleware=[SOCMContextMiddleware(ws, task=TaskContext("reader"), view=view), *extra],
    )
    return graph, model


async def turn(graph, thread="socm", text="Continue"):
    updates = []
    config = {"configurable": {"thread_id": thread}}
    async for update in graph.astream(
        {"messages": [("user", text)]}, config, stream_mode="updates"
    ):
        updates.extend(update.get("model", {}).get("messages", []))
    return (await graph.aget_state(config)).values["messages"], snapshots(updates)


@pytest.mark.asyncio
@pytest.mark.parametrize("view", ["task", "overview", "writing"])
@pytest.mark.parametrize("research_mode", ["table", "findings"])
@pytest.mark.parametrize("routed", [False, True])
async def test_empty_question_has_no_socm(view, research_mode, routed):
    from searchos.harness.routing import research_route

    state = SearchState(research_mode=research_mode)
    if routed:
        state.research_plan = research_route("Question", "research required").plan()
    graph, model = graph_for(InMemoryEvidenceStore(state), view=view)
    history, updates = await turn(graph)
    assert not snapshots(model.received[-1])
    assert not snapshots(history)
    assert not updates


@pytest.mark.asyncio
async def test_only_relevant_changes_write_and_latest_state_stays_visible():
    ws = workspace()
    graph, model = graph_for(ws, extra=[DynamicTrimMiddleware(max_tokens=3000)])
    first, writes = await turn(graph)
    assert len(writes) == len(snapshots(first)) == 1
    stable_id = writes[0].id
    # 其他实体变化不更新当前任务视图。
    ws.state.coverage_map.cells["t/B.Value"].status = CellStatus.FILLED
    second, writes = await turn(graph)
    assert not writes
    assert len(snapshots(second)) == len(snapshots(model.received[-1])) == 1
    cell = ws.state.coverage_map.cells["t/A.Value"]
    cell.status, cell.display_hint = CellStatus.FILLED, "42"
    third, writes = await turn(graph)
    assert len(writes) == len(snapshots(third)) == 1
    assert writes[0].id == stable_id
    assert '"Value"="42"' in snapshots(model.received[-1])[0].content
    _, writes = await turn(graph)
    assert not writes
    assert '"Value"="42"' in snapshots(model.received[-1])[0].content


@pytest.mark.asyncio
async def test_checkpoint_rebuild_and_workspace_only_restore():
    ws, checkpoint = workspace(), MemorySaver()
    graph, _ = graph_for(ws, checkpointer=checkpoint)
    original, _ = await turn(graph)
    restored_ws = InMemoryEvidenceStore(SearchState.model_validate_json(ws.state.model_dump_json()))
    graph, model = graph_for(restored_ws, checkpointer=checkpoint)
    restored, writes = await turn(graph)
    assert not writes
    assert snapshots(restored) == snapshots(original)
    restored_ws.state.coverage_map.cells["t/A.Value"].display_hint = "new value"
    restored_ws.state.coverage_map.cells["t/A.Value"].status = CellStatus.FILLED
    restored, writes = await turn(graph)
    assert len(writes) == 1 and "new value" in snapshots(model.received[-1])[0].content
    # 没有旧执行图时，也从持久研究状态重建投影。
    graph, model = graph_for(restored_ws)
    history, writes = await turn(graph)
    assert len(writes) == len(snapshots(history)) == 1
    assert "new value" in snapshots(model.received[-1])[0].content


@pytest.mark.asyncio
async def test_state_removal_clears_snapshot_and_reappearance_is_visible():
    ws = workspace()
    graph, model = graph_for(ws, view="overview")
    await turn(graph)
    previous = ws.state
    ws.state = SearchState()
    history, writes = await turn(graph)
    assert not snapshots(history) and not snapshots(model.received[-1]) and not writes
    ws.state = previous
    history, writes = await turn(graph)
    assert len(writes) == len(snapshots(history)) == 1


@pytest.mark.asyncio
async def test_one_graph_keeps_threads_independent():
    graph, model = graph_for(workspace())
    for thread in ("one", "two", "one", "two"):
        history, _ = await turn(graph, thread)
        assert len(snapshots(history)) == len(snapshots(model.received[-1])) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["error", "cancel"])
async def test_failed_model_does_not_checkpoint_snapshot(outcome):
    started = asyncio.Event()

    class FailingModel(Model):
        async def _agenerate(self, messages, **kwargs):
            started.set()
            if outcome == "error":
                raise RuntimeError("model failed")
            await asyncio.Event().wait()

    checkpoint, ws = MemorySaver(), workspace()
    graph, _ = graph_for(ws, checkpointer=checkpoint, model=FailingModel(responses=[]))
    job = asyncio.create_task(turn(graph))
    await asyncio.wait_for(started.wait(), 5)
    if outcome == "cancel":
        job.cancel()
    with pytest.raises(RuntimeError if outcome == "error" else asyncio.CancelledError):
        await job
    config = {"configurable": {"thread_id": "socm"}}
    assert not snapshots((await graph.aget_state(config)).values["messages"])
    graph, model = graph_for(ws, checkpointer=checkpoint)
    history, writes = await turn(graph)
    assert len(writes) == len(snapshots(history)) == len(snapshots(model.received[-1])) == 1


@pytest.mark.asyncio
async def test_tool_loop_appends_changed_prompts_at_their_injection_positions(tmp_path):
    import json

    from searchos.harness.telemetry.conversation import (
        ConversationLogger,
        langchain_msg_to_conversation_msgs,
    )
    from searchos.harness.telemetry.episodic import TrajectoryLogger

    ws = workspace()

    @tool
    def record(value: str) -> str:
        """Record a value when provided."""
        if value:
            cell = ws.state.coverage_map.cells["t/A.Value"]
            cell.status, cell.display_hint = CellStatus.FILLED, value
        return "Completed"

    model = Model(
        responses=[
            AIMessage(
                content="", tool_calls=[{"name": "record", "args": {"value": value}, "id": str(i)}]
            )
            for i, value in enumerate(["", "42", ""])
        ]
        + [AIMessage(content="A has value 42.")]
    )
    logger = TrajectoryLogger(tmp_path / "socm.jsonl")
    conversation = ConversationLogger(tmp_path / "conversation.json")
    graph = create_search_agent_graph(
        model=model,
        tools=[record],
        trajectory_logger=logger,
        conversation_logger=conversation,
        agent_id="reader",
        middleware=[SOCMContextMiddleware(ws, task=TaskContext("reader"))],
    )
    config = {"configurable": {"thread_id": "socm"}}
    previous_count = 0
    writes = []
    # 与 session 相同：流式记录普通消息，模型边界记录本轮注入的 user prompt。
    async for kind, event in graph.astream(
        {"messages": [("user", "Continue")]}, config, stream_mode=["values", "updates"]
    ):
        if kind == "updates":
            writes.extend(snapshots(event.get("model", {}).get("messages", [])))
        elif "messages" in event:
            messages = event["messages"]
            for message in messages[previous_count:]:
                for entry in langchain_msg_to_conversation_msgs(message):
                    entry.agent_name = "reader"
                    conversation.log(entry)
            previous_count = len(messages)
    history = (await graph.aget_state(config)).values["messages"]
    assert len(writes) == 2
    assert len(snapshots(history)) == 1
    assert all(len(snapshots(messages)) == 1 for messages in model.received)
    assert [snapshots(messages)[0].content for messages in model.received] == [
        writes[0].content,
        writes[0].content,
        writes[1].content,
        writes[1].content,
    ]
    events = [json.loads(line) for line in (tmp_path / "socm.jsonl").read_text().splitlines()]
    assert sum(e.get("kind") == "socm_inject" for e in events) == 2
    assert all("sf_context_changed" not in m.additional_kwargs for m in snapshots(history))
    assert not langchain_msg_to_conversation_msgs(snapshots(history)[0])
    conversation.flush()
    saved = json.loads(
        (tmp_path / "conversations/snapshots/reader.json").read_text()
    )["messages"]
    injected = [m for m in saved if m["metadata"].get("synthetic") == "socm_update"]
    assert [m["content"] for m in injected] == [m.content for m in writes]
    assert all(m["role"] == "user" for m in injected)
    # 日志保留两个完整版本，分别位于首轮与产生新值的工具回执之后。
    assert injected[0]["step_index"] == 1
    second_position = injected[1]["step_index"]
    assert saved[second_position - 1]["role"] == "tool_result"
    assert saved[second_position - 1]["tool_call_id"] == "1"
    assert saved[second_position + 1]["role"] == "assistant"
    assert saved[second_position + 2]["tool_call_id"] == "2"
    assert 'missing "Value"' in injected[0]["content"]
    assert '"Value"="42"' in injected[1]["content"]
    # 从追加日志恢复后，历史注入内容和位置不受 checkpoint 原位更新影响。
    restored = ConversationLogger(tmp_path / "conversation.json")
    restored.hydrate()
    restored.flush()
    assert json.loads(
        (tmp_path / "conversations/snapshots/reader.json").read_text()
    )["messages"] == saved


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["trim", "compact"])
async def test_long_history_keeps_snapshot_across_context_reduction_and_restore(mode):
    checkpoint, ws = MemorySaver(), workspace()
    summarizer = Model(
        responses=[AIMessage(content="Read the prior sources; continue current work.")]
    )

    def reducers():
        if mode == "trim":
            return [DynamicTrimMiddleware(max_tokens=1500)]
        return [
            CompactionContextMiddleware(
                summarizer,
                context_window=4000,
                trigger_fraction=0.65,
                keep_recent_fraction=0.1,
                summary_fraction=0.075,
                reserve_fraction=0.05,
            )
        ]

    model = Model(
        responses=[AIMessage(content="Earlier reading " * 1700), AIMessage(content="Done")]
    )
    graph, _ = graph_for(ws, checkpointer=checkpoint, model=model, extra=reducers())
    first, _ = await turn(graph)
    latest = snapshots(first)[0]
    history, writes = await turn(graph)
    assert not writes
    assert snapshots(history) == [latest]
    assert snapshots(model.received[-1])[0].content == latest.content
    assert len(str(model.received[-1])) < 7000
    if mode == "compact":
        assert summarizer.received
        assert any(m.additional_kwargs.get("sf_kind") == "context_compaction" for m in history)
    graph, model = graph_for(ws, checkpointer=checkpoint, extra=reducers())
    history, writes = await turn(graph)
    assert not writes
    assert snapshots(history) == [latest]
    assert snapshots(model.received[-1])[0].content == latest.content


@pytest.mark.asyncio
@pytest.mark.parametrize("view", ["task", "overview", "writing"])
async def test_findings_without_schema_update_and_retract(view):
    from searchos.socm import EvidenceNode
    from searchos.socm.evidence.graph import EvidenceStatus, TaskEvidenceBinding

    state = SearchState(research_mode="findings")
    state.frontier.add(FrontierTask(id="mine", question="Research A", assigned_agent_id="reader"))
    state.frontier.add(FrontierTask(id="other", question="Research B", assigned_agent_id="other"))
    for task_id in ["mine", "other"]:
        state.evidence_graph.add_node(
            EvidenceNode(
                id=task_id,
                finding=f"finding-{task_id}",
                source=f"https://example.org/{task_id}",
            )
        )
        state.evidence_graph.task_bindings.append(
            TaskEvidenceBinding(task_id=task_id, evidence_id=task_id)
        )
    ws = InMemoryEvidenceStore(state)
    graph, model = graph_for(ws, view=view)
    history, writes = await turn(graph)
    assert len(writes) == 1
    assert "finding-mine" in snapshots(history)[0].content
    if view == "task":
        assert "finding-other" not in snapshots(history)[0].content
    # 证据数量不变的修订也必须更新。
    ws.state.evidence_graph.get_node("mine").finding = "corrected finding"
    history, writes = await turn(graph)
    assert len(writes) == 1 and "corrected finding" in snapshots(model.received[-1])[0].content
    ws.state.evidence_graph.get_node("mine").status = EvidenceStatus.REJECTED
    history, writes = await turn(graph)
    assert len(writes) == 1
    assert "corrected finding" not in snapshots(model.received[-1])[0].content


@pytest.mark.asyncio
@pytest.mark.parametrize("view", ["overview", "writing"])
async def test_evidence_without_tasks_or_tables_is_visible(view):
    from searchos.socm import EvidenceNode

    state = SearchState(research_mode="findings")
    state.evidence_graph.add_node(
        EvidenceNode(id="a", finding="A finding", source="https://example.org")
    )
    graph, model = graph_for(InMemoryEvidenceStore(state), view=view)
    history, writes = await turn(graph)
    assert len(writes) == 1 and "A finding" in snapshots(model.received[-1])[0].content


@pytest.mark.asyncio
async def test_disk_workspace_restores_without_checkpoint(tmp_path):
    from searchos.socm.storage.workspace import WorkspaceManager

    ws = WorkspaceManager(tmp_path, "restore")
    ws.create()
    ws.save_state(workspace().state)
    graph, _ = graph_for(ws)
    first, _ = await turn(graph)
    restored = WorkspaceManager(tmp_path, "restore")
    graph, model = graph_for(restored)
    history, writes = await turn(graph)
    assert len(writes) == 1 and snapshots(history) == snapshots(first)
    assert snapshots(model.received[-1])[0].content == snapshots(first)[0].content


@pytest.mark.asyncio
async def test_deleted_assigned_table_keeps_missing_target_visible():
    from searchos.socm import CoverageMap

    ws = workspace()
    graph, model = graph_for(ws)
    await turn(graph)
    ws.state.coverage_map = CoverageMap()
    _, writes = await turn(graph)
    assert len(writes) == 1
    text = snapshots(model.received[-1])[0].content
    assert "Unmatched assigned targets" in text and "t/A.Value" in text
    assert "actionable gaps: 0" not in text
