"""Middleware 共享的任务输入；不包含组件装配策略。"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class TaskContext:
    agent_id: str = ""
    task_id: str = ""
    target_table: str = ""
    task_text: str = ""


@dataclass(frozen=True, slots=True)
class SourceContext:
    """来源访问范围和记录来源状态的 workspace。"""

    workspace: Any = None
    scope: Mapping[str, Any] | None = None
