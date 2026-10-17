"""技能工具的固定入口；推荐名称不缩小发现与执行范围。"""

from .catalog import list_skills, load_anti_patterns
from .execution import exec_skill, load_skill, read_skill_file


def get_skill_tools(skill_names: list[str] | None = None) -> list:
    """Fixed discovery and execution surface; dispatch names are recommendations."""
    return [list_skills, load_skill, load_anti_patterns, exec_skill, read_skill_file]


__all__ = [
    "get_skill_tools", "list_skills", "load_skill", "load_anti_patterns",
    "exec_skill", "read_skill_file",
]
