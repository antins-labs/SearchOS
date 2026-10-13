"""显式选择按任务或当前 schema 路由观察。"""

from __future__ import annotations

from typing import Any


class TaskRouting:
    def result_mode(self, state: Any, task: Any, requested: str) -> str:
        return requested or (task.result_mode if task else state.research_mode)

    def expand(self, state: Any, items: list[dict]) -> tuple[list[dict], list[tuple[dict, str]]]:
        return items, []


class SchemaRouting(TaskRouting):
    def result_mode(self, state: Any, task: Any, requested: str) -> str:
        return "table" if state.coverage_map.tables else "findings"

    def expand(self, state: Any, items: list[dict]) -> tuple[list[dict], list[tuple[dict, str]]]:
        if not state.coverage_map.tables:
            return items, []
        routed, rejected = [], []
        tasks = {task.id: task for task in state.frontier.questions}
        for item in items:
            task = tasks.get(item.get("task_id"))
            target = item.get("target_table") or (task.table_id if task else "")
            for table_id in [target] if target else state.coverage_map.tables:
                if table_id not in state.coverage_map.tables:
                    rejected.append((item, table_id))
                    continue
                routed.append(
                    {
                        **item,
                        "result_mode": "table",
                        "target_table": table_id,
                        "all_schema_targets": not bool(target),
                    }
                )
        return routed, rejected
