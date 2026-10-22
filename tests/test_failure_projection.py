"""失败记忆在模型边界更新，并按任务与来源权限隔离。"""

import json
import time
from types import SimpleNamespace

import pytest
from langgraph.checkpoint.memory import MemorySaver

from searchos.harness.middleware.context.socm_middleware import SOCMContextMiddleware
from searchos.harness.middleware.extraction import InMemoryEvidenceStore
from searchos.harness.middleware.models import TaskContext
from searchos.socm import FrontierTask, SearchState
from searchos.socm.failure_memory.memory import record_failure, scope_for_task, source_scope_key
from searchos.socm.failure_memory.models import FailureMemory, FailureScope
from searchos.socm.failure_memory.projection import render_failure_memory
from tests.test_socm_persistence import graph_for, snapshots, turn


def task_state(*, schema=True):
    state = SearchState()
    if schema:
        state.coverage_map.add_table(
            "t", ["Name", "Value"], primary_key=["Name"], entities=["A", "B"]
        )
        state.coverage_map.add_table(
            "other", ["Name", "Value"], primary_key=["Name"], entities=["A"]
        )
    state.frontier.add(
        FrontierTask(
            id="current", question="Find A", assigned_agent_id="reader", status="running",
            table_id="t" if schema else "", target_cells=["t/A.Value"] if schema else [],
        )
    )
    return state


def remember(state, *, kind="query", target="unproductive query", scope=None, **kwargs):
    return state.failure_memory.record(
        FailureMemory(
            kind=kind, target=target, reason="no_relevant_result",
            what_failed=f"Observed limit for {target}",
            scope=scope or scope_for_task(state, "current", "reader"), **kwargs,
        )
    )


def project(state, **kwargs):
    return render_failure_memory(state, task_id="current", agent_id="reader", **kwargs)


@pytest.mark.asyncio
async def test_new_failure_reaches_next_model_call_and_reuses_checkpoint_message():
    ws, checkpoint = InMemoryEvidenceStore(task_state()), MemorySaver()
    graph, model = graph_for(ws, checkpointer=checkpoint)
    _, writes = await turn(graph)
    assert len(writes) == 1
    assert "Search failure memory" not in writes[0].content

    stored = record_failure(
        ws,
        FailureMemory(kind="query", target="failed exact query", reason="empty_result",
                      what_failed="The query returned no candidates.", task_id="current",
                      agent_id="reader", observation_ids=["call-1"]),
    )
    assert stored is not None
    history, writes = await turn(graph)
    assert len(writes) == len(snapshots(history)) == 1
    assert writes[0].id == "socm-current"
    assert "failed exact query" in snapshots(model.received[-1])[0].content

    restored_ws = InMemoryEvidenceStore(SearchState.model_validate_json(ws.state.model_dump_json()))
    graph, model = graph_for(restored_ws, checkpointer=checkpoint)
    history, writes = await turn(graph)
    assert not writes
    assert len(snapshots(history)) == len(snapshots(model.received[-1])) == 1
    assert "sf_context_changed" not in snapshots(history)[0].additional_kwargs

    remember(restored_ws.state, target="unrelated B query", scope=FailureScope(
        table_id="t", target_cells=["t/B.Value"],
        source_scope_key=source_scope_key(restored_ws.state.source_scope),
    ))
    _, writes = await turn(graph)
    assert not writes


def test_reused_agent_does_not_inherit_previous_task_memory():
    state = task_state(schema=False)
    remember(state, target="old task query")
    assert "old task query" in project(state)
    state.frontier.questions[0].status = "completed"
    state.frontier.add(FrontierTask(
        id="next", question="Find B", assigned_agent_id="reader", status="running",
    ))
    remember(state, kind="source", target="shared login restriction", scope=FailureScope(
        source_scope_key=source_scope_key(state.source_scope),
    ))
    text = render_failure_memory(state, task_id="next", agent_id="reader")
    assert "old task query" not in text
    assert "shared login restriction" in text
    text = render_failure_memory(state, agent_id="reader")
    assert "old task query" not in text


def test_source_permission_changes_hide_even_shared_memories():
    state = task_state()
    state.source_scope = {"web": True, "local": False}
    remember(state, kind="source", target="private source", scope=FailureScope(
        source_scope_key=source_scope_key(state.source_scope),
    ))
    assert "private source" in project(state)
    state.source_scope = {"web": False, "local": True}
    assert project(state) == ""
    assert render_failure_memory(state, view="overview") == ""


