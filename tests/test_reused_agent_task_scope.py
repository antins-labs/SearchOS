"""同一 Agent 接续任务时，目标、证据和重试路线按当前任务隔离。"""

import pytest

from searchos.harness.middleware.context.socm_middleware import SOCMContextMiddleware
from searchos.harness.middleware.extraction import InMemoryEvidenceStore
from searchos.harness.middleware.models import TaskContext
from searchos.socm import EvidenceNode, FrontierTask, FrontierTaskStatus, SearchState
from searchos.socm.evidence.graph import TaskEvidenceBinding
from searchos.socm.planning.retry_routes import (
    check_and_record_route,
    record_route_outcome,
    route_signature,
)
from searchos.tools.search_state import _current_task_id_var


@pytest.fixture(autouse=True)
def task_context():
    token = _current_task_id_var.set("")
    try:
        yield
    finally:
        _current_task_id_var.reset(token)


def reused_agent_store():
    state = SearchState()
    state.coverage_map.add_table(
        "papers", ["Name", "Method"], primary_key=["Name"], entities=["Old", "New"]
    )
    for task_id, entity, status in (
        ("old", "Old", FrontierTaskStatus.COMPLETED),
        ("new", "New", FrontierTaskStatus.RUNNING),
    ):
        state.frontier.add(FrontierTask(
            id=task_id,
            question=f"Investigate {entity}",
            assigned_agent_id="reader",
            status=status,
            table_id="papers",
            target_cells=[f"papers/{entity}.Method"],
        ))
        state.evidence_graph.nodes.append(EvidenceNode(
            id=f"e_{task_id}",
            finding=f"{entity} evidence finding",
            source=f"https://example.org/{task_id}",
        ))
        state.evidence_graph.task_bindings.append(TaskEvidenceBinding(
            task_id=task_id, evidence_id=f"e_{task_id}",
        ))
    return InMemoryEvidenceStore(state)


@pytest.mark.parametrize("task_id", ["new", ""])
def test_reused_agent_projection_uses_current_targets(task_id):
    store = reused_agent_store()
    middleware = SOCMContextMiddleware(
        store, task=TaskContext(agent_id="reader", task_id=task_id),
    )

    text = middleware.render()

    projection = middleware._projection
    assert [task.id for task in projection._assigned_tasks(store.state)] == ["new"]
    assert projection._resolve_agent_target_cells(store.state) == (
        {"papers/New.Method"}, {"New"}, "papers",
    )
    assert "New" in text
    assert "Old" not in text
    assert "Investigate Old" not in text


def test_explicit_projection_task_wins_over_another_running_assignment():
    store = reused_agent_store()
    middleware = SOCMContextMiddleware(
        store, task=TaskContext(agent_id="reader", task_id="old"),
    )

    text = middleware.render()

    projection = middleware._projection
    assert [task.id for task in projection._assigned_tasks(store.state)] == ["old"]
    assert projection._resolve_agent_target_cells(store.state) == (
        {"papers/Old.Method"}, {"Old"}, "papers",
    )
    assert "Old" in text
    assert "New" not in text


@pytest.mark.parametrize("task_id", ["new", ""])
def test_reused_agent_routes_read_and_write_current_task(task_id):
    store = reused_agent_store()
    old, current = store.state.frontier.questions
    old.previous_queries = ["fresh paper search"]
    current.previous_queries = ["failed paper search"]
    _current_task_id_var.set(task_id)

    assert not check_and_record_route(
        store, "reader", "search", {"query": "fresh paper search site:example.org"},
    )
    assert not check_and_record_route(
        store, "reader", "search", {"query": "fresh paper search"},
    )
    assert "RETRY_ROUTE_BLOCKED" in check_and_record_route(
        store, "reader", "search", {"query": "failed paper search"},
    )
    signature = route_signature("search", {"query": "fresh paper search"})
    record_route_outcome(store, "reader", signature, "success")

    old, current = store.state.frontier.questions
    assert current.attempt_queries == ["fresh paper search site:example.org", "fresh paper search"]
    assert current.attempt_source_families == ["example.org"]
    assert current.route_history == [{
        "signature": signature, "worker": "reader", "attempt": 0, "outcome": "success",
    }]
    assert old.attempt_queries == []
    assert old.attempt_source_families == []
    assert old.route_history == []


