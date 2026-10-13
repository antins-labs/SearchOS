"""Correctness gates for performance changes; wall-clock thresholds belong in benchmarks."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from searchos.socm.persistence import read_snapshot
from searchos.socm.state import SearchState
from searchos.socm.workspace import WorkspaceManager


def test_snapshot_replacement_and_mutation_isolation(tmp_path):
    ws = WorkspaceManager(tmp_path, "session")
    ws.path.mkdir()
    ws.save_state(SearchState(intent="first"))
    first = read_snapshot(ws.path / "search_state.json")
    assert read_snapshot(ws.path / "search_state.json") is first
    a = ws.load_state()
    a.intent = "not committed"
    assert ws.load_state().intent == "first"
    other = WorkspaceManager(tmp_path, "session")
    other.atomic_update_state(lambda s: s.model_copy(update={"intent": "second"}))
    assert ws.load_state().intent == "second"
    assert read_snapshot(ws.path / "search_state.json").revision != first.revision


def test_noop_does_not_publish_and_concurrent_updates_are_preserved(tmp_path):
    ws = WorkspaceManager(tmp_path, "session")
    ws.path.mkdir()
    ws.save_state(SearchState(intent=""))
    revision = read_snapshot(ws.path / "search_state.json").revision
    ws.atomic_update_state(lambda state: state)
    assert read_snapshot(ws.path / "search_state.json").revision == revision

    def update(i):
        worker = WorkspaceManager(tmp_path, "session")

        def append(state):
            state.intent += f"{i},"
            return state

        worker.atomic_update_state(append)

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(update, range(20)))
    assert set(ws.load_state().intent.rstrip(",").split(",")) == {str(i) for i in range(20)}


def test_conversation_journal_checkpoint_recovery_and_follow_up(tmp_path):
    import json

    from searchos.harness.telemetry.conversation import ConversationLogger, read_conversation
    from searchos.harness.telemetry.trajectory import ConversationMessage

    logger = ConversationLogger(tmp_path / "conversation.json")
    logger.register_sub_agent("orchestrator", "", "task")
    path = tmp_path / "conversations/snapshots/orchestrator.json"
    for i in range(35):
        logger.log(ConversationMessage(content=str(i)))
    assert len(json.loads(path.read_text())["messages"]) == 32
    assert len(read_conversation(path)["messages"]) == 35
    # Simulate an interrupted write after complete entries, then restart before checkpointing.
    with (path.parent.parent / "journals" / "orchestrator.jsonl").open("ab") as stream:
        stream.write(b'{"message":')
    resumed = ConversationLogger(tmp_path / "conversation.json")
    resumed.hydrate()
    resumed.log(ConversationMessage(content="follow-up"))
    assert [msg["content"] for msg in read_conversation(path)["messages"]] == [
        str(i) for i in range(35)
    ] + ["follow-up"]
    resumed.flush()
    assert len(json.loads(path.read_text())["messages"]) == 36
    assert len(read_conversation(path)["messages"]) == 36
    resumed.register_sub_agent("worker", "orchestrator", "child task")
    assert read_conversation(path)["children"] == ["worker"]


def test_state_stream_skips_unchanged_and_encodes_deletes_and_appends(tmp_path):
    import json
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "web"))
    from unittest.mock import patch

    from api.routes.search import _get_live_state
    from api.state_stream import StateStream

    path = tmp_path / "session/search_state.json"
    path.parent.mkdir()
    initial = {
        "large": "x" * 4000,
        "coverage_map": {"cells": {"a": {"value": "old"}, "b": {"value": "remove"}}},
        "evidence_graph": {"nodes": [{"id": "e1"}]},
    }
    path.write_text(json.dumps(initial))
    stream = StateStream()
    first = stream.event(path)
    assert first["type"] == "state_snapshot"
    with patch(
        "api.state_stream.json.loads", side_effect=AssertionError("unchanged must not parse")
    ):
        assert stream.event(path) is None
    initial["coverage_map"]["cells"].pop("b")
    initial["coverage_map"]["cells"]["a"]["value"] = ""
    initial["evidence_graph"]["nodes"].append({"id": "e2"})
    path.write_text(json.dumps(initial))
    changed = stream.event(path)
    assert changed["type"] == "state_delta"
    assert changed["base_revision"] == first["revision"]
    assert {change["op"] for change in changed["changes"]} == {"set", "delete", "append"}
    assert stream.new_evidence == [{"id": "e2"}]
    with patch("api.routes.search.WORKSPACE_ROOT", str(tmp_path)):
        response = _get_live_state("session", changed["revision"])
    assert response["not_modified"] is True and "search_state" not in response
    initial["evidence_graph"]["nodes"] = []
    path.write_text(json.dumps(initial))
    assert any(
        change["op"] == "set" and change["value"] == [] for change in stream.event(path)["changes"]
    )


@pytest.mark.asyncio
async def test_jsonl_stream_preserves_partial_tail_and_stable_replay_ids(tmp_path):
    from api.routes.stream import _stream_jsonl

    class Socket:
        def __init__(self):
            self.events = []

        async def send_json(self, event):
            self.events.append(event)

    path = tmp_path / "trajectory.jsonl"
    path.write_bytes(b'{"n":1}\n{"n":')
    socket, positions = Socket(), {}
    await _stream_jsonl(socket, path, "trajectory", positions)
    assert len(socket.events) == 1
    with path.open("ab") as stream:
        stream.write(b"2}\n")
    await _stream_jsonl(socket, path, "trajectory", positions)
    assert [event["data"]["n"] for event in socket.events] == [1, 2]
    replay = Socket()
    await _stream_jsonl(replay, path, "trajectory", {})
    assert replay.events == socket.events


def recap_document():
    from types import SimpleNamespace

    from searchos.local.models import LineRangeLocator, ParsedSegment

    return SimpleNamespace(
        primary_segments=[
            ParsedSegment(
                id=str(i),
                title=str(i),
                text="body",
                source_locators=[LineRangeLocator(start_line=i + 1, end_line=i + 1)],
            )
            for i in range(6)
        ]
    )


@pytest.mark.asyncio
async def test_recap_bounded_concurrency_order_progress_and_failure(monkeypatch):
    from searchos.local.recap.service import RecapService

    monkeypatch.setattr(
        "searchos.local.recap.service._pack_batches", lambda segments, _: [[s] for s in segments]
    )
    entered = asyncio.Event()
    releases = [asyncio.Event() for _ in range(6)]

    class Client:
        active = 0
        peak = 0
        calls = []

        async def summarize_segment(self, segment):
            self.active += 1
            self.peak = max(self.peak, self.active)
            self.calls.append(segment.id)
            if self.active == 3:
                entered.set()
            try:
                await releases[int(segment.id)].wait()
                if segment.id == "1":
                    raise ValueError("intentional")
                return {"title": segment.title, "summary": "summary"}
            finally:
                self.active -= 1

        async def summarize_document(self, sections):
            self.order = [section.segment_ids[0] for section in sections]
            return "document summary"

    client = Client()
    progress = []
    task = asyncio.create_task(
        RecapService(client, concurrency=3).generate(
            recap_document(), max_chars=2000, on_progress=lambda done, total: progress.append(done)
        )
    )
    await asyncio.wait_for(entered.wait(), 2)
    assert len(client.calls) == 3
    for release in reversed(releases):
        release.set()
    recap = await task
    assert client.peak == 3 and client.active == 0
    assert client.order == ["0", "2", "3", "4", "5"]
    assert len(recap.warnings) == 1
    assert progress == sorted(progress) and progress[-1] == 5


@pytest.mark.asyncio
async def test_recap_cancel_drains_all_workers(monkeypatch):
    from searchos.local.recap.service import RecapService

    monkeypatch.setattr(
        "searchos.local.recap.service._pack_batches", lambda segments, _: [[s] for s in segments]
    )
    entered = asyncio.Event()

    class Client:
        active = 0

        async def summarize_segment(self, segment):
            self.active += 1
            if self.active == 3:
                entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                self.active -= 1

    client = Client()
    task = asyncio.create_task(
        RecapService(client, concurrency=3).generate(recap_document(), max_chars=2000)
    )
    await asyncio.wait_for(entered.wait(), 2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert client.active == 0


def test_websocket_protocol_snapshot_delta_reconnect_and_completion(tmp_path, monkeypatch):
    import json
    from types import SimpleNamespace

    from api.routes import stream
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    ws = WorkspaceManager(tmp_path, "session")
    ws.path.mkdir()
    ws.save_state(SearchState(intent="x" * 4000))
    (ws.path / "trajectory.jsonl").write_text('{"type":"step"}\n')
    running = {"session": {"status": "running"}}
    monkeypatch.setattr(stream, "WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr(stream, "sessions", running)
    app = FastAPI()
    app.include_router(stream.router)
    with TestClient(app) as client:
        with client.websocket_connect("/api/ws/session") as socket:
            trajectory = socket.receive_json()
            first = socket.receive_json()
            assert trajectory["event_id"] == "trajectory:16"
            assert first["type"] == "state_snapshot"
            ws.atomic_update_state(lambda state: state.model_copy(update={"intent": "updated"}))
            changed = socket.receive_json()
            assert changed["type"] == "state_delta"
            assert changed["base_revision"] == first["revision"]
            assert len(json.dumps(changed)) < 500
            running["session"] = {
                "status": "completed",
                "result": SimpleNamespace(
                    coverage_score=0,
                    evidence_count=0,
                    total_queries=0,
                    total_steps=1,
                    elapsed_s=1,
                    eval_verdict="",
                ),
            }
            assert socket.receive_json()["type"] == "search_complete"
        with client.websocket_connect("/api/ws/session") as socket:
            assert socket.receive_json() == trajectory
            assert socket.receive_json()["type"] == "state_snapshot"
            assert socket.receive_json()["type"] == "search_complete"
        with client.websocket_connect("/api/ws/session?tail=1") as socket:
            assert socket.receive_json()["type"] == "state_snapshot"
            assert socket.receive_json()["type"] == "search_complete"


def test_snapshot_cache_observes_another_process_commit(tmp_path):
    import subprocess
    import sys

    ws = WorkspaceManager(tmp_path, "session")
    ws.path.mkdir()
    ws.save_state(SearchState(intent="before"))
    assert ws.load_state().intent == "before"
    subprocess.run(
        [
            sys.executable,
            "-c",
            "from searchos.socm.workspace import WorkspaceManager; import sys; "
            "w=WorkspaceManager(sys.argv[1], 'session'); "
            "w.atomic_update_state(lambda s:s.model_copy(update={'intent':'external'}))",
            str(tmp_path),
        ],
        check=True,
        timeout=15,
    )
    assert ws.load_state().intent == "external"


def test_conversation_directory_move_preserves_snapshot_watermark(tmp_path):
    from searchos.harness.telemetry.conversation import ConversationLogger, read_conversation
    from searchos.harness.telemetry.trajectory import ConversationMessage

    logger = ConversationLogger(tmp_path / "conversation.json")
    for i in range(35):
        logger.log(ConversationMessage(content=str(i)))
    root = tmp_path / "conversations"
    for directory in ("snapshots", "journals"):
        for path in (root / directory).iterdir():
            path.rename(root / path.name)
        (root / directory).rmdir()
    result = read_conversation(root / "snapshots/orchestrator.json")
    assert [m["content"] for m in result["messages"]] == [str(i) for i in range(35)]
    assert not list(root.glob("*.json*"))
    resumed = ConversationLogger(tmp_path / "conversation.json")
    resumed.hydrate()
    resumed.log(ConversationMessage(content="next"))
    assert len(read_conversation(root / "snapshots/orchestrator.json")["messages"]) == 36
