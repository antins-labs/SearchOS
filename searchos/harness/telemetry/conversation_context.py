"""Build the prior-turn context preamble for multi-turn follow-ups, and
reconstruct the user↔AI turn history back out of a persisted conversation.

The interactive TUI keeps a list of completed turns (query + the orchestrator's
closing answer). For a follow-up it reuses the previous ``session_id`` +
``SearchState`` so the coverage table carries over, and feeds this preamble to
``SearchSession.run(context_preamble=...)`` so the orchestrator also has the
conversational history in plain language.

``conversation_turns`` is the inverse: it replays a workspace's
``conversations/orchestrator.json`` into ``[{query, answer, steers}]`` so a
reloaded session (web history reopen, TUI ``/resume``) shows the full
multi-turn dialogue instead of just title + last answer.
"""

from __future__ import annotations

from pathlib import Path
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


# ---- Turn reconstruction (the inverse of build_preamble) ----

# Markers the harness injects as "user" messages that are NOT user input.
_HARNESS_PREFIX = "[AUTOMATED HARNESS"
_STEER_PREFIX = "[用户追问"
# session.run() joins a follow-up preamble and the query with this separator.
_QUERY_SEP = "\n---\n当前问题："


def _msg_text(msg: dict[str, Any]) -> str:
    content = msg.get("content", "")
    if isinstance(content, list):
        content = "\n".join(
            b.get("text", "") for b in content
            if isinstance(b, dict) and b.get("type") == "text"
        )
    return str(content or "").strip()


def conversation_turns(workspace: str | Path) -> list[dict[str, Any]]:
    """Rebuild ``[{query, answer, steers}]`` from the orchestrator's persisted
    conversation log.

    Turn boundary: an assistant text message *not followed by a tool_call*
    (the orchestrator's closing message for that round). Harness-injected
    "user" messages (coverage snapshots, nudges) are ignored; live-steer
    injections become the turn's ``steers``; a follow-up's first message is
    stripped back to the bare query (the preamble precedes ``当前问题：``).
    A closing message with no new user input in between (premature-end
    resume) supersedes the previous turn's answer instead of opening a
    spurious turn.
    """
    import json

    path = Path(workspace) / "conversations" / "orchestrator.json"
    try:
        msgs = json.loads(path.read_text(encoding="utf-8", errors="replace")).get("messages", [])
    except Exception:
        return []

    turns: list[dict[str, Any]] = []
    query: str | None = None
    steers: list[str] = []

    for i, msg in enumerate(msgs):
        role = msg.get("role")
        text = _msg_text(msg)
        if role in ("user", "human"):
            if not text or text.startswith(_HARNESS_PREFIX):
                continue
            if text.startswith(_STEER_PREFIX):
                body = text.split("\n", 1)[1] if "\n" in text else ""
                body = body.split("\n\n请在当前进展", 1)[0].strip()
                if body:
                    steers.append(body)
                continue
            if _QUERY_SEP in text:
                text = text.split(_QUERY_SEP, 1)[1].strip()
            query = text
        elif role in ("ai", "assistant"):
            if msg.get("tool_calls"):
                continue
            nxt = msgs[i + 1] if i + 1 < len(msgs) else None
            if nxt is not None and nxt.get("role") == "tool_call":
                continue
            if not text:
                continue
            if query is not None:
                turns.append({"query": query, "answer": text, "steers": steers})
                query, steers = None, []
            elif turns:
                turns[-1]["answer"] = text
                if steers:
                    turns[-1]["steers"].extend(steers)
                    steers = []
    return turns
