"""技能工具的固定入口；推荐名称不缩小发现与执行范围。"""

from .catalog import list_skills, load_anti_patterns
from .execution import load_skill, read_skill_file


def get_skill_tools(skill_names: list[str] | None = None) -> list:
    """技能发现与加载入口；执行由通用 exec 中的 SearchAnything CLI 发起。"""
    return [list_skills, load_skill, load_anti_patterns, read_skill_file]


__all__ = [
    "get_skill_tools", "list_skills", "load_skill", "load_anti_patterns",
    "read_skill_file",
]
