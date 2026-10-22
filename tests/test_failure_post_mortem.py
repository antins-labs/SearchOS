"""搜索复盘只接受实际调用，范围与归属由宿主确定。"""

import asyncio
import json
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, ToolMessage

from searchos.socm.failure_memory import (
    FailureMemory,
    FailureScope,
    FailureStore,
    post_mortem,
    scope_for_task,
)


class Workspace:
    def __init__(self):
        self.state = SimpleNamespace(
            source_scope={"mode": "web"},
            failure_memory=FailureStore(),
            frontier=SimpleNamespace(
                questions=[
                    SimpleNamespace(
                        id="task",
                        assigned_agent_id="agent",
                        status="running",
                        attempts=2,
                        question="Find Acme's founding year",
                        table_id="companies",
                        target_cells=["Acme.founded"],
                    )
                ]
            ),
            coverage_map=SimpleNamespace(resolve_cell_reference=lambda cell, **_: cell),
        )

    def load_state(self):
        return self.state

    def atomic_update_state(self, update):
        self.state = update(self.state)


class Model:
    def __init__(self, output):
        self.output = output
        self.inputs = []

    async def ainvoke(self, prompt):
        self.inputs.append(json.loads(prompt.split("\nInput:\n", 1)[1]))
        return SimpleNamespace(content=json.dumps(self.output))


def exchange(identifier, name, args, content="No target information", **kwargs):
    return [
        AIMessage(content="", tool_calls=[{"id": identifier, "name": name, "args": args}]),
        ToolMessage(content=content, tool_call_id=identifier, **kwargs),
    ]


def record(kind="query", target="Acme founding year", ids=None, **kwargs):
    return {
        "kind": kind,
        "target": target,
        "reason": "target_not_covered",
        "what_failed": "Inspected results did not cover Acme's founding year.",
        "supporting_call_ids": ids or ["search"],
        **kwargs,
    }


async def review(ws, model, messages, report=None):
    return await post_mortem.run_post_mortem(
        workspace=ws,
        model=model,
        agent_id="agent",
        task_id="task",
        attempt=2,
        report=report or SimpleNamespace(result="Unresolved founding year"),
        messages=messages,
    )


@pytest.fixture(autouse=True)
def enable_memory(monkeypatch):
    from searchos.config.settings import settings

    monkeypatch.setattr(settings, "enable_failure_memory", True)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kind,target,support",
    [
        ("query", "Acme founding year", ["search"]),
        ("source", "https://example.org/current", ["read"]),
        ("skill", "company-history", ["skill"]),
        ("path", "Infer founding year from product launches", ["search", "read"]),
    ],
)
async def test_four_kinds_keep_host_scope_and_actual_call_identity(kind, target, support):
    ws = Workspace()
    messages = [
        *exchange(
            "search",
            "search",
            {"query": "Acme founding year"},
            artifact={"outcome": {"status": "success", "result_count": 0}},
        ),
        *exchange(
            "read",
            "open",
            {"id_or_url": "https://example.org/current"},
            artifact={"page_source": {"source_url": "https://example.org/current"}},
        ),
        *exchange(
            "skill",
            "exec",
            {"skill": "company-history", "argv": ["python", "run.py"]},
            artifact={
                "execution": {
                    "started": True,
                    "package_hash": "version-2",
                    "status": "failed",
                    "error_type": "unsupported_operation",
                }
            },
        ),
    ]
    model = Model(
        [
            record(
                kind,
                target,
                support,
                scope={"global": True},
                task_id="foreign",
                confidence="high",
                skill_version="forged",
            )
        ]
    )
    memories = await review(ws, model, messages)

    assert len(memories) == 1
    memory = memories[0]
    assert memory.task_id == "task" and memory.agent_id == "agent" and memory.attempt == 2
    assert memory.scope.table_id == "companies" and memory.scope.target_cells == ["Acme.founded"]
    assert memory.observation_ids == [f"task:2:{identifier}" for identifier in support]
    assert memory.confidence == "low"
    assert memory.skill_version == ("version-2" if kind == "skill" else "")
    assert [call["id"] for call in model.inputs[0]["tool_trace"]] == ["search", "read", "skill"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "proposal",
    [
        record(ids=["invented"]),
        record(target="invented query"),
        record("source", "example.org", ["search"]),
        record("skill", "company-history", ["search"]),
        record("path", "Infer founding year", ["search"]),
        record(reason="invalid_arguments"),
        record(reason=" "),
        record(what_failed=""),
        record(kind="llm"),
        record(supporting_call_ids="search"),
    ],
)
async def test_untraceable_or_out_of_scope_proposals_are_discarded(proposal):
    ws = Workspace()
    assert (
        await review(
            ws,
            Model([proposal]),
            exchange(
                "search",
                "search",
                {"query": "Acme founding year"},
            ),
        )
        == []
    )
    assert not ws.state.failure_memory.records


