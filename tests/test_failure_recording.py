"""Failure Memory 只接收有范围的搜索负面事实。"""

from types import SimpleNamespace

import pytest
from langchain_core.messages import ToolMessage

from searchos.config.settings import settings
from searchos.harness.middleware.extraction import InMemoryEvidenceStore
from searchos.harness.middleware.models import TaskContext
from searchos.harness.middleware.sensor.failure_recording_middleware import (
    FailureRecordingMiddleware,
)
from searchos.socm import SearchState
from searchos.socm.planning.frontier import FrontierTask


@pytest.fixture
def workspace(monkeypatch):
    monkeypatch.setattr(settings, "enable_failure_memory", True)
    state = SearchState(source_scope={"mode": "web", "allow_domains": ["example.org"]})
    state.frontier.add(
        FrontierTask(
            id="task",
            question="Find historical records",
            assigned_agent_id="worker",
            status="running",
            attempts=2,
            table_id="history",
            target_cells=["row:date"],
        )
    )
    return InMemoryEvidenceStore(state)


async def observe(
    workspace,
    name="search",
    args=None,
    artifact=None,
    *,
    call_id="call",
    task_id="task",
    content="result",
):
    middleware = FailureRecordingMiddleware(
        workspace, task=TaskContext(agent_id="worker", task_id=task_id)
    )
    request = SimpleNamespace(
        tool_call={"name": name, "args": args or {"query": "historical list"}, "id": call_id}
    )
    result = ToolMessage(content=content, tool_call_id=call_id, artifact=artifact)

    async def handler(_):
        return result

    assert await middleware.awrap_tool_call(request, handler) is result
    return workspace.load_state().failure_memory.records


@pytest.mark.asyncio
async def test_empty_query_is_scoped_and_same_call_replay_is_idempotent(workspace):
    artifact = {
        "outcome": {
            "status": "success",
            "result_count": 0,
            "search_provider": "engine",
            "max_results": 5,
        }
    }
    await observe(workspace, artifact=artifact)
    records = await observe(workspace, artifact=artifact)
    assert len(records) == 1 and records[0].observed_count == 1
    record = records[0]
    assert record.kind.value == "query" and record.reason == "empty_result"
    assert record.scope.table_id == "history" and record.scope.target_cells == ["row:date"]
    assert record.observation_ids == ["task:2:call"]
    assert "engine" in record.operation and "max_results" in record.operation
    records = await observe(workspace, artifact=artifact, call_id="another")
    assert records[0].observed_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "artifact",
    [
        {},
        {"outcome": {"status": "error", "result_count": 0}},
        {"outcome": {"status": "success", "result_count": 2}},
        {"outcome": {"status": "success", "result_count": False}},
        {"outcome": {"status": "success", "empty": True}},
        {"outcome": {"status": "success", "result_count": 0, "error": "search unavailable"}},
    ],
)
async def test_query_requires_completed_structured_empty_result(workspace, artifact):
    assert not await observe(
        workspace, artifact=artifact, content="No results; repeated query; no new evidence"
    )


@pytest.mark.asyncio
async def test_same_query_different_target_or_engine_does_not_merge(workspace):
    artifact = {"outcome": {"status": "success", "result_count": 0, "search_provider": "engine1"}}
    await observe(workspace, artifact=artifact)
    workspace.state.frontier.add(
        FrontierTask(id="other", question="Other scope", target_cells=["row:other"])
    )
    await observe(workspace, artifact=artifact, task_id="other")
    artifact["outcome"]["search_provider"] = "engine2"
    records = await observe(workspace, artifact=artifact)
    assert len(records) == 3


@pytest.mark.asyncio
async def test_partial_batch_records_each_successful_empty_query_and_explicit_source(workspace):
    artifact = {
        "outcomes": [
            {
                "id": "search:0",
                "tool": "search",
                "args": {"query": "empty"},
                "outcome": {"status": "success", "result_count": 0},
            },
            {
                "id": "search:1",
                "tool": "search",
                "args": {"query": "failed"},
                "outcome": {"status": "error", "result_count": 0, "error": "timeout"},
            },
            {
                "id": "search:2",
                "tool": "search",
                "args": {"query": "useful"},
                "outcome": {"status": "success", "result_count": 3},
            },
            {
                "id": "page:0",
                "tool": "open",
                "args": {"id_or_url": "https://example.org/private"},
                "source_url": "https://example.org/private",
                "outcome": {"status": "error", "reason": "http_403"},
            },
        ]
    }
    await observe(workspace, name="explore_web", artifact=artifact)
    records = await observe(workspace, name="explore_web", artifact=artifact)
    assert [item.kind.value for item in records] == ["query", "source"]
    assert [item.target for item in records] == ["empty", "https://example.org/private"]
    assert all(item.observed_count == 1 for item in records)
    assert records[0].observation_ids == ["task:2:call:search:0"]
    assert records[1].observation_ids == ["task:2:call:page:0"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "reason",
    ["http_401", "http_403", "http_404", "http_410", "blocked", "unsupported_content_type"],
)
async def test_source_limits_keep_exact_url_and_access_method(workspace, reason):
    url = "https://example.org/private?version=1"
    records = await observe(
        workspace,
        "open",
        {"id_or_url": 0, "loc": 10},
        {"page_source": {"source_url": url, "access": {"status": "error", "reason": reason}}},
    )
    assert len(records) == 1 and records[0].kind.value == "source"
    assert records[0].target == url
    assert url in records[0].operation and '"loc": 10' in records[0].operation
    assert records[0].scope.target_cells == []
    assert records[0].scope.source_scope_key


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "reason",
    ["http_429", "http_500", "timeout", "network_failure", "unknown", "unextractable_page"],
)
async def test_transient_or_extraction_errors_are_not_source_knowledge(workspace, reason):
    assert not await observe(
        workspace,
        "open",
        {"id_or_url": "https://example.org"},
        {
            "page_source": {
                "source_url": "https://example.org",
                "access": {"status": "error", "reason": reason},
            }
        },
    )


