"""Frontier 任务、研究计划与报告工具入口。"""

from searchos.tools.tasks.evidence import bind_evidence, extract_observation
from searchos.tools.tasks.plan import set_research_plan
from searchos.tools.tasks.queue import enqueue_tasks, stop_task
from searchos.tools.tasks.reports import check_agents

__all__ = [
    "enqueue_tasks", "stop_task", "check_agents", "bind_evidence",
    "extract_observation", "set_research_plan", "get_task_tools",
]


def get_task_tools() -> list:
    """Orchestrator task tools (enqueue / check / stop)."""
    return [enqueue_tasks, stop_task, check_agents, bind_evidence, extract_observation]
