"""Durable, coalesced final-answer events for file-tailing clients."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


def message_chunk_text(chunk: Any) -> str:
    """Return visible text from a LangChain message chunk without trimming it."""
    content = getattr(chunk, "content", chunk)
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict):
            text = block.get("text")
            if isinstance(text, str):
                parts.append(text)
    return "".join(parts)


class AnswerStreamEmitter:
    """Publish only final-answer text as a bounded set of durable UI events."""

    def __init__(
        self,
        emit: Callable[[dict[str, Any]], None],
        *,
        stream_prefix: str,
        flush_chars: int = 48,
    ) -> None:
        self._emit = emit
        self._stream_prefix = stream_prefix
        self._flush_chars = max(1, flush_chars)
        self._sequence = 0
        self._stream_id = ""
        self._buffer = ""
        self._active = False

    def push(self, delta: str) -> None:
        if not delta:
            return
        first_delta = not self._active
        if not self._active:
            self._sequence += 1
            self._stream_id = f"{self._stream_prefix}-{self._sequence}"
            self._active = True
            self._emit({
                "type": "answer_stream_start",
                "stream_id": self._stream_id,
                "phase": "final_answer",
            })
        self._buffer += delta
        if first_delta or len(self._buffer) >= self._flush_chars or "\n" in self._buffer:
            self.flush()

    def flush(self) -> None:
        if not self._buffer:
            return
        self._emit({
            "type": "answer_stream_delta",
            "stream_id": self._stream_id,
            "phase": "final_answer",
            "delta": self._buffer,
        })
        self._buffer = ""

    def finish(self) -> None:
        """Finish the current final-answer publication."""
        self.flush()
        self._active = False
