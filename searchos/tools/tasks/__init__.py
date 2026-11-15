"""Frontier 任务与报告工具入口。"""

from searchos.tools.tasks.evidence import bind_evidence, extract_observation
from searchos.tools.tasks.queue import enqueue_tasks, stop_task
from searchos.tools.tasks.reports import check_agents

__all__ = [
    "enqueue_tasks", "check_agents", "stop_task", "bind_evidence",
    "extract_observation", "get_task_tools",
]


def get_task_tools() -> list:
    """Orchestrator task tools."""
    return [enqueue_tasks, check_agents, stop_task, bind_evidence, extract_observation]
