"""Session logger 的 agent 事件记录器；不参与功能装配。"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from searchos.harness.middleware.utils.messages import extract_tool_name, unwrap_ai_message
from searchos.harness.telemetry.state_delta import capture_state, state_delta


class AgentRecorder:
    def __init__(
        self, logger, *, agent_id: str, workspace=None, emit_started=False, conversation_logger=None
    ):
        self.context_recorder = ContextRecorder(agent_id, logger, conversation_logger)
        self.logger = logger
        self.agent_id = agent_id
        self.workspace = workspace
        self.emit_started = emit_started
        self._step_index = 0
        self._reasoning = ""

    def model_received(self, request):
        for message in getattr(request, "messages", ()):
            kind = getattr(message, "additional_kwargs", {}).get("sf_kind")
            if kind:
                self.context_recorder(str(message.content), kind)

    def model_completed(self, response):
        self._reasoning = reasoning_text(response)[:800]
        if self._reasoning and not getattr(unwrap_ai_message(response), "tool_calls", None):
            self.logger._append_raw(
                {
                    "type": "agent_final",
                    "agent": self.agent_id,
                    "reasoning": self._reasoning,
                }
            )

    def tool_started(self, request):
        call = request.tool_call
        name, args = extract_tool_name(request), call.get("args", {})
        index, reasoning = self._step_index, self._reasoning
        self._step_index += 1
        self._reasoning = ""
        if self.emit_started:
            self.logger._append_raw(
                {
                    "type": "tool_call_started",
                    "agent": self.agent_id,
                    "tool": name,
                    "tool_call_id": call.get("id", ""),
                    "args": args,
                }
            )
        return index, reasoning, capture_state(self.workspace)

    def tool_completed(self, request, result, started):
        index, reasoning, before = started
        delta = state_delta(before, capture_state(self.workspace))
        text = observation_text(result)
        self.logger._append_raw(
            {
                "type": "step",
                "agent": self.agent_id,
                "step_index": index,
                "timestamp": datetime.now(UTC).isoformat(),
                "reasoning": reasoning,
                "action": {
                    "name": extract_tool_name(request),
                    "args": request.tool_call.get("args", {}),
                },
                "observation": text,
                "observation_preview": text[:500],
                "state_delta": delta.model_dump(),
                "step_value": self.logger._compute_step_value(delta),
            }
        )
        self.logger._step_count += 1


def reasoning_text(response: Any) -> str:
    """Extract the LLM's reasoning text.

    Priority:
    1. additional_kwargs['reasoning_content'] — native thinking from
       models with enable_thinking (GLM-5, DeepSeek-R1). This is the
       highest-quality source: it's the model's actual chain-of-thought,
       separate from content, and doesn't enter conversation history.
    2. msg.content — prompt-instructed reasoning (## Thinking block).
       Fallback for models without native thinking.
    """
    msg = unwrap_ai_message(response)

    # Priority 1: native reasoning_content (from patched langchain)
    if hasattr(msg, "additional_kwargs"):
        reasoning = msg.additional_kwargs.get("reasoning_content", "")
        if reasoning:
            return reasoning

    # Priority 2: content-based reasoning (legacy / models without thinking)
    if not hasattr(msg, "content"):
        return ""
    content = msg.content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") in ("text", "thinking"):
                    parts.append(block.get("text") or block.get("thinking", ""))
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(parts).strip()
    return ""


def observation_text(result: Any) -> str:
    """Extract the readable text content from a tool result.

    Handles ToolMessage, AIMessage, dict, string — returns the actual
    content rather than the object repr.
    """
    # ToolMessage / AIMessage have .content attribute
    if hasattr(result, "content"):
        content = result.content
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            # List of content blocks (Claude format)
            parts = []
            for block in content:
                if isinstance(block, dict):
                    parts.append(block.get("text", str(block)))
                else:
                    parts.append(str(block))
            return "\n".join(parts)
        return str(content)
    # dict with content key
    if isinstance(result, dict) and "content" in result:
        return str(result["content"])
    # Plain string
    if isinstance(result, str):
        return result
    # Fallback
    return str(result)


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ContextRecorder:
    agent_id: str
    trajectory: Any = None
    conversation: Any = None

    def __call__(self, content: str, kind: str) -> None:
        if self.trajectory is not None:
            try:
                self.trajectory._append_raw(
                    {
                        "type": "harness",
                        "kind": "socm_inject" if kind == "socm_update" else kind,
                        "agent": self.agent_id,
                        "chars": len(content),
                        "preview": content[:500],
                    }
                )
            except Exception:
                logger.warning("Context trajectory write failed", exc_info=True)
        if self.conversation is not None:
            from searchos.harness.telemetry.trajectory import ConversationMessage

            try:
                self.conversation.log(
                    ConversationMessage(
                        role="user",
                        content=content,
                        agent_name=self.agent_id,
                        metadata={"synthetic": kind},
                    )
                )
            except Exception:
                logger.warning("Context conversation write failed", exc_info=True)
