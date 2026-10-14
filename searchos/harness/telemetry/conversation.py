"""ConversationLogger: per-agent 完整对话记录。

每个 agent 一个 JSON：workspace/<session>/conversations/snapshots/<agent_name>.json
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
import os
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from typing import Any

from searchos.harness.telemetry.trajectory import ConversationMessage

logger = logging.getLogger(__name__)


class ConversationLogger:
    """层级化对话记录器 → conversation.json。

    每个 agent（orchestrator + sub-agents）有自己的消息列表，
    通过 parent/children 关系形成树。逐条追加日志，每 32 条及会话结束生成快照。
    """

    def __init__(self, path: str | Path | None = None) -> None:
        self._path: Path | None = Path(path) if path else None
        self._lock = RLock()
        self._dirty: set[str] = set()
        self._agents: dict[
            str, dict
        ] = {}  # agent_name → {messages, parent, task, children, system_prompt, agent_type}

    def set_path(self, path: str | Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def _per_agent_dir(self) -> Path | None:
        if self._path is None:
            return None
        folder = self._path.parent / "conversations"
        organize_conversations(folder)
        return folder

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
        with self._lock:
            self._log(message)

    def _log(self, message: ConversationMessage) -> None:
        """Record one conversation message under its agent."""
        if self._path is None:
            return
        if not message.timestamp:
            message.timestamp = datetime.now(UTC).isoformat()

        agent = message.agent_name or "orchestrator"
        parent = message.parent_agent or ""
        new_agent = agent not in self._agents
        self._ensure_agent(agent, parent)
        if new_agent:
            self._append(
                agent, {"meta": {k: v for k, v in self._agents[agent].items() if k != "messages"}}
            )
            self._flush_per_agent(agent)

        # Per-agent step index — the conversion never sets it (was always 0).
        message.step_index = len(self._agents[agent]["messages"])
        self._agents[agent]["messages"].append(message.model_dump())
        self._append(agent, {"message": self._agents[agent]["messages"][-1]})
        if len(self._agents[agent]["messages"]) % 32 == 0:
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
        with self._lock:
            self._register_sub_agent(agent_name, parent, task, system_prompt, agent_type)

    def _register_sub_agent(self, agent_name, parent, task, system_prompt, agent_type) -> None:
        self._ensure_agent(agent_name, parent, task, system_prompt, agent_type)
        if parent in self._agents and agent_name not in self._agents[parent]["children"]:
            self._agents[parent]["children"].append(agent_name)
        self._append(
            agent_name,
            {"meta": {k: v for k, v in self._agents[agent_name].items() if k != "messages"}},
        )
        if parent in self._agents:
            self._append(
                parent, {"meta": {k: v for k, v in self._agents[parent].items() if k != "messages"}}
            )
        self._flush_per_agent(agent_name)

    def _append(self, agent_name: str, entry: dict) -> None:
        folder = self._per_agent_dir
        if folder is None:
            return
        folder = folder / "journals"
        folder.mkdir(parents=True, exist_ok=True)
        safe_name = agent_name.replace("/", "_")
        path = folder / f"{safe_name}.jsonl"
        with path.open("a+b") as stream:
            end = stream.tell()
            # A crash can leave an incomplete tail; never join the next record to it.
            if end:
                stream.seek(end - 1)
                if stream.read(1) != b"\n":
                    cursor = end
                    while cursor:
                        start = max(0, cursor - 65536)
                        stream.seek(start)
                        chunk = stream.read(cursor - start)
                        newline = chunk.rfind(b"\n")
                        if newline >= 0:
                            stream.truncate(start + newline + 1)
                            break
                        cursor = start
                    else:
                        stream.truncate(0)
            stream.seek(0, 2)
            stream.write(
                (json.dumps(entry, ensure_ascii=False, default=str) + "\n").encode("utf-8")
            )
        self._dirty.add(agent_name)

    def flush(self) -> None:
        with self._lock:
            for name in list(self._dirty):
                self._flush_per_agent(name)

    def _flush_per_agent(self, agent_name: str) -> None:
        """Write one agent's full record (prompt + messages) to conversations/snapshots/<agent>.json."""
        target_dir = self._per_agent_dir
        if target_dir is None:
            return
        target_dir = target_dir / "snapshots"
        rec = self._agents.get(agent_name)
        if rec is None:
            return
        target_dir.mkdir(parents=True, exist_ok=True)
        safe_name = agent_name.replace("/", "_")
        out_path = target_dir / f"{safe_name}.json"
        journal = conversation_journal_path(out_path)
        payload = {**rec, "_journal_offset": journal.stat().st_size if journal.exists() else 0}
        temporary = out_path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, default=str, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, out_path)
        self._dirty.discard(agent_name)

    def hydrate(self) -> None:
        """Load existing per-agent records from disk into memory so a
        follow-up turn *appends* to the prior conversation instead of
        overwriting it.

        A follow-up reuses the same ``session_id``/workspace, but each
        ``SearchSession.run`` builds a fresh ``ConversationLogger`` whose
        in-memory ``self._agents`` is empty — the first ``log`` on the
        orchestrator would otherwise ``_flush_per_agent`` an empty record
        over the existing ``conversations/snapshots/orchestrator.json``. Idempotent;
        a no-op on a brand-new session (nothing on disk). Records already
        held in memory (this run) stay authoritative.
        """
        for name, rec in self.load().get("agents", {}).items():
            self._agents.setdefault(name, rec)

    def load(self) -> dict:
        """Load all per-agent conversations from conversations/snapshots/<agent>.json."""
        target_dir = self._per_agent_dir
        if target_dir is None or not target_dir.exists():
            return {"agents": {}}
        agents: dict[str, dict] = {}
        names = {p.stem for p in (target_dir / "snapshots").glob("*.json")} | {
            p.stem for p in (target_dir / "journals").glob("*.jsonl")
        }
        for name in names:
            rec = read_conversation(target_dir / "snapshots" / f"{name}.json")
            agents[rec.get("agent_name", name)] = rec
        return {"agents": agents}


