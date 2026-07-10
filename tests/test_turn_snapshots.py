"""Per-turn SearchState persistence and history decoration regression tests."""

# ruff: noqa: E402, I001

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
for path in (str(_REPO), str(_REPO / "web")):
    if path not in sys.path:
        sys.path.insert(0, path)

from api.routes.history import _load_turn_resources, _trajectory_records_for_turn, _turn_views
from searchos.socm.state import SearchState
from searchos.socm.workspace import WorkspaceManager


def _complete_event(query: str) -> str:
    return json.dumps({"type": "task_complete", "query": query})


def test_workspace_persists_snapshots_by_successful_turn(tmp_path):
    workspace = WorkspaceManager(tmp_path, "session")
    workspace.create()
    workspace.trajectory_path.write_text(_complete_event("first") + "\n", encoding="utf-8")

    first = workspace.save_turn_snapshot(
        "first",
        SearchState(intent="first"),
        {"coverage_score": 0.5, "evidence_count": 2},
    )
    with workspace.trajectory_path.open("a", encoding="utf-8") as stream:
        stream.write(_complete_event("second") + "\n")
    second = workspace.save_turn_snapshot(
        "second",
        SearchState(intent="second"),
        {"coverage_score": 1.0, "evidence_count": 4},
    )

    assert first.name == "0001.json"
    assert second.name == "0002.json"
    first_data = json.loads(first.read_text(encoding="utf-8"))
    second_data = json.loads(second.read_text(encoding="utf-8"))
    assert first_data["turn_index"] == 0
    assert first_data["search_state"]["intent"] == "first"
    assert second_data["turn_index"] == 1
    assert second_data["coverage_score"] == 1.0


def test_turn_views_never_reuses_latest_state_for_earlier_legacy_turns():
    turns = [
        {"query": "first", "answer": "a"},
        {"query": "second", "answer": "b"},
        {"query": "third", "answer": "c"},
    ]
    latest = {"intent": "third"}

    views = _turn_views(
        turns,
        {},
        latest_state=latest,
        latest_coverage=0.9,
        latest_evidence_count=7,
    )

    assert [view["state_source"] for view in views] == [
        "unavailable", "unavailable", "latest",
    ]
    assert views[0]["search_state"] is None
    assert views[1]["search_state"] is None
    assert views[2]["search_state"] == latest


def test_turn_views_prefers_exact_snapshot_over_latest_fallback():
    turns = [
        {"query": "first", "answer": "a"},
        {"query": "second", "answer": "b"},
    ]
    snapshots = {
        0: {
            "search_state": {"intent": "first"},
            "coverage_score": 0.4,
            "evidence_count": 3,
        },
        1: {
            "search_state": {"intent": "second-at-the-time"},
            "coverage_score": 0.8,
            "evidence_count": 6,
        },
    }

    views = _turn_views(
        turns,
        snapshots,
        latest_state={"intent": "latest-session-state"},
        latest_coverage=1.0,
        latest_evidence_count=9,
    )

    assert [view["state_source"] for view in views] == ["snapshot", "snapshot"]
    assert views[0]["search_state"]["intent"] == "first"
    assert views[1]["search_state"]["intent"] == "second-at-the-time"


def test_turn_resources_restore_usage_from_trajectory(tmp_path):
    trajectory = tmp_path / "trajectory.jsonl"
    trajectory.write_text("\n".join([
        json.dumps({"type": "task_start", "query": "first"}),
        json.dumps({
            "type": "task_complete",
            "elapsed_s": 12.5,
            "total_queries": 3,
            "tool_counts": {"search": 3, "open": 2},
            "token_usage": {"total_tokens": 1200, "llm_calls": 4},
        }),
    ]) + "\n", encoding="utf-8")

    resources = _load_turn_resources(tmp_path)
    views = _turn_views(
        [{"query": "first", "answer": "answer"}],
        {0: {"search_state": {"intent": "first"}}},
        latest_state=None,
        latest_coverage=None,
        latest_evidence_count=None,
        resources=resources,
    )

    assert views[0]["elapsed_s"] == 12.5
    assert views[0]["total_queries"] == 3
    assert views[0]["tool_counts"]["open"] == 2
    assert views[0]["token_usage"]["total_tokens"] == 1200


