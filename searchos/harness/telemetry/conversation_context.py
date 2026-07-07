"""Build the prior-turn context preamble for multi-turn follow-ups.

The interactive TUI keeps a list of completed turns (query + the orchestrator's
closing answer). For a follow-up it reuses the previous ``session_id`` +
``SearchState`` so the coverage table carries over, and feeds this preamble to
``SearchSession.run(context_preamble=...)`` so the orchestrator also has the
conversational history in plain language.
"""

from __future__ import annotations

from typing import Any

MAX_TURNS = 4
MAX_ANSWER_CHARS = 800


def build_preamble(
    turns: list[dict[str, Any]],
    *,
    max_turns: int = MAX_TURNS,
    max_answer_chars: int = MAX_ANSWER_CHARS,
) -> str:
    """Render the last few turns as a Chinese context preamble.

    ``turns`` items are dicts with ``query`` and ``answer`` keys. Returns an
    empty string when there is no history (first turn of a conversation).
    """
    if not turns:
        return ""
    recent = turns[-max_turns:]
    blocks: list[str] = []
    for i, t in enumerate(recent, 1):
        q = (t.get("query") or "").strip()
        a = (t.get("answer") or "").strip()
        if len(a) > max_answer_chars:
            a = a[:max_answer_chars] + "…"
        blocks.append(
            f"[第 {i} 轮]\n问题：{q}\n回答：{a or '(无文本回答)'}"
        )
    body = "\n\n".join(blocks)
    return (
        "## 对话历史（供参考；本轮已沿用上一轮的覆盖表/证据）\n"
        f"{body}\n\n"
        "用户现在提出新的追问。请先判断本轮是否真的需要再检索：\n"
        "- 若答案已在现有覆盖表/证据中（例如就已收集的数据做筛选、比较、改写、解释或直接问答），"
        "先用 `inspect_table` 读取当前单元格的值，然后**直接作答**，不要再派发 Explore/搜索代理，也不要重建 schema。\n"
        "- 仅当追问确需表中尚无的数据（新增一列、补充若干行、或需重新取证纠正某个值）时才检索，"
        "且应在现有覆盖表上扩展，不要从零重建；若确为全新话题，再新建结构。"
    )
