"""ConversationLogger: per-agent 完整对话记录。

每个 agent 一个 JSON：workspace/<session>/conversations/<agent_name>.json
结构：
{
  "agent_name": "...",
  "agent_type": "search_agent" | "writer_agent" | "orchestrator" | ...,
  "parent": "...",
  "task": "...",             # 完整任务文本，不截断
  "system_prompt": "...",    # 完整系统提示词
  "messages": [ {role, content, tool_name, tool_call_id, timestamp}, ... ],
  "children": [...]
}
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from searchos.harness.telemetry.trajectory import ConversationMessage

logger = logging.getLogger(__name__)


class ConversationLogger:
    """层级化对话记录器 → conversation.json。

    每个 agent（orchestrator + sub-agents）有自己的消息列表，
    通过 parent/children 关系形成树。每次 log 后自动 flush 到磁盘。
    """

    def __init__(self, path: str | Path | None = None) -> None:
        self._path: Path | None = Path(path) if path else None
        self._agents: dict[str, dict] = {}  # agent_name → {messages, parent, task, children, system_prompt, agent_type}

    def set_path(self, path: str | Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def _per_agent_dir(self) -> Path | None:
        if self._path is None:
            return None
        return self._path.parent / "conversations"

    def _ensure_agent(
        self,
        agent_name: str,
        parent: str = "",
        task: str = "",
        system_prompt: str = "",
        agent_type: str = "",
    ) -> None:
        if agent_name not in self._agents:
            self._agents[agent_name] = {
                "agent_name": agent_name,
                "agent_type": agent_type,
                "parent": parent,
                "task": task,
                "system_prompt": system_prompt,
                "messages": [],
                "children": [],
            }
            if parent and parent in self._agents:
                if agent_name not in self._agents[parent]["children"]:
                    self._agents[parent]["children"].append(agent_name)
        else:
            rec = self._agents[agent_name]
            if system_prompt and not rec.get("system_prompt"):
                rec["system_prompt"] = system_prompt
            if agent_type and not rec.get("agent_type"):
                rec["agent_type"] = agent_type
            if task and not rec.get("task"):
                rec["task"] = task

    def log(self, message: ConversationMessage) -> None:
        """Record one conversation message under its agent."""
        if self._path is None:
            return
        if not message.timestamp:
            message.timestamp = datetime.now(timezone.utc).isoformat()

        agent = message.agent_name or "orchestrator"
        parent = message.parent_agent or ""
        self._ensure_agent(agent, parent)

        # Per-agent step index — the conversion never sets it (was always 0).
        message.step_index = len(self._agents[agent]["messages"])
        self._agents[agent]["messages"].append(message.model_dump())
        self._flush_per_agent(agent)

    def register_sub_agent(
        self,
        agent_name: str,
        parent: str,
        task: str,
        system_prompt: str = "",
        agent_type: str = "",
    ) -> None:
        """Register an agent with its system prompt before messages arrive."""
        self._ensure_agent(agent_name, parent, task, system_prompt, agent_type)
        if parent in self._agents and agent_name not in self._agents[parent]["children"]:
            self._agents[parent]["children"].append(agent_name)
        self._flush_per_agent(agent_name)

    def _flush_per_agent(self, agent_name: str) -> None:
        """Write one agent's full record (prompt + messages) to conversations/<agent>.json."""
        target_dir = self._per_agent_dir
        if target_dir is None:
            return
        rec = self._agents.get(agent_name)
        if rec is None:
            return
        target_dir.mkdir(parents=True, exist_ok=True)
        safe_name = agent_name.replace("/", "_")
        out_path = target_dir / f"{safe_name}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(rec, f, ensure_ascii=False, indent=2, default=str)

    def hydrate(self) -> None:
        """Load existing per-agent records from disk into memory so a
        follow-up turn *appends* to the prior conversation instead of
        overwriting it.

        A follow-up reuses the same ``session_id``/workspace, but each
        ``SearchSession.run`` builds a fresh ``ConversationLogger`` whose
        in-memory ``self._agents`` is empty — the first ``log`` on the
        orchestrator would otherwise ``_flush_per_agent`` an empty record
        over the existing ``conversations/orchestrator.json``. Idempotent;
        a no-op on a brand-new session (nothing on disk). Records already
        held in memory (this run) stay authoritative.
        """
        for name, rec in self.load().get("agents", {}).items():
            self._agents.setdefault(name, rec)

    def load(self) -> dict:
        """Load all per-agent conversations from conversations/<agent>.json."""
        target_dir = self._per_agent_dir
        if target_dir is None or not target_dir.exists():
            return {"agents": {}}
        agents: dict[str, dict] = {}
        for p in target_dir.glob("*.json"):
            with open(p, encoding="utf-8") as f:
                rec = json.load(f)
            agents[rec.get("agent_name", p.stem)] = rec
        return {"agents": agents}


def langchain_msg_to_conversation_msgs(msg: Any) -> list[ConversationMessage]:
    """Convert a LangChain BaseMessage into ConversationMessage(s).

    An AI message with tool_calls produces an assistant message plus
    one tool_call message per call.
    """
    results: list[ConversationMessage] = []
    msg_type = getattr(msg, "type", None)
    content = getattr(msg, "content", "")
    if isinstance(content, list):
        content = str(content)

    if msg_type == "human":
        results.append(ConversationMessage(role="user", content=content))
    elif msg_type == "ai":
        reasoning = ""
        extras = getattr(msg, "additional_kwargs", None) or {}
        if isinstance(extras, dict):
            reasoning = extras.get("reasoning_content", "") or ""
        results.append(ConversationMessage(
            role="assistant", content=content, reasoning=reasoning,
        ))
        for tc in getattr(msg, "tool_calls", []) or []:
            # `dict.get("k", default)` does NOT fall back when the key
            # exists with explicit None (langchain sometimes emits that
            # shape during streaming). Use `or ""` to coerce.
            results.append(ConversationMessage(
                role="tool_call",
                tool_name=(tc.get("name") or ""),
                tool_call_id=(tc.get("id") or ""),
                content=str(tc.get("args") or ""),
            ))
    elif msg_type == "tool":
        results.append(ConversationMessage(
            role="tool_result",
            tool_name=(getattr(msg, "name", "") or ""),
            tool_call_id=(getattr(msg, "tool_call_id", "") or ""),
            content=content,
        ))
    return results
