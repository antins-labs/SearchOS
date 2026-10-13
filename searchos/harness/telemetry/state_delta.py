"""记录工具执行前后的研究状态增量。"""

from __future__ import annotations

from typing import Any

from searchos.harness.telemetry.trajectory import StateDelta


def capture_state(workspace) -> dict[str, Any]:
    """Capture a lightweight snapshot of current search state for delta computation."""
    if workspace is None:
        return {}
    try:
        state = workspace.state
        resolved_ids = {q.id for q in state.frontier.questions if q.status.value == "completed"}
        return {
            "coverage": state.coverage_map.coverage_score,
            "evidence_count": state.evidence_graph.node_count,
            "frontier_resolved": resolved_ids,
            "frontier_count": len(state.frontier.questions),
            "conflict_count": len(state.evidence_graph.get_conflicts()),
        }
    except Exception:
        return {}


def state_delta(
    before: dict[str, Any],
    after: dict[str, Any],
) -> StateDelta:
    """Compute the state delta between two snapshots."""
    if not before or not after:
        return StateDelta()

    resolved_before = before.get("frontier_resolved", set())
    resolved_after = after.get("frontier_resolved", set())
    newly_resolved = list(resolved_after - resolved_before)

    conflicts_before = before.get("conflict_count", 0)
    conflicts_after = after.get("conflict_count", 0)
    new_conflicts = max(0, conflicts_after - conflicts_before)
    resolved_conflicts = max(0, conflicts_before - conflicts_after)

    return StateDelta(
        coverage_before=before.get("coverage", 0.0),
        coverage_after=after.get("coverage", 0.0),
        new_evidence_count=max(
            0,
            after.get("evidence_count", 0) - before.get("evidence_count", 0),
        ),
        frontier_resolved=newly_resolved,
        frontier_added=[],  # hard to track without IDs
        conflicts_detected=new_conflicts,
        conflicts_resolved=resolved_conflicts,
    )
