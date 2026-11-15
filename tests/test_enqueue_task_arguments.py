"""通过真实工具与执行图验证派发参数、正文保真及失败恢复。"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.utils.function_calling import convert_to_openai_tool

from searchos.agents.runtime import create_search_agent_graph
from searchos.config.settings import settings
from searchos.socm import SearchState
from searchos.socm.refs import cell_key, cell_ref, row_key
from searchos.socm.storage.workspace import WorkspaceManager
from searchos.tools.search_state import _source_scope_var
from searchos.tools.tasks import queue

BRIEF = (
    "Explain why in JavaScript the pattern items.forEach(async item => await save(item)) "
    "shows the success prompt before all items are actually saved, and provide three "
    "implementations: sequential save, full concurrency, and max 5 concurrent, "
    "each with failure handling.\n\n"
    "Research these four points with authoritative sources "
    "(MDN preferred, Chinese docs also fine):\n\n"
    "1. CAUSE: Array.prototype.forEach does not await async callbacks. forEach ignores "
    "the callback's return value, so async callbacks that return Promises are not awaited. "
    "forEach fires all callbacks and returns immediately, so following code (the success "
    "prompt) runs before saves finish. This is fire-and-forget behavior and may create "
    "unhandled Promise rejections. Cite MDN's forEach + async/await note.\n\n"
    "2. SEQUENTIAL implementation: use for...of with await, or reduce chaining promises. "
    "One item awaited at a time; first failure short-circuits and stops remaining items. "
    "Provide code and failure handling (try/catch, rethrow, continue).\n\n"
    "3. FULL CONCURRENCY: Promise.all(items.map(i => save(i))). All requests fired at once; "
    "one failure rejects the whole Promise.all (short-circuits, though all requests already "
    "sent). Use Promise.allSettled to wait for all including failures. Provide code.\n\n"
    "4. MAX 5 CONCURRENT: build a concurrency pool / semaphore queue, or use p-limit library. "
    "Give failure handling options: retry failed item, skip and continue, "
    "or abort all on first failure.\n\n"
    "Provide key code snippets, pros/cons comparison, and failure semantics differences. "
    "Note source URLs. Output findings mode with no table."
)


@pytest.fixture
def dispatch(tmp_path, monkeypatch):
    workspace = WorkspaceManager(tmp_path, "enqueue-arguments")
    workspace.create()
    workspace.save_state(SearchState(source_scope={"mode": "web"}))
    scheduler = SimpleNamespace(allow_tasks=Mock(), tick=AsyncMock(return_value={}))
    monkeypatch.setattr(queue, "_ctx", SimpleNamespace(
        workspace=workspace, task_pool={}, skill_registry=None, repair_target_allowlist=None,
    ))
    monkeypatch.setattr(queue, "_scheduler", lambda: scheduler)
    monkeypatch.setattr(settings, "max_search_agents_per_session", 0)
    token = _source_scope_var.set({"mode": "web"})
    try:
        yield workspace, scheduler
    finally:
        _source_scope_var.reset(token)


def task(brief=BRIEF):
    return {"agent_type": "search_agent", "task": brief}


@pytest.mark.asyncio
async def test_named_prerequisite_and_generated_dependent_id(dispatch):
    workspace, _ = dispatch
    result = json.loads(await queue.enqueue_tasks.ainvoke({"items": [
        {**task("Identify available editions."), "task_id": "editions"},
        {**task("Compare their release dates."), "blocked_by": ["editions"]},
    ]}))
    prerequisite, dependent = workspace.load_state().frontier.questions
    assert result["queued"] == [prerequisite.id, dependent.id]
    assert prerequisite.id == "editions" and dependent.id.startswith("t_")
    assert dependent.blocked_by == [prerequisite.id]
    assert dependent.status.value == "blocked"
    duplicate = json.loads(await queue.enqueue_tasks.ainvoke({"items": [
        {**task("Some other question."), "task_id": "editions"},
    ]}))
    assert duplicate["queued"] == []
    assert "task id already exists" in duplicate["rejected"][0]["reason"]


@pytest.mark.asyncio
async def test_unscoped_task_remains_unrestricted_after_schema_creation(dispatch):
    workspace, _ = dispatch
    async def enqueue(**scope):
        return json.loads(await queue.enqueue_tasks.ainvoke({"items": [{**task("Compare providers"), **scope}]}))

    first = await enqueue()
    state = workspace.load_state()
    for tid in ("providers", "prices"):
        state.coverage_map.add_table(tid, ["Name", "Value"], primary_key=["Name"], entities=[row_key(["A"])])
    # Load a task saved by the previous version and deduplicate it after schema creation.
    payload = state.model_dump()
    payload["frontier"]["questions"][0]["result_mode"] = "findings"
    workspace.save_state(SearchState.model_validate(payload))
    duplicate = await enqueue()
    assert duplicate["deduped"] == [{"index": 0, "existing_id": first["queued"][0]}]
    cell = {"table_id": "prices", "key": ["A"], "attribute": "Value"}
    scoped = await enqueue(target_cells=[cell])
    assert scoped["queued"]
    assert (await enqueue(target_table="providers", target_cells=[cell]))["rejected"]
    assert (await enqueue(target_cells=[cell, {**cell, "table_id": "providers"}]))["rejected"]
    stored = workspace.load_state().frontier.questions
    assert [t.table_id for t in stored] == ["", "prices"]
    assert stored[1].target_cells == [cell_key("prices", row_key(["A"]), "Value")]


@pytest.mark.asyncio
async def test_inferred_columns_stay_out_of_search_dispatch_and_extraction(dispatch):
    from searchos.harness.middleware.extraction.core.tables.rows import RowExtractor
    from searchos.harness.middleware.extraction.core.models import ExtractionConfig
    from searchos.socm import ColumnDesc

    workspace, _ = dispatch
    state = workspace.load_state()
    school = row_key(["北京大学"])
    state.coverage_map.add_table("schools", ["学校", "省份", "分数线"], primary_key=["学校"],
        entities=[school], column_desc={"省份": ColumnDesc(requires_search=False)})
    workspace.save_state(state)
    province, score = [cell_key("schools", school, col) for col in ("省份", "分数线")]
    extraction = RowExtractor(None, ExtractionConfig(dual_mode=True))
    assert extraction.plan_calls("schools", state, []) == [("fill", {score}), ("discover", None)]
    item = {"agent_type": "search_agent", "task": "查分数线", "target_cells": [cell_ref(province), cell_ref(score)]}
    receipt = json.loads(await queue.enqueue_tasks.ainvoke({"items": [item]}))
    assert not receipt["queued"] and receipt["rejected"][0]["target_cells"] == [cell_ref(province)]
    item["target_cells"] = [cell_ref(score)]
    assert json.loads(await queue.enqueue_tasks.ainvoke({"items": [item]}))["queued"]


@pytest.mark.asyncio
async def test_large_target_batches_normalize_and_reject_partial_overlaps(dispatch, monkeypatch):
    from searchos.agents.orchestrator import lifecycle

    workspace, _ = dispatch
    monkeypatch.setattr(lifecycle, "_ctx", queue._ctx)
    state = workspace.load_state()
    state.coverage_map.add_table("t", ["Name", "Value"], primary_key=["Name"],
                                 entities=[row_key([f"E{i:04d}"]) for i in range(1001)])
    workspace.save_state(state)

    def item(keys, **extra):
        return {"agent_type": "search_agent", "task": "Collect each assigned value.",
                "target_table": "t", "target_cells": [cell_ref(cell_key("t", row_key([key]), "Value")) for key in keys], **extra}

    first = json.loads(await queue.enqueue_tasks.ainvoke({"items": [
        item([f"E{i:04d}" for i in range(1000)]),
    ]}))
    assert len(first["queued"]) == 1
    stored = workspace.load_state().frontier.questions[0]
    assert len(stored.target_cells) == 1000
    assert stored.target_cells[0] == cell_key("t", row_key(["E0000"]), "Value")
    # 已到创建额度时仍可返回已存在的任务。
    monkeypatch.setattr(settings, "max_search_agents_per_session", 1)
    duplicate = json.loads(await queue.enqueue_tasks.ainvoke({"items": [
        item(["E0000"]),
    ]}))
    assert duplicate["deduped"] == [{"index": 0, "existing_id": stored.id}]
    overlap = json.loads(await queue.enqueue_tasks.ainvoke({"items": [
        item(["E0999", "E1000"]),
    ]}))
    assert overlap["rejected"][0]["overlaps"] == [
        {"task_id": stored.id, "cells": [cell_ref(cell_key("t", row_key(["E0999"]), "Value"))]},
    ]
    assert len(workspace.load_state().frontier.questions) == 1
    monkeypatch.setattr(settings, "max_search_agents_per_session", 0)
    independent = json.loads(await queue.enqueue_tasks.ainvoke({"items": [
        item(["E0000"], blocked_by=[stored.id]),
    ]}))
    assert len(independent["queued"]) == 1


class Model(FakeMessagesListChatModel):
    def bind_tools(self, tools, **kwargs):
        return self


@pytest.mark.asyncio
@pytest.mark.parametrize("table_id", ["migration", "m/igration"])
async def test_repair_targets_allow_slashes_in_column_names(dispatch, table_id, monkeypatch):
    from searchos.agents.orchestrator import lifecycle

    workspace, scheduler = dispatch
    monkeypatch.setattr(lifecycle, "_ctx", queue._ctx)
    state = workspace.load_state()
    state.coverage_map.add_table(
        table_id, ["Requirement", "API/Behavior"],
        primary_key=["Requirement"], entities=[row_key(["M1"]), row_key(["M2"])],
    )
    workspace.save_state(state)
    queue._ctx.repair_target_allowlist = {cell_key(table_id, row_key(["M1"]), "API/Behavior")}
    result = json.loads(await queue.enqueue_tasks.ainvoke({"items": [
        {
            "agent_type": "search_agent", "task": "Verify the selected API behavior.",
            "target_table": table_id, "target_cells": [{"table_id": table_id, "key": [row], "attribute": "API/Behavior"}],
        }
        for row in ("M1", "M2")
    ]}))
    assert len(result["queued"]) == len(result["rejected"]) == 1
    assert not result["errors"]
    assert "outside repair allowlist" in result["rejected"][0]["reason"]
    stored = workspace.load_state().frontier.questions
    assert len(stored) == 1 and stored[0].target_cells == [cell_key(table_id, row_key(["M1"]), "API/Behavior")]
    scheduler.allow_tasks.assert_called_once_with(result["queued"])


@pytest.mark.asyncio
async def test_graph_enqueues_multiline_brief_without_a_table(dispatch):
    workspace, scheduler = dispatch
    arguments = json.loads(json.dumps({"items": [task()]}))
    graph = create_search_agent_graph(
        model=Model(responses=[
            AIMessage(content="", tool_calls=[{
                "name": "enqueue_tasks", "args": arguments, "id": "enqueue",
            }]),
            AIMessage(content="已派发。"),
        ]),
        tools=[queue.enqueue_tasks],
    )
    result = await graph.ainvoke(
        {"messages": [("user", "研究异步保存的失败语义")]},
        {"configurable": {"thread_id": "native-items"}},
    )
    receipt = next(m for m in result["messages"] if isinstance(m, ToolMessage))
    payload = json.loads(str(receipt.content))
    assert len(payload["queued"]) == 1
    assert not payload["errors"] and not payload["rejected"]
    state = workspace.load_state()
    assert not state.coverage_map.tables
    assert state.frontier.questions[0].task_prompt == BRIEF
    assert state.frontier.questions[0].table_id == ""
    scheduler.allow_tasks.assert_called_once_with(payload["queued"])
    scheduler.tick.assert_awaited_once()


@pytest.mark.asyncio
async def test_task_text_preserves_quotes_code_unicode_and_control_characters(dispatch):
    workspace, _ = dispatch
    brief = '  核查 "success"。\r\n\t保存失败\n代码：/\\w+/.test(name); C:\\temp\\file\n  '
    arguments = {"items": [task(brief)]}
    result = json.loads(await queue.enqueue_tasks.ainvoke(arguments))
    assert result["queued"]
    assert workspace.load_state().frontier.questions[0].task_prompt == brief


@pytest.mark.asyncio
@pytest.mark.parametrize("arguments,path", [
    ({}, "items"),
    ({"items": []}, "items"),
    ({"items": None}, "items"),
    ({"items": json.dumps([task()])}, "items"),
    ({"items": [5]}, "items.0"),
    ({"items": [{"task": "missing role"}]}, "items.0.agent_type"),
    ({"items": [{"agent_type": "search_agent"}]}, "items.0.task"),
    ({"items_json": json.dumps([task()])}, "items_json"),
    ({"items": [task()], "items_json": "[]"}, "items_json"),
])
async def test_invalid_payload_never_enqueues(dispatch, arguments, path):
    workspace, scheduler = dispatch
    result = json.loads(await queue.enqueue_tasks.ainvoke(arguments))
    assert result["error"] == "invalid task arguments"
    assert path in {error["path"] for error in result["errors"]}
    assert result["queued"] == []
    assert not workspace.load_state().frontier.questions
    scheduler.tick.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("field,value", [
    ("task", " \n\t"),
    ("task", {"prompt": "not text"}),
    ("task", 123),
    ("agent_type", "unknown_agent"),
    ("result_mode", "findings"),
    ("result_mode", "table"),
    ("priority", "high"),
    ("priority", True),
    ("priority", -0.1),
    ("priority", 1.1),
    ("priority", float("nan")),
    ("priority", float("inf")),
    ("max_searches", "5"),
    ("max_searches", True),
    ("max_searches", 0),
    ("max_searches", 1.5),
    ("blocked_by", "task-a,task-b"),
    ("blocked_by", [123]),
    ("skills", ["skill-a"]),
    ("id", "old-task-name"),
    ("parent_id", "parent"),
    ("depth", 0),
    ("task_id", "  "),
    ("target_table", {}),
    ("target_cells", "Alpha.Credits"),
    ("target_cells", ["Alpha"]),
    ("target_cells", ["Alpha."]),
    ("target_cells", [".Credits"]),
    ("kind", "search"),
    ("text", "old alias"),
    ("table_id", "old alias"),
    ("created_by", "user"),
])
async def test_invalid_item_rejects_entire_batch_before_mutation(dispatch, field, value):
    workspace, scheduler = dispatch
    payload = {"items": [task("Valid first item"), {**task(), field: value}]}
    result = json.loads(await queue.enqueue_tasks.ainvoke(payload))
    assert result["error"] == "invalid task arguments"
    assert any(error["path"].startswith(f"items.1.{field}") for error in result["errors"])
    assert result["queued"] == []
    assert not workspace.load_state().frontier.questions
    scheduler.tick.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("ceiling,expected", [(3, 3), (0, 1)])
async def test_valid_numeric_arguments_keep_priority_and_runtime_budget_limit(
    dispatch, monkeypatch, ceiling, expected,
):
    workspace, _ = dispatch
    monkeypatch.setattr(settings, "max_searches_per_sub_agent_ceiling", ceiling)
    result = json.loads(await queue.enqueue_tasks.ainvoke({
        "items": [{**task(), "priority": 0, "max_searches": 10}],
    }))
    assert result["queued"]
    saved = workspace.load_state().frontier.questions[0]
    assert saved.priority == 0
    assert saved.max_searches == expected


@pytest.mark.asyncio
async def test_graph_can_correct_validation_error_and_dispatch_once(dispatch):
    workspace, scheduler = dispatch
    graph = create_search_agent_graph(
        model=Model(responses=[
            AIMessage(content="", tool_calls=[{
                "name": "enqueue_tasks", "args": {"items": [{**task(), "priority": "high"}]},
                "id": "invalid",
            }]),
            AIMessage(content="", tool_calls=[{
                "name": "enqueue_tasks", "args": {"items": [task()]}, "id": "corrected",
            }]),
            AIMessage(content="已派发。"),
        ]),
        tools=[queue.enqueue_tasks],
    )
    result = await graph.ainvoke(
        {"messages": [("user", "研究异步保存的失败语义")]},
        {"configurable": {"thread_id": "correct-arguments"}},
    )
    receipts = [m for m in result["messages"] if isinstance(m, ToolMessage)]
    assert receipts[0].status == "error"
    assert json.loads(str(receipts[0].content))["errors"][0]["path"] == "items.0.priority"
    assert receipts[1].status == "success"
    assert len(workspace.load_state().frontier.questions) == 1
    scheduler.tick.assert_awaited_once()


def test_model_tool_schema_defines_item_fields_and_constraints():
    schema = convert_to_openai_tool(queue.enqueue_tasks)["function"]["parameters"]
    assert set(schema["properties"]) == {"items"}
    assert schema["required"] == ["items"]
    assert queue.enqueue_tasks.args_schema.model_json_schema()["additionalProperties"] is False
    array = schema["properties"]["items"]
    assert array["type"] == "array" and array["minItems"] == 1
    item = array["items"]
    assert set(item["required"]) == {"agent_type", "task"}
    assert item["additionalProperties"] is False
    assert set(item["properties"]) == {
        "agent_type", "task", "task_id", "agent_id", "priority", "blocked_by",
        "target_table", "target_cells", "max_searches",
    }
    assert item["properties"]["priority"]["minimum"] == 0
    assert item["properties"]["priority"]["maximum"] == 1
    assert all(field.get("description") for field in item["properties"].values())