@pytest.mark.asyncio
async def test_intended_blocked_replayed_or_not_started_calls_are_not_evidence():
    messages = [
        AIMessage(
            content="The source is blocked",
            tool_calls=[
                {
                    "id": "intent",
                    "name": "open",
                    "args": {"id_or_url": "https://example.org"},
                }
            ],
        )
    ]
    for identifier, metadata in (
        ("blocked", {"additional_kwargs": {"sf_blocked": True}}),
        ("not-started", {"artifact": {"execution": {"started": False}}}),
        ("replayed", {"artifact": {"execution": {"started": True, "replayed": True}}}),
    ):
        messages.extend(exchange(identifier, "exec", {"skill": "company-history"}, **metadata))
    messages.extend(
        exchange(
            "argument",
            "open",
            {"id_or_url": "https://example.org"},
            artifact={"outcome": {"code": "invalid_arguments"}},
        )
    )
    model = Model([record("source", "https://example.org", ["intent"])])
    assert await review(Workspace(), model, messages) == []
    assert not model.inputs


@pytest.mark.asyncio
async def test_direct_fact_is_not_recounted_by_semantic_paraphrase():
    ws = Workspace()
    ws.state.failure_memory.record(
        FailureMemory(
            kind="query",
            target="Acme founding year",
            reason="empty_result",
            what_failed="No search results",
            observation_ids=["task:2:search:0"],
            scope=scope_for_task(ws.state, "task", "agent"),
        )
    )
    assert (
        await review(
            ws,
            Model([record()]),
            exchange(
                "search",
                "search",
                {"query": "Acme founding year"},
                artifact={"outcome": {"status": "success", "result_count": 0}},
            ),
        )
        == []
    )
    assert len(ws.state.failure_memory.records) == 1
    assert ws.state.failure_memory.records[0].observed_count == 1


@pytest.mark.asyncio
async def test_post_mortem_replay_is_idempotent_and_new_path_can_use_known_facts():
    ws = Workspace()
    messages = [
        *exchange(
            "search",
            "search",
            {"query": "Acme founding year"},
            artifact={"outcome": {"status": "success", "result_count": 0}},
        ),
        *exchange("read", "open", {"id_or_url": "https://example.org/current"}),
    ]
    model = Model([record(), record("path", "Product launch route", ["search", "read"])])
    assert len(await review(ws, model, messages)) == 2
    assert await review(ws, model, messages) == []
    assert [item.observed_count for item in ws.state.failure_memory.records] == [1, 1]


@pytest.mark.asyncio
@pytest.mark.parametrize("content", ["invalid JSON", "{}", "[]"])
async def test_invalid_or_empty_model_output_is_best_effort(content):
    class RawModel:
        async def ainvoke(self, _):
            return SimpleNamespace(content=content)

    assert (
        await review(
            Workspace(),
            RawModel(),
            exchange(
                "search",
                "search",
                {"query": "Acme founding year"},
            ),
        )
        == []
    )


