"""生成带版本的状态事件与可增量读取的运行时间线。"""

from __future__ import annotations

import heapq
import json
from pathlib import Path

from searchos.socm.storage.file_snapshots import read_snapshot


def json_delta(before, after, path=()):
    if isinstance(before, dict) and isinstance(after, dict):
        changes = [{"op": "delete", "path": [*path, key]} for key in before.keys() - after.keys()]
        for key, value in after.items():
            if key not in before:
                changes.append({"op": "set", "path": [*path, key], "value": value})
            else:
                changes.extend(json_delta(before[key], value, (*path, key)))
        return changes
    if before == after:
        return []
    if (
        isinstance(before, list)
        and isinstance(after, list)
        and len(after) > len(before)
        and after[: len(before)] == before
    ):
        return [{"op": "append", "path": list(path), "value": after[len(before) :]}]
    return [{"op": "set", "path": list(path), "value": after}]


class StateStream:
    def __init__(self):
        self.revision = ""
        self.state = None
        self.new_evidence = []

    def event(self, path: Path):
        try:
            snapshot = read_snapshot(path)
        except FileNotFoundError:
            return None
        if snapshot.revision == self.revision:
            return None
        state = json.loads(snapshot.content)
        previous_ids = {
            node["id"] for node in (self.state or {}).get("evidence_graph", {}).get("nodes", [])
        }
        self.new_evidence = [
            node
            for node in state.get("evidence_graph", {}).get("nodes", [])
            if node["id"] not in previous_ids
        ]
        event = {"type": "state_snapshot", "revision": snapshot.revision, "state": state}
        if self.state is not None:
            delta = {
                "type": "state_delta",
                "base_revision": self.revision,
                "revision": snapshot.revision,
                "changes": json_delta(self.state, state),
            }
            if len(json.dumps(delta, ensure_ascii=False)) < len(snapshot.content):
                event = delta
        self.state, self.revision = state, snapshot.revision
        return event


def report_journal(workspace: Path) -> Path:
    return workspace / "conversations/journals/orchestrator.jsonl"


def _records(path, positions, *, contains=None):
    try:
        stream = path.open("rb")
    except FileNotFoundError:
        return
    key = str(path)
    with stream:
        offset = positions.get(key, 0)
        size = stream.seek(0, 2)
        stream.seek(offset if offset <= size else 0)
        while line := stream.readline():
            if not line.endswith(b"\n"):
                break
            positions[key] = stream.tell()
            if contains and contains not in line:
                continue
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if isinstance(record, dict):
                yield positions[key], record


def file_events(path, prefix, positions):
    return ({"type": prefix, "data": record, "event_id": f"{prefix}:{end}"}
            for end, record in _records(path, positions))


def _report_events(workspace, positions):
    for end, record in _records(report_journal(workspace), positions, contains=b'"agent_reports"'):
        message = record.get("message") or {}
        if message.get("role") != "system" or (message.get("metadata") or {}).get("synthetic") != "agent_reports":
            continue
        try:
            payload = json.loads(message["content"])
        except (KeyError, TypeError, ValueError):
            continue
        reports = payload.get("reports") if isinstance(payload, dict) else None
        if not isinstance(reports, list):
            continue
        for i, report in enumerate(reports):
            if isinstance(report, dict) and report.get("agent_id"):
                yield {"type": "trajectory", "event_id": f"agent_report:{end}:{i}",
                       "data": {"type": "agent_report", "agent": "orchestrator",
                                "timestamp": message.get("timestamp", ""), "report": report}}


def timeline_events(workspace: Path, positions: dict[str, int]) -> list[dict]:
    return list(heapq.merge(
        file_events(workspace / "trajectory.jsonl", "trajectory", positions),
        _report_events(workspace, positions),
        key=lambda event: event["data"].get("timestamp") or "",
    ))
