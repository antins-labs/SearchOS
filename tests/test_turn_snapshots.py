"""Per-turn SearchState persistence and history decoration regression tests."""

# ruff: noqa: E402, I001

from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
for path in (str(_REPO), str(_REPO / "web")):
    if path not in sys.path:
        sys.path.insert(0, path)

from api.routes.history import _turn_views
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
