"""将 skill 返回值保存为可用 open/find 浏览的不可变页面。"""

from __future__ import annotations

import json
import re
from typing import Any
from uuid import uuid4

from searchos.tools.simple_browser.render import PageContents
from searchos.tools.simple_browser.state import VIEW_TOKENS, _get_browser, _persist_page


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def format_skill_result(result: Any, width: int = 80) -> str:
    """按行宽装填 JSON token；只添加空白，不改变字段、层级或顺序。"""
    if width < 1:
        raise ValueError("width must be positive")
    # 字符串（包括转义引号）不可拆分；其余 token 可在边界处换行。
    tokens = re.finditer(r'"(?:[^"\\]|\\.)*"|[{}\[\],:]|[^{}\[\],:\s]+', _json(result))
    lines: list[str] = []
    line = ""
    depth = 0
    previous = ""
    for match in tokens:
        token = match.group()
        closing = token in ("}", "]")
        next_depth = max(0, depth - 1) if closing else depth
        separator = " " if previous in (",", ":") else ""
        if line and len(line) + len(separator) + len(token) > width:
            lines.append(line)
            # 深层结果仍给内容留空间；括号保留准确的原始层级。
            line = " " * min(next_depth * 2, 8, width // 4) + token
        else:
            line += separator + token
        depth = next_depth + (token in ("{", "["))
        previous = token
    if line:
        lines.append(line)
    return "\n".join(lines)


def show_skill_result(
    skill_name: str, params: dict[str, Any], result: Any, *, artifact=None,
) -> str:
    """保留完整结果，仅将现有 renderer 的初始视窗返回给 agent。"""
    url = f"skill://{skill_name}/{uuid4().hex}"
    body = (
        f"# Skill result: {skill_name}\n\n"
        "## Parameters\n\n" + format_skill_result(params)
        + "\n\n## Result\n\n"
        + format_skill_result(result)
    )
    from searchos.socm.provenance import result_source_urls
    page = PageContents(
        url=url, title=f"Skill: {skill_name}", text=body,
        metadata={"kind": "skill_result", "source_urls": result_source_urls(result)},
    )
    browser = _get_browser()
    browser.add_page(page)
    page_id = _persist_page(url, page)
    if page_id:
        browser.page_ids[url] = page_id
    return browser.show_page(loc=0, view_tokens=VIEW_TOKENS, artifact=artifact)