@pytest.mark.asyncio
async def test_model_timeout_is_best_effort_but_external_cancellation_propagates(monkeypatch):
    class Slow:
        async def ainvoke(self, _):
            await asyncio.Event().wait()

    messages = exchange(
        "search",
        "search",
        {"query": "Acme founding year"},
        artifact={"outcome": {"status": "success", "result_count": 0}},
    )
    monkeypatch.setattr(post_mortem, "POST_MORTEM_TIMEOUT_SECONDS", 0.01)
    assert await review(Workspace(), Slow(), messages) == []
    monkeypatch.setattr(post_mortem, "POST_MORTEM_TIMEOUT_SECONDS", 60)
    task = asyncio.create_task(review(Workspace(), Slow(), messages))
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_schedule_uses_search_signals_and_session_limit(monkeypatch):
    from searchos.config.settings import settings

    monkeypatch.setattr(settings, "max_post_mortems_per_session", 1)
    ws, model, pending, count = Workspace(), Model([]), [], [0]

    def schedule(messages, report):
        post_mortem.schedule_post_mortem(
            workspace=ws,
            model=model,
            pending_tasks=pending,
            count=count,
            agent_id="agent",
            task_id="task",
            attempt=2,
            report=report,
            messages=messages,
        )

    schedule([], SimpleNamespace(status="error", last_message="LLM request failed"))
    schedule(
        exchange("search", "search", {"query": "Acme founding year"}),
        SimpleNamespace(status="completed", cells_filled=[], evidence_nodes_added=0),
    )
    assert not pending and count == [0]
    schedule(
        exchange(
            "search",
            "search",
            {"query": "Acme founding year"},
            artifact={"outcome": {"status": "empty"}},
        ),
        SimpleNamespace(status="completed"),
    )
    schedule(
        exchange("search", "search", {"query": "Acme founding year"}),
        SimpleNamespace(status="completed", last_message="Founding year unresolved"),
    )
    assert len(pending) == 1 and count == [1]
    await asyncio.gather(*pending)


@pytest.mark.asyncio
async def test_schedule_freezes_scope_goal_and_tool_messages_before_reuse():
    ws, model, pending = Workspace(), Model([record()]), []
    messages = exchange(
        "search",
        "search",
        {"query": "Acme founding year"},
        artifact={"outcome": {"status": "success", "result_count": 0}},
    )
    post_mortem.schedule_post_mortem(
        workspace=ws,
        model=model,
        pending_tasks=pending,
        count=[0],
        agent_id="agent",
        task_id="task",
        attempt=2,
        report=SimpleNamespace(last_message="Founding year unresolved"),
        messages=messages,
    )
    task = ws.state.frontier.questions[0]
    task.table_id, task.target_cells, task.question = "other", ["Beta.revenue"], "A different goal"
    task.attempts = 3
    messages[0].tool_calls[0]["args"]["query"] = "A different query"
    await asyncio.gather(*pending)
    memory = ws.state.failure_memory.records[0]
    assert memory.attempt == 2 and memory.scope.table_id == "companies"
    assert memory.scope.target_cells == ["Acme.founded"]
    assert model.inputs[0]["target"] == "Find Acme's founding year"
    assert model.inputs[0]["tool_trace"][0]["arguments"]["query"] == "Acme founding year"


def test_trace_is_bounded_and_deduplicates_checkpoint_messages():
    messages = []
    for index in range(30):
        messages.extend(
            exchange(
                str(index),
                "open",
                {"id_or_url": f"https://example.org/{index}"},
                content="x" * 10000,
            )
        )
    messages.extend(messages[-2:])
    calls = post_mortem._trace_calls(messages)
    assert len(calls) <= 24 and calls[-1]["id"] == "29"
    assert len({call["id"] for call in calls}) == len(calls)
    assert len(json.dumps(calls)) < 26000


