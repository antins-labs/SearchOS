"""复用检索 Agent 时保留上下文，并隔离每次 Frontier Task 的执行状态。"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest
import pytest_asyncio
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage
from langchain_core.tools import tool
from pydantic import Field

from searchos.agents import runtime, search
from searchos.agents.orchestrator import lifecycle
from searchos.config.settings import settings
from searchos.socm import FrontierTask, FrontierTaskStatus, SearchState
from searchos.socm.storage.workspace import WorkspaceManager
from searchos.tools.search_state import _source_scope_var, set_workspace
from searchos.tools.tasks import queue


class Model(FakeMessagesListChatModel):
    requests: list = Field(default_factory=list, exclude=True)

    def bind_tools(self, tools, **kwargs):
        return self

    async def _agenerate(self, messages, **kwargs):
        self.requests.append(list(messages))
        return await super()._agenerate(messages, **kwargs)


def call(name, value, call_id):
    return AIMessage(content="", tool_calls=[{
        "name": name, "args": {"query": value}, "id": call_id,
    }])


async def enqueue_items(items):
    """同时验证字符串参数与结构化参数的派发接口。"""
    arguments = (
        {"items_json": json.dumps(items)}
        if "items_json" in queue.enqueue_tasks.args
        else {"items": items}
    )
    return json.loads(await queue.enqueue_tasks.ainvoke(arguments))


@pytest_asyncio.fixture
async def harness(tmp_path, monkeypatch):
    workspace = WorkspaceManager(tmp_path, "agent-reuse")
    workspace.create()
    workspace.save_state(SearchState(
        intent="研究项目 Alpha 和 Beta 的独立来源事实。",
        research_mode="findings", source_scope={"mode": "web"},
    ))
    monkeypatch.setattr(settings, "enable_scheduler", True)
    monkeypatch.setattr(settings, "enable_writer_agent", False)
    monkeypatch.setattr(settings, "max_search_agents_per_session", 0)
    monkeypatch.setattr(settings, "max_parallel_agents", 3)
    monkeypatch.setattr(settings, "spawn_stagger_s", 0)
    token = _source_scope_var.set({"mode": "web"})
    pools = []

    def configure(responses, tools=(), extraction_model=None):
        from searchos.tools.skills.catalog import _skill_access_policy_var

        model = Model(responses=responses)
        _source_scope_var.set({"mode": "web"})
        _skill_access_policy_var.set({
            "access_only": None, "access_deny": frozenset(),
            "strategy_deny": frozenset(), "orchestrator_deny": frozenset(),
        })
        set_workspace(workspace)
        monkeypatch.setattr(search, "get_tools", lambda *args, **kwargs: list(tools))
        runtime.set_orchestrator_context(
            workspace=workspace, model=model, extraction_model=extraction_model,
            scheduler_task_allowlist=set(),
        )
        pools.append(runtime._ctx.task_pool)
        return model

    async def spawn(task_id="first", brief="检查 Alpha 的资料。", **kwargs):
        def add(state):
            state.frontier.add(FrontierTask(
                id=task_id, question=brief, task_prompt=brief,
                kind="search", agent_type="search_agent", result_mode="findings",
            ))
            return state

        workspace.atomic_update_state(add)
        agent_id = await lifecycle._spawn_sub_agent(
            "search_agent", brief, [], bind_task_id=task_id, **kwargs,
        )
        return agent_id

    async def enqueue(agent_id, task_id="second", brief="检查 Beta 的资料。", **kwargs):
        return await enqueue_items([{
            "id": task_id, "agent_type": "search_agent", "task": brief,
            "result_mode": "findings", "agent_id": agent_id, **kwargs,
        }])

    yield SimpleNamespace(
        workspace=workspace, configure=configure, spawn=spawn, enqueue=enqueue,
    )
    pending = [task for pool in pools for task in pool.values() if not task.done()]
    for task in pending:
        task.cancel()
    await asyncio.gather(*pending, return_exceptions=True)
    _source_scope_var.reset(token)


@pytest.mark.asyncio
async def test_reuse_preserves_history_browser_and_updates_report_task(harness):
    from searchos.tools.simple_browser import _get_browser

    browsers = []

    @tool
    async def inspect_context(query: str) -> str:
        """Inspect the current browser without network access."""
        browser = _get_browser()
        browsers.append(browser)
        if query == "first":
            browser.search_history.append("loaded-source-alpha")
        else:
            assert "loaded-source-alpha" in browser.search_history
        return f"retained-context:{query}"

    model = harness.configure([
        call("inspect_context", "first", "lookup-a"), AIMessage("FIRST RESULT"),
        AIMessage("SIBLING RESULT"),
        call("inspect_context", "second", "lookup-b"), AIMessage("SECOND RESULT"),
    ], [inspect_context])
    agent_id = await harness.spawn()
    first_report = await runtime._ctx.task_pool[agent_id]
    original_thread = runtime._ctx.agent_graphs[agent_id]["thread_id"]
    sibling_id = await harness.spawn("sibling", "研究另一个独立项目。")
    await runtime._ctx.task_pool[sibling_id]

    receipt = await harness.enqueue(agent_id)
    assert receipt["queued"] == ["second"]
    assert not receipt["errors"] and not receipt["rejected"]
    second_report = await runtime._ctx.task_pool[agent_id]

    assert set(runtime._ctx.agent_graphs) == {agent_id, sibling_id}
    assert runtime._ctx.agent_graphs[agent_id]["thread_id"] == original_thread
    assert first_report.task_ids == ["first"]
    assert second_report.task_ids == ["second"]
    assert second_report.last_message == "SECOND RESULT"
    assert len(browsers) == 2 and browsers[0] is browsers[1]
    request = "\n".join(str(message.content) for message in model.requests[-1])
    assert "FIRST RESULT" in request
    assert "retained-context:first" in request
    assert "检查 Beta 的资料。" in request
    tasks = {task.id: task for task in harness.workspace.load_state().frontier.questions}
    for task_id in ("first", "second"):
        assert tasks[task_id].status == FrontierTaskStatus.COMPLETED
        assert tasks[task_id].assigned_agent_id == agent_id
        assert tasks[task_id].attempts == 1


@pytest.mark.asyncio
async def test_reuse_rebinds_extraction_and_progress_to_new_task(harness):
    passages = {
        "first": "Project Alpha records 12 observations during its 2025 experiment.",
        "second": "Project Beta records 27 observations during its 2026 experiment.",
    }

    class Judge:
        async def ainvoke(self, prompt):
            payload = json.loads(prompt.rsplit("\n", 1)[-1])
            if "candidates" in payload:
                result = [{"id": row["id"], "supported": True}
                          for row in payload["candidates"]]
            else:
                passage = next((text for text in passages.values()
                                if text in payload.get("text", "")), None)
                result = ([{"finding": passage, "source_excerpt": passage,
                            "relation": "supports"}] if passage else [])
            return SimpleNamespace(content=json.dumps(result))

    @tool("open")
    async def open_source(query: str) -> str:
        """Read a deterministic source page."""
        return (
            f"[Now viewing] Project {query}\nURL: https://example.org/{query}\n\n"
            f"L1: {passages[query]}"
        )

    harness.configure([
        call("open", "first", "read-a"), AIMessage("Alpha checked."),
        call("open", "second", "read-b"), AIMessage("Beta checked."),
    ], [open_source], Judge())
    agent_id = await harness.spawn()
    first_report = await runtime._ctx.task_pool[agent_id]
    first_extraction = runtime._ctx.agent_graphs[agent_id]["extraction"]
    assert first_report.evidence_nodes_added == 1
    receipt = await harness.enqueue(agent_id)
    assert receipt["queued"] == ["second"]
    second_report = await runtime._ctx.task_pool[agent_id]
    info = runtime._ctx.agent_graphs[agent_id]
    assert info["extraction"] is not first_extraction
    assert info["extraction"].task.task_id == "second"
    assert second_report.task_ids == ["second"]
    assert second_report.evidence_nodes_added == 1
    state = harness.workspace.load_state()
    nodes = {node.id: node for node in state.evidence_graph.nodes}
    findings = {task_id: {nodes[b.evidence_id].finding
                         for b in state.evidence_graph.task_bindings if b.task_id == task_id}
                for task_id in ("first", "second")}
    assert findings == {"first": {passages["first"]}, "second": {passages["second"]}}


@pytest.mark.asyncio
async def test_reuse_receives_new_task_budget_without_resetting_agent_identity(harness):
    queries = []

    @tool("search")
    async def source_search(query: str) -> str:
        """Search a deterministic source."""
        queries.append(query)
        return f"found:{query}"

    harness.configure([
        call("search", "first", "search-a"), AIMessage("First checked."),
        call("search", "second", "search-b"), AIMessage("Second checked."),
    ], [source_search])
    agent_id = await harness.spawn(search_budget=1)
    await runtime._ctx.task_pool[agent_id]
    receipt = await harness.enqueue(agent_id, max_searches=1)
    assert receipt["queued"] == ["second"]
    report = await runtime._ctx.task_pool[agent_id]
    assert report.task_ids == ["second"]
    assert queries == ["first", "second"]
    assert len(runtime._ctx.agent_graphs) == 1


@pytest.mark.asyncio
async def test_two_queued_tasks_for_same_agent_execute_serially(harness):
    entered, release = asyncio.Event(), asyncio.Event()
    active = 0
    peak = 0

    @tool
    async def hold_context(query: str) -> str:
        """Pause one task while the next remains queued."""
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        entered.set()
        try:
            if query == "second":
                await release.wait()
            return query
        finally:
            active -= 1

    harness.configure([
        AIMessage("Initial done."),
        call("hold_context", "second", "hold-b"), AIMessage("Second done."),
        call("hold_context", "third", "hold-c"), AIMessage("Third done."),
    ], [hold_context])
    agent_id = await harness.spawn()
    await runtime._ctx.task_pool[agent_id]
    receipt = await enqueue_items([
        {"id": task_id, "agent_type": "search_agent", "task": f"Research {task_id}.",
         "result_mode": "findings", "agent_id": agent_id}
        for task_id in ("second", "third")
    ])
    assert receipt["queued"] == ["second", "third"]
    await asyncio.wait_for(entered.wait(), 2)
    second_run = runtime._ctx.task_pool[agent_id]
    await runtime._scheduler().tick()
    assert runtime._ctx.task_pool[agent_id] is second_run
    tasks = {task.id: task for task in harness.workspace.load_state().frontier.questions}
    assert tasks["second"].status == FrontierTaskStatus.RUNNING
    assert tasks["third"].status == FrontierTaskStatus.PENDING
    assert len(runtime._ctx.agent_graphs) == 1
    release.set()
    assert (await second_run).task_ids == ["second"]
    await runtime._scheduler().tick()
    assert (await runtime._ctx.task_pool[agent_id]).task_ids == ["third"]
    assert peak == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid", [
    "missing", "role", "source_scope", "runtime_scope", "skill_policy",
])
async def test_reuse_rejects_missing_incompatible_or_unauthorized_agent(harness, invalid):
    harness.configure([AIMessage("Initial done.")])
    agent_id = await harness.spawn()
    await runtime._ctx.task_pool[agent_id]
    if invalid == "missing":
        agent_id = "unknown-search-agent"
    elif invalid == "role":
        runtime._ctx.agent_graphs[agent_id]["agent_type"] = "explore_agent"
    elif invalid == "source_scope":
        def change_scope(state):
            state.source_scope = {"mode": "hybrid", "documents": []}
            return state

        harness.workspace.atomic_update_state(change_scope)
        _source_scope_var.set({"mode": "hybrid", "documents": []})
    elif invalid == "runtime_scope":
        _source_scope_var.set({"mode": "hybrid", "documents": []})
    else:
        from searchos.tools.skills.catalog import _skill_access_policy_var

        _skill_access_policy_var.set({
            "access_only": frozenset(), "access_deny": frozenset(),
            "strategy_deny": frozenset(), "orchestrator_deny": frozenset(),
        })
    receipt = await harness.enqueue(agent_id)
    assert receipt["queued"] == []
    assert receipt["rejected"] and not receipt["errors"]
    assert len(harness.workspace.load_state().frontier.questions) == 1


@pytest.mark.asyncio
async def test_reuse_does_not_spend_another_agent_creation_slot(harness, monkeypatch):
    harness.configure([AIMessage("First done."), AIMessage("Second done.")])
    agent_id = await harness.spawn()
    await runtime._ctx.task_pool[agent_id]
    monkeypatch.setattr(settings, "max_search_agents_per_session", 1)
    receipt = await harness.enqueue(agent_id)
    assert receipt["queued"] == ["second"]
    assert (await runtime._ctx.task_pool[agent_id]).task_ids == ["second"]
    assert len(runtime._ctx.agent_graphs) == 1


@pytest.mark.asyncio
async def test_reuse_executes_loaded_snapshot_without_reloading_and_isolates_work(
    harness, tmp_path, monkeypatch,
):
    from searchos.skills.core.schema import parse_skill_file
    from searchos.tools.skills import execution

    package = tmp_path / "sample-skill"
    package.mkdir()
    (package / "SKILL.md").write_text(
        "---\nname: sample-skill\ndescription: Test source reader\n"
        "metadata:\n  searchos-category: access\n---\nOriginal instructions\n",
    )
    (package / "run.py").write_text("print('original')")
    skill = parse_skill_file(package)
    monkeypatch.setattr(execution, "_skill", lambda _name: skill)
    executions = []

    async def run_command(skill_dir, argv, *, work_dir, execution_dir, **kwargs):
        executions.append({
            "package": skill_dir, "work": work_dir,
            "script": (skill_dir / "run.py").read_text(),
        })
        result = {
            "execution_id": kwargs["execution_id"], "status": "completed",
            "started": True, "exit_code": 0, "stdout": "source ready",
            "stderr": "", "truncated": False, "artifacts": [],
        }
        execution._write_json(execution_dir / kwargs["execution_id"] / "record.json", result)
        return result

    monkeypatch.setattr("searchos.skills.runtime.command_runtime.run_command", run_command)
    execute = AIMessage(content="", tool_calls=[{
        "name": "exec", "args": {"skill": "sample-skill", "argv": ["python", "run.py"]},
        "id": "same-call-id-across-tasks",
    }])
    model = harness.configure([
        AIMessage(content="", tool_calls=[{
            "name": "load_skill", "args": {"skill_name": "sample-skill"}, "id": "load-a",
        }]),
        execute, AIMessage("First task checked."),
        execute.model_copy(deep=True), AIMessage("Second task checked."),
    ], [execution.load_skill, execution.exec_skill])
    agent_id = await harness.spawn()
    await runtime._ctx.task_pool[agent_id]
    assert len(executions) == 1
    (package / "run.py").write_text("raise RuntimeError('new unvalidated version')")
    receipt = await harness.enqueue(agent_id)
    assert receipt["queued"] == ["second"]
    report = await runtime._ctx.task_pool[agent_id]
    assert report.task_ids == ["second"]
    assert len(executions) == 2
    assert executions[0]["package"] == executions[1]["package"]
    assert executions[0]["work"] != executions[1]["work"]
    assert executions[1]["script"] == "print('original')"
    calls = [call for message in model.requests[-1]
             for call in getattr(message, "tool_calls", [])]
    assert sum(call["name"] == "load_skill" for call in calls) == 1


@pytest.mark.asyncio
async def test_local_agent_reuse_preserves_authorized_document_context(harness, tmp_path):
    from searchos.local.library import LocalLibraryService

    service = LocalLibraryService(tmp_path / "local-data")
    library = service.create_library("Research notes")
    incoming = tmp_path / "incoming.txt"
    incoming.write_text("Project Alpha studies persistent research state.")
    document = await service.index_uploaded_file(library.library_id, incoming, "notes.txt")
    record, _ = service._verified_blocks(library.library_id, [document["document_id"]])[0]
    scope = {
        "mode": "local", "index_root": library.index_root,
        "documents": [record.model_dump(mode="json")],
    }
    model = harness.configure([AIMessage("LOCAL FIRST"), AIMessage("LOCAL SECOND")])
    _source_scope_var.set(scope)

    def add(state):
        state.source_scope = scope
        state.frontier.add(FrontierTask(
            id="first", question="检查本地研究目标。", kind="search",
            agent_type="local_search_agent", result_mode="findings",
        ))
        return state

    harness.workspace.atomic_update_state(add)
    agent_id = await lifecycle._spawn_sub_agent(
        "local_search_agent", "检查本地研究目标。", [], bind_task_id="first",
    )
    await runtime._ctx.task_pool[agent_id]
    receipt = await harness.enqueue(agent_id, agent_type="local_search_agent")
    assert receipt["queued"] == ["second"]
    report = await runtime._ctx.task_pool[agent_id]
    assert report.task_ids == ["second"]
    assert len(runtime._ctx.agent_graphs) == 1
    text = "\n".join(str(message.content) for message in model.requests[-1])
    assert "LOCAL FIRST" in text
    assert "LOCAL SECOND" == report.last_message


@pytest.mark.asyncio
async def test_reuse_rejects_an_agent_still_running(harness):
    entered, release = asyncio.Event(), asyncio.Event()

    @tool
    async def wait_for_source(query: str) -> str:
        """Keep the first task active."""
        entered.set()
        await release.wait()
        return "ready"

    harness.configure([
        call("wait_for_source", "first", "wait-a"), AIMessage("Done."),
    ], [wait_for_source])
    agent_id = await harness.spawn()
    await asyncio.wait_for(entered.wait(), 2)
    receipt = await harness.enqueue(agent_id)
    assert receipt["queued"] == []
    assert receipt["rejected"] and not receipt["errors"]
    release.set()
    await runtime._ctx.task_pool[agent_id]
    assert len(harness.workspace.load_state().frontier.questions) == 1


@pytest.mark.asyncio
async def test_check_agents_delivers_every_uncollected_reuse_report_once(harness):
    from searchos.tools.tasks.reports import check_agents

    harness.configure([
        AIMessage("FIRST RESULT"), AIMessage("SECOND RESULT"), AIMessage("THIRD RESULT"),
    ])
    agent_id = await harness.spawn()
    await runtime._ctx.task_pool[agent_id]
    for task_id in ("second", "third"):
        receipt = await harness.enqueue(agent_id, task_id=task_id, brief=f"Research {task_id}.")
        assert receipt["queued"] == [task_id]
        await runtime._ctx.task_pool[agent_id]

    collected = json.loads(await check_agents.ainvoke({"timeout": 0.01}))
    assert [report["task_ids"] for report in collected["reports"]] == [
        ["first"], ["second"], ["third"],
    ]
    assert [report["agent_report"]["text"] for report in collected["reports"]] == [
        "FIRST RESULT", "SECOND RESULT", "THIRD RESULT",
    ]
    assert collected["remaining"] == 0
    again = json.loads(await check_agents.ainvoke({"timeout": 0.01}))
    assert again["reports"] == []


@pytest.mark.asyncio
async def test_check_agents_pre_tick_reuse_keeps_preceding_report(harness):
    from searchos.tools.tasks.reports import check_agents

    harness.configure([AIMessage("FIRST RESULT"), AIMessage("SECOND RESULT")])
    agent_id = await harness.spawn()
    await runtime._ctx.task_pool[agent_id]

    def enqueue_without_tick(state):
        state.frontier.add(FrontierTask(
            id="second", question="Check the independent Beta experiment.",
            task_prompt="Check the independent Beta experiment.", kind="search",
            agent_type="search_agent", result_mode="findings", requested_agent_id=agent_id,
        ))
        return state

    harness.workspace.atomic_update_state(enqueue_without_tick)
    runtime._scheduler().allow_tasks(["second"])
    collected = json.loads(await check_agents.ainvoke({"timeout": 1}))
    assert [report["task_ids"] for report in collected["reports"]] == [["first"], ["second"]]
    assert [report["agent_report"]["text"] for report in collected["reports"]] == [
        "FIRST RESULT", "SECOND RESULT",
    ]
    assert len(runtime._ctx.agent_graphs) == 1
    again = json.loads(await check_agents.ainvoke({"timeout": 0.01}))
    assert again["reports"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["cancelled", "tool_error"])
async def test_reuse_rejects_unfinished_checkpoint_after_interrupted_tool(harness, outcome):
    entered = asyncio.Event()

    @tool
    async def interrupted_source(query: str) -> str:
        """Interrupt source reading before a tool result is checkpointed."""
        entered.set()
        if outcome == "tool_error":
            raise RuntimeError("source read failed")
        await asyncio.Event().wait()
        return "unreachable"

    harness.configure([
        call("interrupted_source", "first", "interrupted-a"), AIMessage("Not reached."),
    ], [interrupted_source])
    agent_id = await harness.spawn()
    worker = runtime._ctx.task_pool[agent_id]
    await asyncio.wait_for(entered.wait(), 2)
    if outcome == "cancelled":
        worker.cancel()
        with pytest.raises(asyncio.CancelledError):
            await worker
    else:
        assert (await worker).status == "error"
    info = runtime._ctx.agent_graphs[agent_id]
    checkpoint = info["graph"].get_state({"configurable": {"thread_id": info["thread_id"]}})
    assert checkpoint.next
    receipt = await harness.enqueue(agent_id)
    assert receipt["queued"] == []
    assert receipt["rejected"]
    assert "checkpoint" in receipt["rejected"][0]["reason"]
    assert len(harness.workspace.load_state().frontier.questions) == 1


@pytest.mark.asyncio
async def test_stop_task_retains_capacity_until_cancelled_worker_has_stopped(harness, monkeypatch):
    entered, cancelled, release = asyncio.Event(), asyncio.Event(), asyncio.Event()

    @tool
    async def slow_cleanup(query: str) -> str:
        """Wait for cleanup even after cancellation arrives."""
        entered.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            await release.wait()
        return "cleanup finished"

    harness.configure([
        call("slow_cleanup", "first", "cleanup-a"), AIMessage("Cleanup complete."),
    ], [slow_cleanup])
    agent_id = await harness.spawn()
    worker = runtime._ctx.task_pool[agent_id]
    await asyncio.wait_for(entered.wait(), 2)

    async def do_not_wait_for_cleanup(tasks, **kwargs):
        await asyncio.sleep(0)
        return {task for task in tasks if task.done()}, {task for task in tasks if not task.done()}

    monkeypatch.setattr(queue.asyncio, "wait", do_not_wait_for_cleanup)
    stopped = json.loads(await queue.stop_task.ainvoke({"task_ids_json": '["first"]'}))
    await asyncio.wait_for(cancelled.wait(), 2)
    assert stopped["remaining"] == 1
    assert agent_id in stopped["running_ids"]
    assert runtime._ctx.task_pool[agent_id] is worker
    assert not worker.done()
    receipt = await harness.enqueue(agent_id)
    assert receipt["queued"] == []
    assert receipt["rejected"] and "busy" in receipt["rejected"][0]["reason"]
    release.set()
    await asyncio.gather(worker, return_exceptions=True)