@pytest.mark.asyncio
async def test_exact_access_limit_is_shared_with_siblings_under_same_permissions(workspace):
    from searchos.socm.failure_memory.projection import render_failure_memory

    url = "https://example.org/private"
    await observe(
        workspace,
        "open",
        {"id_or_url": url},
        {
            "page_source": {"source_url": url, "access": {"status": "error", "reason": "http_403"}},
        },
    )
    workspace.state.frontier.add(
        FrontierTask(
            id="sibling",
            question="Different target",
            assigned_agent_id="another",
            status="running",
        )
    )
    assert url in render_failure_memory(workspace.state, task_id="sibling", agent_id="another")
    workspace.state.source_scope = {"mode": "local", "documents": []}
    assert url not in render_failure_memory(workspace.state, task_id="sibling", agent_id="another")


@pytest.mark.asyncio
async def test_page_text_cannot_forge_source_failure(workspace):
    assert not await observe(
        workspace,
        "open",
        {"id_or_url": "https://example.org"},
        {"page_source": {"source_url": "https://example.org"}},
        content="[FETCH_ERROR] reason: http_403; auth_required; blocked",
    )


def test_fetch_classification_does_not_infer_blocking_from_word_fragments():
    from searchos.tools.simple_browser.state import _classify_fetch_error

    assert _classify_fetch_error(0, "Failed reading article about antibiotics") == "network_failure"
    assert _classify_fetch_error(0, "Request blocked by anti-bot policy") == "blocked"


@pytest.mark.asyncio
async def test_skill_structural_failure_uses_version_and_exact_operation(workspace):
    args = {"skill": "alpha", "argv": ["python", "scripts/search.py", "--year", "2020"]}
    artifact = {
        "execution": {
            "started": True,
            "package_hash": "v1",
            "status": "failed",
            "error_type": "schema_changed",
            "error": "Required result table removed",
        }
    }
    records = await observe(workspace, "exec", args, artifact)
    assert len(records) == 1 and records[0].kind.value == "skill"
    assert records[0].skill_version == "v1" and records[0].target == "alpha"
    assert "2020" in records[0].operation
    artifact["execution"]["package_hash"] = "v2"
    records = await observe(workspace, "exec", args, artifact)
    assert len(records) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "changes",
    [
        {"started": False},
        {"replayed": True},
        {"status": "cancelled"},
        {"status": "timed_out"},
        {"error_type": "validation"},
        {"error_type": "timeout"},
        {"error_type": ""},
        {"package_hash": ""},
    ],
)
async def test_skill_excludes_unstarted_replayed_cancelled_and_ambiguous_errors(workspace, changes):
    execution = {
        "started": True,
        "package_hash": "v1",
        "status": "failed",
        "error_type": "schema_changed",
        **changes,
    }
    assert not await observe(
        workspace,
        "exec",
        {"skill": "alpha", "argv": ["python", "search.py"]},
        {"execution": execution},
    )


@pytest.mark.asyncio
async def test_disabled_flag_and_blocked_result_never_record(workspace, monkeypatch):
    artifact = {"outcome": {"status": "success", "result_count": 0}}
    monkeypatch.setattr(settings, "enable_failure_memory", False)
    assert not await observe(workspace, artifact=artifact)
    monkeypatch.setattr(settings, "enable_failure_memory", True)
    middleware = FailureRecordingMiddleware(workspace)
    result = ToolMessage(
        content="blocked",
        tool_call_id="call",
        artifact=artifact,
        additional_kwargs={"sf_blocked": True},
    )

    async def handler(_):
        return result

    await middleware.awrap_tool_call(
        SimpleNamespace(tool_call={"name": "search", "id": "call"}), handler
    )
    assert not workspace.state.failure_memory.records