def organize_conversations(folder: Path) -> None:
    """Move flat conversation files into their directories without rewriting data."""
    for suffix, directory in ((".json", "snapshots"), (".jsonl", "journals")):
        for source in folder.glob(f"*{suffix}"):
            target = folder / directory / source.name
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                # Exclusive creation avoids overwriting a concurrently published file.
                os.link(source, target)
            except FileExistsError:
                if not source.exists():
                    continue
                if not os.path.samefile(source, target):
                    raise FileExistsError(f"Conversation layout conflict: {target}")
            except FileNotFoundError:
                continue
            source.unlink(missing_ok=True)


def conversation_journal_path(snapshot: Path) -> Path:
    """Return the journal paired with a conversation snapshot."""
    return snapshot.parent.parent / "journals" / f"{snapshot.stem}.jsonl"


def read_conversation(path: Path) -> dict:
    """Read an atomic checkpoint plus every complete journal record after its watermark."""
    organize_conversations(path.parent.parent)
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        record = {"messages": []}
    offset = record.pop("_journal_offset", 0)
    try:
        with conversation_journal_path(path).open("rb") as stream:
            stream.seek(offset)
            for line in stream:
                if not line.endswith(b"\n"):
                    break
                entry = json.loads(line)
                if "meta" in entry:
                    record.update(entry["meta"])
                if "message" in entry:
                    record.setdefault("messages", []).append(entry["message"])
    except FileNotFoundError:
        pass
    return record


def langchain_msg_to_conversation_msgs(msg: Any) -> list[ConversationMessage]:
    """Convert a LangChain BaseMessage into ConversationMessage(s).

    An AI message with tool_calls produces an assistant message plus
    one tool_call message per call.
    """
    results: list[ConversationMessage] = []
    msg_type = getattr(msg, "type", None)
    content = getattr(msg, "content", "")

    if msg_type == "human":
        extras = getattr(msg, "additional_kwargs", {}) or {}
        metadata = {
            key: extras[f"sf_{key}"]
            for key in ("steer_id", "steer_mode", "steer_text") if f"sf_{key}" in extras
        }
        results.append(ConversationMessage(role="user", content=content, metadata=metadata))
    elif msg_type == "ai":
        reasoning = ""
        extras = getattr(msg, "additional_kwargs", None) or {}
        if isinstance(extras, dict):
            reasoning = extras.get("reasoning_content", "") or ""
        results.append(
            ConversationMessage(
                role="assistant",
                content=content,
                reasoning=reasoning,
            )
        )
        for tc in getattr(msg, "tool_calls", []) or []:
            # `dict.get("k", default)` does NOT fall back when the key
            # exists with explicit None (langchain sometimes emits that
            # shape during streaming). Use `or ""` to coerce.
            results.append(
                ConversationMessage(
                    role="tool_call",
                    tool_name=(tc.get("name") or ""),
                    tool_call_id=(tc.get("id") or ""),
                    content=str(tc.get("args") or ""),
                )
            )
    elif msg_type == "tool":
        results.append(
            ConversationMessage(
                role="tool_result",
                tool_name=(getattr(msg, "name", "") or ""),
                tool_call_id=(getattr(msg, "tool_call_id", "") or ""),
                content=content,
            )
        )
    return results