def test_trajectory_turn_segments_preserve_full_tool_payload(tmp_path):
    records = [
        {"type": "task_start", "query": "first", "session_id": "source"},
        {
            "type": "step",
            "agent": "orchestrator",
            "action": {"name": "search", "args": {"query": "first query"}},
            "observation": "first full output",
        },
        {"type": "task_complete", "session_id": "source"},
        {"type": "task_start", "query": "second", "session_id": "source"},
        {
            "type": "step",
            "agent": "orchestrator",
            "action": {
                "name": "open",
                "args": {"id_or_url": "https://example.com"},
            },
            "observation": "second full output",
        },
        {"type": "task_complete", "session_id": "source"},
    ]
    (tmp_path / "trajectory.jsonl").write_text(
        "\n".join(json.dumps(record) for record in records) + "\n",
        encoding="utf-8",
    )

    second = _trajectory_records_for_turn(tmp_path, 1, 2)

    assert [record["type"] for record in second] == ["task_start", "step", "task_complete"]
    assert second[1]["action"]["args"]["id_or_url"] == "https://example.com"
    assert second[1]["observation"] == "second full output"


def test_branched_workspace_appends_after_copied_baseline(tmp_path):
    workspace = WorkspaceManager(tmp_path, "branch")
    workspace.create()
    workspace.save_turn_snapshot("baseline", SearchState(intent="baseline"))
    workspace.trajectory_path.write_text(_complete_event("follow-up") + "\n", encoding="utf-8")

    follow_up = workspace.save_turn_snapshot(
        "follow-up",
        SearchState(intent="follow-up"),
    )

    assert follow_up.name == "0002.json"
    assert json.loads(follow_up.read_text(encoding="utf-8"))["turn_index"] == 1


def test_in_place_edit_refreshes_latest_snapshot(tmp_path):
    workspace = WorkspaceManager(tmp_path, "session")
    workspace.create()
    workspace.save_turn_snapshot(
        "first",
        SearchState(intent="before"),
        {"coverage_score": 0.2},
    )

    target = workspace.update_latest_turn_snapshot(
        SearchState(intent="after"),
        {"coverage_score": 0.8},
    )

    assert target is not None
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["search_state"]["intent"] == "after"
    assert payload["coverage_score"] == 0.8
    assert payload["updated_at"]


@pytest.mark.asyncio
async def test_history_turn_branch_is_independent_and_restorable(tmp_path, monkeypatch):
    import api.routes.history as history
    from searchos.harness.telemetry.conversation_context import conversation_turns

    monkeypatch.setattr(history, "WORKSPACE_ROOT", str(tmp_path))
    source = WorkspaceManager(tmp_path, "source")
    source.create()
    state = SearchState(intent="original research")
    source.save_state(state)
    history._write_branch_conversation(source.path, "original question", "original answer")
    source.trajectory_path.write_text("\n".join([
        json.dumps({"type": "task_start", "session_id": "source", "query": "original question"}),
        json.dumps({
            "type": "step",
            "agent": "orchestrator",
            "action": {"name": "search", "args": {"query": "full original query"}},
            "observation": "full original tool output",
        }),
        json.dumps({"type": "task_complete", "session_id": "source"}),
    ]) + "\n", encoding="utf-8")
    source.save_turn_snapshot(
        "original question",
        state,
        {"coverage_score": 0.75, "evidence_count": 3},
    )

    response = await history.branch_history_turn("source", 0)
    branch = WorkspaceManager(tmp_path, response.session_id)

    assert response.source_session_id == "source"
    assert response.source_turn_index == 0
    assert branch.path != source.path
    assert branch.load_state().intent == "original research"
    assert conversation_turns(branch.path) == [{
        "query": "original question",
        "answer": "original answer",
        "steers": [],
    }]
    origin = json.loads((branch.path / ".branch_origin.json").read_text(encoding="utf-8"))
    assert origin["source_session_id"] == "source"
    assert origin["copied_event_count"] == 3
    branch_records = [
        json.loads(line)
        for line in branch.trajectory_path.read_text(encoding="utf-8").splitlines()
    ]
    assert branch_records[0]["session_id"] == response.session_id
    assert branch_records[1]["action"]["args"]["query"] == "full original query"
    assert branch_records[1]["observation"] == "full original tool output"
    assert (branch.path / "turn_snapshots" / "0001.json").exists()


@pytest.mark.asyncio
async def test_history_branch_supports_legacy_final_state(tmp_path, monkeypatch):
    import api.routes.history as history

    monkeypatch.setattr(history, "WORKSPACE_ROOT", str(tmp_path))
    source = WorkspaceManager(tmp_path, "legacy")
    source.create()
    source.save_state(SearchState(intent="legacy research"))

    response = await history.branch_history_turn("legacy", 0)
    branch = WorkspaceManager(tmp_path, response.session_id)

    assert branch.load_state().intent == "legacy research"
    assert (branch.path / "turn_snapshots" / "0001.json").exists()