def test_cell_and_entity_matches_preserve_table_and_exact_names():
    state = task_state()
    permission = source_scope_key(state.source_scope)
    remember(state, target="matching short cell", scope=FailureScope(
        table_id="t", target_cells=["A.Value"], source_scope_key=permission,
    ))
    remember(state, target="wrong table", scope=FailureScope(
        table_id="other", target_cells=["other/A.Value"], source_scope_key=permission,
    ))
    remember(state, target="wrong cell", scope=FailureScope(
        table_id="t", target_cells=["t/B.Value"], source_scope_key=permission,
    ))
    remember(state, kind="path", target="matching entity", scope=FailureScope(
        table_id="t", entities=["A"], source_scope_key=permission,
    ))
    remember(state, kind="path", target="entity substring", scope=FailureScope(
        table_id="t", entities=["Find A"], source_scope_key=permission,
    ))
    text = project(state)
    assert "matching short cell" in text and "matching entity" in text
    assert "wrong table" not in text and "wrong cell" not in text
    assert "entity substring" not in text


def test_unscoped_query_and_unknown_permission_never_broadcast():
    state = task_state()
    remember(state, target="unscoped query", scope=FailureScope(
        source_scope_key=source_scope_key(state.source_scope),
    ))
    remember(state, kind="source", target="unknown permission", scope=FailureScope())
    assert project(state) == ""


@pytest.mark.parametrize("view", ["task", "overview", "writing"])
def test_relevant_failure_can_trigger_projection_without_schema(view):
    state = task_state(schema=False)
    remember(state, kind="path", target="metadata route")
    middleware = SOCMContextMiddleware(
        SimpleNamespace(load_state=lambda: state),
        task=TaskContext(agent_id="reader", task_id="current"), view=view,
    )
    assert "Search failure memory" in middleware.render()
    assert "metadata route" in middleware.render()


def test_ttl_superseded_limit_and_refresh(monkeypatch):
    from searchos.config.settings import settings

    state = task_state()
    now = time.time()
    monkeypatch.setattr(settings, "failure_memory_decay_seconds", 100)
    monkeypatch.setattr(settings, "failure_memory_max_inject", 2)
    remember(state, target="expired", created_at=now - 101)
    remember(state, target="superseded", created_at=now, superseded=True)
    remember(state, target="oldest visible", created_at=now - 40)
    remember(state, target="recent", created_at=now - 20)
    remember(state, target="refreshed", created_at=now - 200, last_seen=now)
    text = project(state)
    assert "recent" in text and "refreshed" in text
    assert "expired" not in text and "superseded" not in text and "oldest visible" not in text
    monkeypatch.setattr(settings, "failure_memory_max_inject", 0)
    assert project(state) == ""


def test_overview_aggregates_and_writer_hides_query_trace():
    state = task_state()
    remember(state, target="raw query trace")
    remember(state, kind="source", target="unavailable archive")
    remember(state, kind="skill", target="parser capability")
    remember(state, kind="path", target="current ranking route")
    remember(state, kind="path", target="other table route", scope=FailureScope(
        table_id="other", target_cells=["other/A.Value"],
        source_scope_key=source_scope_key(state.source_scope),
    ))
    overview = render_failure_memory(state, view="overview")
    assert "raw query trace" in overview and "other table route" in overview
    writing = render_failure_memory(state, target_table="t", view="writing")
    assert "raw query trace" not in writing and "other table route" not in writing
    assert all(target in writing for target in (
        "unavailable archive", "parser capability", "current ranking route",
    ))


@pytest.mark.parametrize("view", ["task", "overview", "writing"])
def test_post_mortem_inference_keeps_record_confidence_without_guidance(view):
    state = task_state()
    remember(state, kind="path", target="archive route", source="post_mortem", confidence="low")

    text = project(state, view=view)

    assert "post_mortem inference; confidence=low" in text
    assert "observed limits" not in text and "Conditional guidance" not in text


def test_writer_keeps_source_object_access_conditions_and_skill_version_without_query_trace():
    state = task_state()
    remember(
        state, kind="source", target="https://example.org/archive", confidence="high",
        operation=json.dumps(["open", {"url": "https://example.org/archive", "loc": 10}]),
    )
    remember(
        state, kind="source", target="https://example.org/annual", source="post_mortem",
        operation=json.dumps([
            {"tool": "search", "arguments": {"query": "raw source search trace"}},
            {"tool": "open", "arguments": {"id_or_url": "https://example.org/annual", "loc": 20}},
        ]),
    )
    remember(
        state, kind="skill", target="annual-parser", skill_version="package-v1",
        operation=json.dumps(["exec", {"argv": ["python", "run.py", "raw skill query trace"]}]),
    )
    remember(
        state, kind="path", target="historical archive route", source="post_mortem",
        operation=json.dumps([{"tool": "search", "arguments": {"query": "raw path query trace"}}]),
    )

    text = render_failure_memory(state, view="writing")

    assert "https://example.org/archive" in text and "https://example.org/annual" in text
    assert '"open", {"loc": 10}' in text and '"open", {"loc": 20}' in text
    assert "annual-parser" in text and "skill_version=package-v1" in text
    assert "tool observation; confidence=high" in text
    assert "post_mortem inference; confidence=low" in text
    assert "raw source search trace" not in text
    assert "raw skill query trace" not in text and "raw path query trace" not in text
