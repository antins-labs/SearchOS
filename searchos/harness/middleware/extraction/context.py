"""Evidence Intake 完成后返回给 Agent 的 Skill 上下文策略。"""

from __future__ import annotations

import json
from typing import Any


def render_skill_context(
    content: str,
    *,
    source_url: str,
    committed_count: int,
    max_chars: int,
    preview_records: int,
    feedback: str = "",
) -> str:
    """保留短结果；把超长结构化结果收束为有界、可解释的预览。

    完整输入已经由同步 Intake 分批处理，因此这里的截断只影响 Agent
    对话上下文，不影响 Evidence Graph 中刚提交的抽取结果。
    """
    max_chars = max(300, int(max_chars))
    full_context = content + ("\n\n" + feedback if feedback else "")
    if len(full_context) <= max_chars:
        return full_context

    preview, shown, total = _structured_preview(content, max(1, preview_records))
    lines = [
        "[Skill Evidence Intake 回执]",
        "完整返回已完成分批 FILL → DISCOVER；以下仅为 Agent 上下文预览。",
        "不要仅因预览截断而重复调用该 Skill。",
        f"来源：{source_url or '<unknown>'}",
        f"原始字符数：{len(content)}；已写入 Evidence Graph：{committed_count}",
    ]
    if total is not None:
        lines.append(f"结构化记录：共 {total} 条，预览 {shown} 条")
    if feedback:
        lines.append(feedback)
    prefix = "\n".join(lines) + "\n\n"
    remaining = max_chars - len(prefix)
    if remaining <= 0:
        return prefix[:max_chars]
    return prefix + preview[:remaining]


def _structured_preview(content: str, limit: int) -> tuple[str, int, int | None]:
    try:
        data = json.loads(content)
    except Exception:
        return content, 0, None

    if isinstance(data, list):
        shown = min(limit, len(data))
        return _dump(data[:shown]), shown, len(data)
    if not isinstance(data, dict):
        return _dump(data), 0, None

    array_key = ""
    rows: list[Any] = []
    for key, value in data.items():
        if isinstance(value, list) and len(value) > len(rows):
            array_key, rows = str(key), value
    if not array_key:
        return _dump(data), 0, None

    shown = min(limit, len(rows))
    # 只保留轻量顶层元数据；避免另一个大字段绕过上下文预算。
    metadata = {
        key: value
        for key, value in data.items()
        if key != array_key and isinstance(value, (str, int, float, bool, type(None)))
    }
    return _dump({**metadata, array_key: rows[:shown]}), shown, len(rows)


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)