@pytest.mark.asyncio
async def test_existing_memories_only_include_current_scope_and_explicit_shared_limits():
    ws = Workspace()
    scope = scope_for_task(ws.state, "task", "agent")
    shared = FailureScope(source_scope_key=scope.source_scope_key)
    for target, kind, memory_scope, extras in [
        ("same", "query", scope, {}),
        ("shared-source", "source", shared, {}),
        ("shared-skill", "skill", shared, {}),
        ("unscoped-query", "query", shared, {}),
        (
            "other-permissions",
            "source",
            shared.model_copy(update={"source_scope_key": "other"}),
            {},
        ),
        ("other-task", "query", scope.model_copy(update={"task_id": "foreign"}), {}),
        ("other-cell", "query", scope.model_copy(update={"target_cells": ["Beta.founded"]}), {}),
        ("expired", "source", shared, {"created_at": 1, "last_seen": 1}),
        ("superseded", "source", shared, {"superseded": True}),
    ]:
        ws.state.failure_memory.record(
            FailureMemory(
                kind=kind,
                target=target,
                reason="observed_limit",
                what_failed=target,
                scope=memory_scope,
                **extras,
            )
        )
    model = Model([])
    await review(ws, model, exchange("search", "search", {"query": "Acme founding year"}))
    assert {item["target"] for item in model.inputs[0]["existing_memories"]} == {
        "same",
        "shared-source",
        "shared-skill",
    }


@pytest.mark.asyncio
async def test_schedule_filters_existing_memories_using_frozen_permissions():
    ws, model, pending = Workspace(), Model([]), []
    scope = scope_for_task(ws.state, "task", "agent")
    ws.state.failure_memory.record(
        FailureMemory(
            kind="source",
            target="old-access",
            reason="auth_required",
            what_failed="Old permission",
            scope=scope,
        )
    )
    post_mortem.schedule_post_mortem(
        workspace=ws,
        model=model,
        pending_tasks=pending,
        count=[0],
        agent_id="agent",
        task_id="task",
        attempt=2,
        report=SimpleNamespace(last_message="unresolved"),
        messages=exchange("search", "search", {"query": "Acme founding year"}),
    )
    ws.state.source_scope = {"mode": "local"}
    ws.state.failure_memory.record(
        FailureMemory(
            kind="source",
            target="new-access",
            reason="auth_required",
            what_failed="New permission",
            scope=scope_for_task(ws.state, "task", "agent"),
        )
    )
    await asyncio.gather(*pending)
    assert [item["target"] for item in model.inputs[0]["existing_memories"]] == ["old-access"]


@pytest.mark.asyncio
@pytest.mark.parametrize("tool", ["exec", "skill_company-history"])
@pytest.mark.parametrize("versions", [[None], [""], ["v1", "v2"], ["v1", None]])
async def test_skill_memory_requires_one_known_version_for_its_actual_target(tool, versions):
    messages = []
    for index, version in enumerate(versions):
        messages.extend(
            exchange(
                f"s{index}",
                tool,
                {"skill": "company-history"},
                artifact={"execution": {"started": True, "package_hash": version}},
            )
        )
    assert (
        await review(
            Workspace(),
            Model(
                [
                    record(
                        "skill",
                        "company-history",
                        [f"s{index}" for index in range(len(versions))],
                    )
                ]
            ),
            messages,
        )
        == []
    )


@pytest.mark.asyncio
async def test_typed_skill_version_comes_only_from_target_execution():
    messages = [
        *exchange(
            "target",
            "skill_company-history",
            {},
            artifact={
                "execution": {
                    "started": True,
                    "package_hash": "actual-version",
                    "status": "failed",
                    "error_type": "unsupported_operation",
                },
            },
        ),
        *exchange(
            "other",
            "exec",
            {"skill": "other"},
            artifact={
                "execution": {"started": True, "package_hash": "unrelated-version"},
            },
        ),
    ]
    memories = await review(
        Workspace(),
        Model(
            [
                record("skill", "company-history", ["target", "other"], skill_version="forged"),
            ]
        ),
        messages,
    )
    assert len(memories) == 1 and memories[0].skill_version == "actual-version"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "detail,status",
    [
        ({"status": "success", "result_count": 2}, "success"),
        ({"status": "error", "result_count": 0}, "success"),
        ({"status": "success", "result_count": 0, "error": "provider failed"}, "success"),
        ({"status": "success", "result_count": 0}, "error"),
        ({"status": "success", "result_count": False}, "success"),
        ({}, "success"),
        ({"page_source": {"source_url": "https://example.org/source"}}, "success"),
    ],
)
async def test_unread_candidates_and_request_errors_cannot_establish_query_failure(detail, status):
    messages = exchange(
        "search",
        "search",
        {"query": "Acme founding year"},
        status=status,
        artifact={"outcome": detail},
    )
    assert await review(Workspace(), Model([record()]), messages) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("candidate_source", ["results", "content"])
