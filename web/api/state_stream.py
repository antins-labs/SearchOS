"""Versioned state events. Delta paths address JSON keys, never executable expressions."""

from __future__ import annotations

import json
from pathlib import Path

from searchos.socm.persistence import read_snapshot


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