def test_explicit_route_task_wins_over_another_running_assignment():
    store = reused_agent_store()
    old, current = store.state.frontier.questions
    _current_task_id_var.set("old")

    assert not check_and_record_route(store, "reader", "search", {"query": "original question"})
    record_route_outcome(store, "reader", "original-route", "empty")

    old, current = store.state.frontier.questions
    assert old.attempt_queries == ["original question"]
    assert old.route_history == [{
        "signature": "original-route", "worker": "reader", "attempt": 0, "outcome": "empty",
    }]
    assert current.attempt_queries == []
    assert current.route_history == []


def test_route_task_context_cannot_write_a_sibling_assignment():
    store = reused_agent_store()
    store.state.frontier.add(FrontierTask(
        id="sibling", question="Separate question", assigned_agent_id="other_reader",
        status=FrontierTaskStatus.RUNNING,
    ))
    _current_task_id_var.set("sibling")

    assert not check_and_record_route(store, "reader", "search", {"query": "current question"})
    record_route_outcome(store, "reader", "current-route", "success")

    old, current, sibling = store.state.frontier.questions
    assert current.attempt_queries == ["current question"]
    assert current.route_history[-1]["signature"] == "current-route"
    assert old.attempt_queries == sibling.attempt_queries == []
    assert old.route_history == sibling.route_history == []


@pytest.mark.parametrize("outcome", ["empty", "permanent_error"])
def test_reused_worker_cannot_repeat_failed_route_from_previous_attempt(outcome):
    store = reused_agent_store()
    store.state.frontier.questions[1].attempts = 1
    _current_task_id_var.set("new")
    args = {"query": "paper evaluation site:example.org"}
    signature = route_signature("search", args)
    assert not check_and_record_route(store, "reader", "search", args)
    record_route_outcome(store, "reader", signature, outcome)
    store.state.frontier.questions[1].attempts = 2

    assert "RETRY_ROUTE_BLOCKED" in check_and_record_route(store, "reader", "search", args)
    assert not check_and_record_route(
        store, "reader", "search", {"query": "paper evaluation site:other.org"},
    )
    assert store.state.frontier.questions[1].route_history[0]["attempt"] == 1


@pytest.mark.parametrize("outcome", ["empty", "permanent_error", "success", "transient_error"])
def test_route_outcome_does_not_block_current_attempt(outcome):
    store = reused_agent_store()
    store.state.frontier.questions[1].attempts = 2
    _current_task_id_var.set("new")
    args = {"query": "paper evaluation"}
    record_route_outcome(store, "reader", route_signature("search", args), outcome)

    assert not check_and_record_route(store, "reader", "search", args)


@pytest.mark.parametrize("outcome", ["success", "transient_error"])
def test_reused_worker_can_repeat_successful_or_transient_route_across_attempts(outcome):
    store = reused_agent_store()
    store.state.frontier.questions[1].attempts = 1
    _current_task_id_var.set("new")
    args = {"query": "paper evaluation"}
    record_route_outcome(store, "reader", route_signature("search", args), outcome)
    store.state.frontier.questions[1].attempts = 2

    assert not check_and_record_route(store, "reader", "search", args)


@pytest.mark.parametrize("worker,blocked", [("reader", False), ("previous_reader", True)])
def test_legacy_route_without_attempt_preserves_worker_based_compatibility(worker, blocked):
    store = reused_agent_store()
    args = {"query": "legacy paper route"}
    current = store.state.frontier.questions[1]
    current.attempts = 2
    current.route_history = [{
        "signature": route_signature("search", args), "worker": worker, "outcome": "empty",
    }]
    _current_task_id_var.set("new")

    result = check_and_record_route(store, "reader", "search", args)

    assert ("RETRY_ROUTE_BLOCKED" in result) is blocked