@pytest.mark.parametrize("related", [False, True])
async def test_query_semantic_failure_requires_reading_its_own_candidate(candidate_source, related):
    artifact = {"outcome": {"status": "success", "result_count": 1}}
    content = "Candidates returned"
    if candidate_source == "results":
        artifact["results"] = [{"url": "https://example.org/candidate"}]
    else:
        content = "[0] https://example.org/candidate\nCandidate title"
    messages = [
        *exchange(
            "search", "search", {"query": "Acme founding year"}, content=content, artifact=artifact
        ),
        *exchange(
            "read",
            "open",
            {"id_or_url": 0},
            artifact={
                "page_source": {
                    "source_url": "https://example.org/candidate"
                    if related
                    else "https://other.org/page",
                }
            },
        ),
    ]
    memories = await review(Workspace(), Model([record(ids=["search", "read"])]), messages)
    assert len(memories) == int(related)


@pytest.mark.asyncio
async def test_batch_query_cannot_borrow_neighbor_results_or_request_success():
    content = (
        "## Query 1: Acme founding year\nURL: https://example.org/acme\n"
        "## Query 2: Beta founding year\nURL: https://example.org/beta\n"
    )
    artifact = {
        "outcomes": [
            {
                "tool": "search",
                "args": {"query": "Acme founding year"},
                "outcome": {"status": "error", "result_count": 0},
            },
            {
                "tool": "search",
                "args": {"query": "Beta founding year"},
                "outcome": {"status": "success", "result_count": 1},
            },
        ]
    }
    messages = [
        *exchange(
            "batch",
            "explore_web",
            {
                "queries": ["Acme founding year", "Beta founding year"],
            },
            content=content,
            artifact=artifact,
        ),
        *exchange(
            "read",
            "open",
            {
                "id_or_url": "https://example.org/beta",
            },
            artifact={"page_source": {"source_url": "https://example.org/beta"}},
        ),
    ]
    model = Model([record(ids=["batch", "read"])])
    assert await review(Workspace(), model, messages) == []
    artifact["outcomes"][0]["outcome"] = {"status": "success", "result_count": 1}
    assert await review(Workspace(), model, messages) == []
    messages[-2].tool_calls[0]["args"]["id_or_url"] = "https://example.org/acme"
    messages[-1].artifact["page_source"]["source_url"] = "https://example.org/acme"
    assert len(await review(Workspace(), model, messages)) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case,expected",
    [
        ("unread", 0),
        ("unrelated", 0),
        ("related", 1),
        ("request_error", 0),
        ("repeated_empty", 0),
        ("zero_cells", 0),
    ],
)
async def test_path_needs_distinct_operations_and_a_linked_read_or_concrete_negative(
    case, expected
):
    detail = {"status": "success", "result_count": 1}
    messages = exchange(
        "search",
        "search",
        {"query": "Acme founding year"},
        content="[0] https://example.org/candidate",
        artifact={"outcome": detail},
    )
    second = exchange(
        "other", "search", {"query": "Acme product launch"}, artifact={"outcome": detail}
    )
    if case in {"related", "unrelated", "zero_cells"}:
        second = exchange(
            "other",
            "open",
            {
                "id_or_url": (
                    "https://example.org/candidate"
                    if case != "unrelated"
                    else "https://other.org/page"
                )
            },
            artifact={
                "page_source": {
                    "source_url": (
                        "https://example.org/candidate"
                        if case != "unrelated"
                        else "https://other.org/page"
                    )
                }
            },
        )
    elif case == "request_error":
        messages[-1].artifact["outcome"] = {"status": "error", "result_count": 0}
        second[-1].artifact["outcome"] = {"status": "error", "result_count": 0}
    elif case == "repeated_empty":
        messages[-1].artifact["outcome"] = {"status": "success", "result_count": 0}
        second = exchange(
            "other",
            "search",
            {"query": "Acme founding year"},
            artifact={"outcome": {"status": "success", "result_count": 0}},
        )
    proposal = record(
        "path",
        "Product launch route",
        ["search", "other"],
        reason="zero_cells" if case == "zero_cells" else "unsupported_premise",
    )
    assert len(await review(Workspace(), Model([proposal]), [*messages, *second])) == expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "artifact,status",
    [
        ({}, "success"),
        ({"outcome": {"status": "error", "reason": "timeout"}}, "error"),
        (
            {
                "page_source": {
                    "source_url": "https://example.org/source",
                    "access": {"status": "error", "reason": "network_error"},
                }
            },
            "success",
        ),
        (
            {
                "page_source": {"source_url": "https://example.org/source"},
                "outcome": {"status": "success", "error": "connection failed"},
            },
            "success",
        ),
    ],
)
async def test_model_cannot_relabel_source_timeout_or_unread_url_as_access_limit(artifact, status):
    messages = exchange(
        "read",
        "open",
        {"id_or_url": "https://example.org/source"},
        artifact=artifact,
        status=status,
        content="Error: connection timed out",
    )
    model = Model(
        [record("source", "https://example.org/source", ["read"], reason="auth_required")]
    )
    assert await review(Workspace(), model, messages) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("batch", [False, True])