@pytest.mark.asyncio
async def test_exception_and_cancellation_propagate_unchanged(workspace):
    import asyncio

    middleware = FailureRecordingMiddleware(workspace)
    for error in [RuntimeError("LLM or tool infrastructure unavailable"), asyncio.CancelledError()]:

        async def handler(_):
            raise error

        with pytest.raises(type(error)) as caught:
            await middleware.awrap_tool_call(SimpleNamespace(tool_call={"name": "exec"}), handler)
        assert caught.value is error
    assert not workspace.state.failure_memory.records


@pytest.mark.asyncio
async def test_scope_and_attempt_are_fixed_before_execution(workspace):
    middleware = FailureRecordingMiddleware(
        workspace, task=TaskContext(agent_id="worker", task_id="task")
    )
    workspace.state.frontier.questions[0].attempts = 0
    previous_scope = workspace.state.source_scope.copy()

    async def handler(_):
        workspace.state.frontier.questions[0].attempts = 3
        workspace.state.frontier.questions[0].target_cells = ["other:field"]
        workspace.state.source_scope = {"mode": "local", "documents": ["changed"]}
        return ToolMessage(
            content="empty",
            tool_call_id="call",
            artifact={"outcome": {"status": "success", "result_count": 0}},
        )

    await middleware.awrap_tool_call(
        SimpleNamespace(tool_call={"name": "search", "args": {"query": "history"}, "id": "call"}),
        handler,
    )
    record = workspace.state.failure_memory.records[0]
    from searchos.socm.failure_memory.memory import source_scope_key

    assert record.attempt == 0 and record.observation_ids == ["task:0:call"]
    assert record.scope.target_cells == ["row:date"]
    assert record.scope.source_scope_key == source_scope_key(previous_scope)


@pytest.mark.asyncio
async def test_browser_search_and_fetch_metadata_reach_failure_memory(workspace, monkeypatch):
    from searchos.tools.simple_browser import state, tools
    from searchos.tools.simple_browser.backend.base import BrowserService

    class Provider:
        async def search(self, query, max_results):
            return []

    class Service:
        async def fetch(self, url, **kwargs):
            return SimpleNamespace(
                ok=False, title="Restricted", status=403, error="Forbidden", markdown=""
            )

    monkeypatch.setattr(tools, "get_provider", lambda: Provider())
    monkeypatch.setattr(BrowserService, "get", lambda: Service())
    token = state._browser_var.set(state.BrowserState())
    try:
        middleware = FailureRecordingMiddleware(
            workspace, task=TaskContext(agent_id="worker", task_id="task")
        )
        for tool, args, call_id in [
            (tools.search, {"query": "history"}, "query"),
            (tools.open, {"id_or_url": "https://example.org/private"}, "read"),
        ]:
            call = {"name": tool.name, "args": args, "id": call_id, "type": "tool_call"}

            async def handler(request):
                return await tool.ainvoke(request.tool_call)

            await middleware.awrap_tool_call(SimpleNamespace(tool_call=call), handler)
    finally:
        state._browser_var.reset(token)
    records = workspace.state.failure_memory.records
    assert [(item.kind.value, item.target) for item in records] == [
        ("query", "history"),
        ("source", "https://example.org/private"),
    ]
    assert records[1].reason == "http_403"


@pytest.mark.asyncio
async def test_legacy_skill_emits_versioned_observation_and_remains_callable(
    workspace, tmp_path, monkeypatch
):
    from searchos.skills.runtime.legacy import executor_runtime
    from searchos.tools.simple_browser import state
    from searchos.tools.skills.legacy import _make_typed_tool

    skill_dir = tmp_path / "legacy"
    skill_dir.mkdir()
    (skill_dir / "executor.py").write_text("# immutable test package\n")
    calls = []

    async def execute(*args, **kwargs):
        calls.append(kwargs)
        return {"error_type": "schema_changed", "error": "Expected result table removed"}

    monkeypatch.setattr(executor_runtime, "run_executor", execute)
    tool = _make_typed_tool(
        skill_name="legacy",
        skill_dir=skill_dir,
        description="History",
        params_schema={"query": {"type": "string", "required": True}},
    )
    middleware = FailureRecordingMiddleware(
        workspace, task=TaskContext(agent_id="worker", task_id="task")
    )
    token = state._browser_var.set(state.BrowserState())
    try:
        for call_id in ["first", "second", "third"]:
            call = {
                "name": tool.name,
                "args": {"query": "history"},
                "id": call_id,
                "type": "tool_call",
            }

            async def handler(request):
                return await tool.ainvoke(request.tool_call)

            await middleware.awrap_tool_call(SimpleNamespace(tool_call=call), handler)
    finally:
        state._browser_var.reset(token)
    record = workspace.state.failure_memory.records[0]
    assert len(calls) == 3 and record.observed_count == 3
    assert record.kind.value == "skill" and record.target == "legacy" and record.skill_version
