"""任务可归属的有效事实与用途增量；不把其他 worker 的提交算给当前任务。"""

from __future__ import annotations

from typing import Any

from searchos.harness.middleware.models import TaskContext


def task_progress(workspace: Any, task: TaskContext) -> frozenset[tuple] | None:
    if workspace is None:
        return frozenset()
    try:
        from searchos.socm.coverage import answer_evidence

        state = workspace.load_state()
        active = {node.id for node in answer_evidence(state)}
        task_id = task.task_id
        if not task_id and task.agent_id:
            assigned = [
                q.id for q in state.frontier.questions if q.assigned_agent_id == task.agent_id
            ]
            if len(assigned) != 1:
                return None  # Unknown ownership must not become a global worker snapshot.
            task_id = assigned[0]
        bindings = {
            (b.task_id, b.evidence_id, b.relation)
            for b in state.evidence_graph.task_bindings
            if b.evidence_id in active and (not task_id or b.task_id == task_id)
        }
        owned = {b[1] for b in bindings} if task_id else active
        result = {("fact", eid) for eid in owned} | {("task", *b) for b in bindings}
        for key, cell in state.coverage_map.cells.items():
            if owned.intersection(cell.supporting_evidence_ids):
                result.add(("cell", key, cell.status.value, cell.display_hint, cell.has_conflict))
        return frozenset(result)
    except Exception:
        return None  # A failed snapshot is unknown, never evidence of stagnation.