async def test_source_access_limit_needs_structured_observation(batch):
    outcome = {"status": "error", "reason": "auth_required"}
    artifact = (
        {
            "outcomes": [
                {"tool": "open", "source_url": "https://example.org/source", "outcome": outcome}
            ]
        }
        if batch
        else {"outcome": outcome}
    )
    messages = exchange(
        "read",
        "explore_web" if batch else "open",
        {"queries": ["Acme"]}
        if batch
        else {
            "id_or_url": "https://example.org/source",
        },
        artifact=artifact,
    )
    memories = await review(
        Workspace(),
        Model(
            [
                record("source", "https://example.org/source", ["read"], reason="auth_required"),
            ]
        ),
        messages,
    )
    assert len(memories) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "execution",
    [
        {"status": "failed", "error_type": "timeout"},
        {"status": "failed", "error_type": "auth_required"},
        {"status": "failed", "error_type": "network_error"},
        {"status": "failed", "error_type": "invalid_arguments"},
        {"status": "failed", "error_type": "ValidationError"},
        {"status": "timed_out"},
        {"status": "cancelled"},
        {"status": "failed", "error_type": "parse_error", "timed_out": True},
        {"status": "failed", "exit_code": 1, "stderr": "Connection timed out"},
        {"status": "failed", "exit_code": 1, "stderr": "Invalid arguments: use --help"},
        {"status": "failed", "exit_code": 1, "stderr": "HTTP 401 authentication required"},
    ],
)
async def test_model_cannot_relabel_skill_transient_or_call_errors_as_capability_limits(execution):
    execution = {"started": True, "package_hash": "actual-version", **execution}
    memories = await review(
        Workspace(),
        Model(
            [
                record("skill", "company-history", ["skill"], reason="capability_unavailable"),
            ]
        ),
        exchange("skill", "exec", {"skill": "company-history"}, artifact={"execution": execution}),
    )
    assert memories == []


@pytest.mark.asyncio
async def test_untyped_cli_failure_can_use_actual_stderr_when_version_is_known():
    execution = {
        "started": True,
        "package_hash": "actual-version",
        "status": "failed",
        "exit_code": 1,
        "stderr": "ParserError: required table absent from response",
    }
    memories = await review(
        Workspace(),
        Model(
            [
                record("skill", "company-history", ["skill"], reason="schema_changed"),
            ]
        ),
        exchange("skill", "exec", {"skill": "company-history"}, artifact={"execution": execution}),
    )
    assert len(memories) == 1 and memories[0].skill_version == "actual-version"


