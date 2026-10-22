"""统一失败记忆的持久化、范围、回放与历史状态回归。"""

from concurrent.futures import ThreadPoolExecutor

import pytest
from pydantic import ValidationError

from searchos.config.settings import settings
from searchos.socm import (
    FailureMemory,
    FailureScope,
    FailureStore,
    FrontierTask,
    SearchState,
    WorkspaceManager,
    record_failure,
)


def memory(event="t:1:c1", **changes):
    fields = dict(
        kind="query",
        target="Acme revenue",
        reason="empty_result",
        what_failed="The completed query returned no candidates.",
        task_id="t",
        agent_id="a",
        attempt=1,
        observation_ids=[event],
    )
    return FailureMemory(**(fields | changes))


def workspace(tmp_path):
    ws = WorkspaceManager(tmp_path, "session")
    ws.create()
    state = SearchState()
    state.frontier.add(
        FrontierTask(
            id="t", question="Acme revenue", assigned_agent_id="a", attempts=1, status="running"
        )
    )
    ws.save_state(state)
    return ws


def test_replay_is_idempotent_and_a_real_retry_adds_one_observation(tmp_path):
    ws = workspace(tmp_path)
    record_failure(ws, memory())
    record_failure(ws, memory())
    record_failure(ws, memory("t:1:c2"))
    (item,) = ws.load_state().failure_memory.records
    assert item.observed_count == 2
    assert item.observation_ids == ["t:1:c1", "t:1:c2"]
    assert item.scope.task_id == "t"
    assert item.attempt == 1
    assert item.id


@pytest.mark.parametrize(
    "changes",
    [
        {"scope": FailureScope(task_id="other")},
        {"reason": "irrelevant_results"},
        {"operation": "different query filters"},
        {"skill_version": "new-package"},
    ],
)
def test_different_failure_conditions_are_not_merged(changes):
    store = FailureStore()
    store.record(memory())
    store.record(memory("t:1:c2", **changes))
    assert len(store.records) == 2
    assert all(item.observed_count == 1 for item in store.records)


def test_scope_order_does_not_create_distinct_memories():
    store = FailureStore()
    store.record(memory(scope=FailureScope(target_cells=["t/A.x", "t/B.x"])))
    store.record(memory("t:1:c2", scope=FailureScope(target_cells=["t/B.x", "t/A.x"])))
    assert len(store.records) == 1
    assert store.records[0].observed_count == 2


def test_a_path_with_multiple_supporting_calls_counts_as_one_failure():
    store = FailureStore()
    first = memory(kind="path", observation_ids=["t:1:s1", "t:1:r1"])
    second = memory(kind="path", observation_ids=["t:2:s2", "t:2:r2"])
    store.record(first)
    store.record(first)
    store.record(second)
    assert store.records[0].observed_count == 2
    assert len(store.records[0].observation_ids) == 4


def test_replay_cannot_revive_superseded_memory_but_new_failure_can_be_recorded():
    store = FailureStore()
    old = store.record(memory())
    old.superseded = True
    store.record(memory())
    assert len(store.records) == 1 and store.records[0].superseded
    fresh = store.record(memory("t:2:new-call"))
    assert len(store.records) == 2 and not fresh.superseded
    assert fresh.id != old.id


def test_target_cells_keep_table_identity(tmp_path):
    ws = workspace(tmp_path)

    def setup(state):
        for tid in ("first", "second"):
            state.coverage_map.add_table(
                tid, ["name", "value"], primary_key=["name"], entities=["A"]
            )
        task = state.frontier.questions[0]
        task.table_id = "first"
        task.target_cells = ["A.value"]
        return state

    ws.atomic_update_state(setup)
    record_failure(ws, memory())
    assert ws.load_state().failure_memory.records[0].scope.target_cells == ["first/A.value"]


def test_concurrent_records_survive_restart_and_do_not_overwrite(tmp_path):
    ws = workspace(tmp_path)
    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(lambda i: record_failure(ws, memory(f"t:1:c{i}")), range(12)))
    recovered = WorkspaceManager(tmp_path, "session").load_state()
    assert len(recovered.failure_memory.records) == 1
    assert recovered.failure_memory.records[0].observed_count == 12
    assert len(recovered.failure_memory.records[0].observation_ids) == 12


def test_ablation_disables_the_single_write_entry(tmp_path, monkeypatch):
    ws = workspace(tmp_path)
    monkeypatch.setattr(settings, "enable_failure_memory", False)
    assert record_failure(ws, memory()) is None
    assert not ws.load_state().failure_memory.records


def test_logging_failure_is_observable_without_crashing_the_search(caplog):
    class BrokenWorkspace:
        def atomic_update_state(self, update):
            raise OSError("disk unavailable")

    assert record_failure(BrokenWorkspace(), memory()) is None
    assert "Failed to persist search failure memory" in caplog.text


def test_failed_publication_does_not_report_a_record_as_persisted():
    class BrokenPublication:
        def atomic_update_state(self, update):
            update(SearchState())
            raise OSError("publication failed after in-memory update")

    assert record_failure(BrokenPublication(), memory()) is None


def test_old_snapshot_is_converted_once_and_drops_non_search_signals():
    state = SearchState.model_validate(
        {
            "strategy_log": {
                "patterns": [
                    {
                        "kind": "source",
                        "signature": "example.org",
                        "reason": "login required",
                        "first_seen": 3,
                    },
                    {"kind": "query", "signature": "Q", "reason": "query repeated 3 times"},
                    {"kind": "claim", "signature": "e1", "reason": "rejected"},
                ],
                "failure_memories": [
                    {
                        "failure_class": "blocked_source",
                        "what_failed": "A page required login.",
                        "applies_to": "entity:Acme",
                        "do_not_retry": ["source: https://example.org/article"],
                        "created_at": 4,
                    },
                    {"failure_class": "llm_error", "what_failed": "Model failed."},
                ],
            }
        }
    )
    assert len(state.failure_memory.records) == 1
    assert state.failure_memory.records[0].scope.entities == ["Acme"]
    assert state.failure_memory.records[0].target == "https://example.org/article"
    dumped = state.model_dump()
    assert "strategy_log" not in dumped
    assert SearchState.model_validate(dumped).failure_memory == state.failure_memory


@pytest.mark.parametrize("kind", ["claim", "branch", "llm", "tool", "budget"])
def test_only_four_search_failure_kinds_are_accepted(kind):
    with pytest.raises(ValidationError):
        memory(kind=kind)
