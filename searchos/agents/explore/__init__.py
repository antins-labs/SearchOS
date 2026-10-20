"""按需解决首次或后续检索中的不确定性，以简报返回线索与建议。"""

from __future__ import annotations

AGENT_TYPE = "explore_agent"


def get_tools(skill_names: list[str] | None = None) -> list:
    """根据开关选择并发覆盖波次或旧版串行浏览工具。"""
    from searchos.config.settings import settings
    from searchos.tools.simple_browser import explore_web, find, get_simple_browser_tools, open

    if settings.enable_explore_batch:
        return [explore_web, open, find]
    return list(get_simple_browser_tools())