@pytest.mark.asyncio
@pytest.mark.parametrize("reading", ["none", "unrelated", "related"])
async def test_successful_skill_needs_read_product_before_capability_judgment(reading):
    messages = exchange(
        "skill",
        "exec",
        {"skill": "company-history"},
        artifact={
            "execution": {
                "started": True,
                "package_hash": "actual-version",
                "status": "completed",
                "exit_code": 0,
                "page_url": "skill://execution/result.json",
            }
        },
    )
    ids = ["skill"]
    if reading != "none":
        url = "skill://execution/result.json" if reading == "related" else "https://other.org/page"
        messages.extend(
            exchange(
                "read", "open", {"id_or_url": url}, artifact={"page_source": {"source_url": url}}
            )
        )
        ids.append("read")
    memories = await review(
        Workspace(),
        Model(
            [
                record("skill", "company-history", ids, reason="historical_data_not_supported"),
            ]
        ),
        messages,
    )
    assert len(memories) == int(reading == "related")


@pytest.mark.asyncio
async def test_two_successful_empty_queries_trigger_path_review_without_report_hint():
    ws, pending = Workspace(), []
    model = Model(
        [
            record(
                "path",
                "Company history via current-product queries",
                ["q1", "q2"],
                what_failed="Two targeted queries returned no candidates.",
            )
        ]
    )
    messages = []
    for identifier, query in [("q1", "Acme founding year"), ("q2", "Acme first product")]:
        messages.extend(
            exchange(
                identifier,
                "search",
                {"query": query},
                artifact={"outcome": {"status": "success", "result_count": 0}},
            )
        )
    post_mortem.schedule_post_mortem(
        workspace=ws,
        model=model,
        pending_tasks=pending,
        count=[0],
        agent_id="agent",
        task_id="task",
        attempt=2,
        report=SimpleNamespace(status="completed"),
        messages=messages,
    )
    assert len(pending) == 1
    await asyncio.gather(*pending)
    assert len(ws.state.failure_memory.records) == 1
    assert ws.state.failure_memory.records[0].kind == "path"


def rendered_batch(rows, pages, *, budget=20000, queries=None):
    from searchos.tools.simple_browser.batch import _render_wave
    from searchos.util.tool_output_budget import tool_output_budget

    token = tool_output_budget.set(budget)
    try:
        content, artifact = _render_wave(rows, pages, "Explore wave")
    finally:
        tool_output_budget.reset(token)
    return exchange(
        "batch",
        "explore_web",
        {"queries": queries or [row[0] for row in rows]},
        content=content,
        artifact=artifact,
    )


@pytest.mark.asyncio
async def test_real_explore_producer_preserves_late_query_candidate_identity():
    from searchos.tools.simple_browser.render import PageContents
    from searchos.tools.simple_browser.search.base import SearchResult

    rows = [
        (
            "Unrelated catalog",
            [
                SearchResult(
                    url="https://example.org/catalog", snippet="irrelevant candidate " * 180
                )
            ],
            "",
        ),
        ("Acme founding year", [SearchResult(url="https://example.org/history")], ""),
    ]
    messages = rendered_batch(
        rows,
        [
            PageContents(
                url="https://example.org/history", text="This history covers product launches only."
            )
        ],
    )
    assert "## Query 2:" not in messages[-1].content[:1200]
    memories = await review(Workspace(), Model([record(ids=["batch"])]), messages)
    assert len(memories) == 1 and memories[0].kind == "query"


@pytest.mark.asyncio
async def test_real_explore_producer_counts_shown_search_and_read_as_path_operations():
    from searchos.tools.simple_browser.render import PageContents
    from searchos.tools.simple_browser.search.base import SearchResult

    rows = [("Acme founding year", [SearchResult(url="https://example.org/history")], "")]
    messages = rendered_batch(
        rows,
        [
            PageContents(
                url="https://example.org/history", text="Only current product launch dates appear."
            )
        ],
    )
    memories = await review(
        Workspace(),
        Model(
            [
                record(
                    "path",
                    "Find founding date through product announcements",
                    ["batch"],
                )
            ]
        ),
        messages,
    )
    assert len(memories) == 1 and memories[0].kind == "path"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case,expected",
    [
        ("two_empty", 1),
        ("repeated_empty", 0),
        ("requested_only", 0),
        ("hidden_page", 0),
        ("known_access_limit", 1),
    ],
)
async def test_real_explore_producer_only_counts_completed_shown_or_negative_children(
    case, expected
):
    from searchos.tools.simple_browser.render import PageContents
    from searchos.tools.simple_browser.search.base import SearchResult

    rows, pages, queries, budget = [("Acme founding year", [], "")], [], None, 20000
    if case == "two_empty":
        rows.append(("Acme first product", [], ""))
    elif case == "repeated_empty":
        rows.append(rows[0])
    elif case == "requested_only":
        queries = ["Acme founding year", "Acme first product"]
    else:
        rows = [("Acme founding year", [SearchResult(url="https://example.org/history")], "")]
        pages = [PageContents(url="https://example.org/history", text="History body " * 200)]
        budget = 20
        if case == "known_access_limit":
            pages[0].text = "[FETCH_ERROR] Authentication required"
            pages[0].metadata = {"access": {"status": "error", "reason": "auth_required"}}
    messages = rendered_batch(rows, pages, budget=budget, queries=queries)
    if budget == 20:
        assert messages[-1].artifact["pages"] == []
    memories = await review(
        Workspace(),
        Model(
            [
                record(
                    "path",
                    "Company history through targeted searches",
                    ["batch"],
                )
            ]
        ),
        messages,
    )
    assert len(memories) == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("read_candidate", [False, True])
async def test_real_search_producer_keeps_candidate_identity_past_trace_excerpt(
    monkeypatch, read_candidate
):
    from searchos.tools.simple_browser import tools
    from searchos.tools.simple_browser.search.base import SearchResult
    from searchos.tools.simple_browser.state import BrowserState

    class Provider:
        name = "test-search"

        async def search(self, query, max_results):
            return [
                SearchResult(url="https://example.org/catalog", snippet="Long catalog " * 250),
                SearchResult(url="https://example.org/history"),
            ]

    browser = BrowserState()
    monkeypatch.setattr(tools, "_get_browser", lambda: browser)
    monkeypatch.setattr(tools, "get_provider", lambda: Provider())
    monkeypatch.setattr(tools, "apply_source_controls", lambda results: results)
    call = {
        "type": "tool_call",
        "id": "search",
        "name": "search",
        "args": {"query": "Acme founding year"},
    }
    result = await tools.search.ainvoke(call)
    assert "https://example.org/history" not in result.content[:1200]
    messages = [
        AIMessage(content="", tool_calls=[{key: call[key] for key in ("id", "name", "args")}]),
        result,
    ]
    ids = ["search"]
    if read_candidate:
        messages.extend(
            exchange(
                "read",
                "open",
                {"id_or_url": "https://example.org/history"},
                artifact={"page_source": {"source_url": "https://example.org/history"}},
            )
        )
        ids.append("read")
    memories = await review(Workspace(), Model([record(ids=ids)]), messages)
    assert len(memories) == int(read_candidate)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "length,related,expected", [(900, False, 0), (900, True, 1), (5000, True, 0)]
)
async def test_long_source_identity_is_complete_or_rejected_without_prefix_alias(
    length, related, expected
):
    candidate = "https://example.org/" + "x" * length + "/candidate"
    read = candidate if related else "https://example.org/" + "x" * length + "/other"
    messages = [
        *exchange(
            "search",
            "search",
            {"query": "Acme founding year"},
            artifact={
                "outcome": {"status": "success", "result_count": 1},
                "results": [{"url": candidate}],
            },
        ),
        *exchange(
            "read", "open", {"id_or_url": read}, artifact={"page_source": {"source_url": read}}
        ),
    ]
    memories = await review(Workspace(), Model([record(ids=["search", "read"])]), messages)
    assert len(memories) == expected
