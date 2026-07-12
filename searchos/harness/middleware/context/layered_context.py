"""Deterministic context folding at ``search`` episode boundaries.

Completed episodes retain tool inputs and SOCM progress deltas. Tool outputs
stay in graph state and telemetry for replay, but are removed from model input.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any

from langchain.agents.middleware.types import AgentMiddleware
from langchain_core.messages import AIMessage, BaseMessage, SystemMessage

from searchos.harness.middleware._shared import unwrap_ai_message


@dataclass(frozen=True)
class ToolCallRecord:
    name: str
    args: dict[str, Any]


@dataclass(frozen=True)
class EpisodeMark:
    message_index: int
    evidence_ids: frozenset[str]
    filled_cells: frozenset[str]


@dataclass(frozen=True)
class EpisodeRecord:
    tool_calls: tuple[ToolCallRecord, ...]
    evidence_added: tuple[str, ...]
    coverage_delta: dict[str, int]


class SearchEpisodeMiddleware(AgentMiddleware):
    """Fold every completed ``search`` episode without an LLM summary."""

    name = "SearchEpisodeMiddleware"

    def __init__(
        self,
        workspace: Any,
        *,
        evidence_source: Any = None,
        history_max_tokens: int = 8_000,
    ) -> None:
        self._workspace = workspace
        self._evidence_source = evidence_source
        self._history_max_chars = history_max_tokens * 3
        self._active: EpisodeMark | None = None
        self._preamble: list[BaseMessage] = []
        self._episodes: list[EpisodeRecord] = []

    async def awrap_model_call(self, request: Any, handler: Callable) -> Any:
        messages = list(request.messages)
        model_request = request
        if self._episodes and self._active is not None:
            history = SystemMessage(
                content=self._render_history(),
                additional_kwargs={"sf_kind": "search_episode_history"},
            )
            current = messages[self._active.message_index:]
            model_request = replace(
                request,
                messages=_insert_history(self._preamble, history, current),
            )

        response = await handler(model_request)
        message = unwrap_ai_message(response)
        if any(call.name == "search" for call in _tool_calls(message)):
            if self._active is None:
                self._preamble = messages
            else:
                await self._close_episode(messages[self._active.message_index:])
            self._active = self._snapshot(len(messages))
        return response

    async def _close_episode(self, messages: list[BaseMessage]) -> None:
        source = self._evidence_source
        if source is not None and hasattr(source, "await_pending_flushes"):
            await source.await_pending_flushes(timeout=5.0)

        current = self._snapshot(-1)
        assert self._active is not None
        evidence_added = current.evidence_ids - self._active.evidence_ids
        self._episodes.append(EpisodeRecord(
            tool_calls=tuple(
                call for message in messages for call in _tool_calls(message)
            ),
            evidence_added=tuple(sorted(evidence_added)),
            coverage_delta=self._coverage_delta(
                baseline=self._active.filled_cells,
                evidence_ids=evidence_added,
            ),
        ))

    def _snapshot(self, message_index: int) -> EpisodeMark:
        state = self._workspace.load_state()
        cells = getattr(getattr(state, "coverage_map", None), "cells", {}) or {}
        filled = frozenset(
            key for key, cell in cells.items()
            if getattr(getattr(cell, "status", None), "value", "") == "filled"
        )
        source_ids = getattr(self._evidence_source, "committed_node_ids", ())
        return EpisodeMark(message_index, frozenset(source_ids or ()), filled)

    def _coverage_delta(
        self,
        *,
        baseline: frozenset[str],
        evidence_ids: frozenset[str],
    ) -> dict[str, int]:
        if not evidence_ids:
            return {}
        state = self._workspace.load_state()
        cells = getattr(getattr(state, "coverage_map", None), "cells", {}) or {}
        delta: dict[str, int] = {}
        for key, cell in cells.items():
            if key in baseline:
                continue
            if getattr(getattr(cell, "status", None), "value", "") != "filled":
                continue
            supporting = set(getattr(cell, "supporting_evidence_ids", ()) or ())
            if evidence_ids.isdisjoint(supporting):
                continue
            table_id = key.split("/", 1)[0] if "/" in key else "_default"
            delta[table_id] = delta.get(table_id, 0) + 1
        return dict(sorted(delta.items()))

    def _render_history(self) -> str:
        rendered = [_render_episode(i + 1, episode) for i, episode in enumerate(self._episodes)]
        selected: list[str] = []
        used = 0
        for text in reversed(rendered):
            if selected and used + len(text) > self._history_max_chars:
                break
            selected.append(text[:self._history_max_chars])
            used += len(selected[-1])
        selected.reverse()
        omitted = len(rendered) - len(selected)
        header = (
            "[PAST SEARCH EPISODES — tool outputs removed; facts remain in SOCM]"
        )
        if omitted:
            header += f"\n[{omitted} older episode(s) omitted]"
        return header + "\n\n" + "\n\n".join(selected)


def _tool_calls(message: BaseMessage) -> tuple[ToolCallRecord, ...]:
    if not isinstance(message, AIMessage):
        return ()
    records = []
    for call in getattr(message, "tool_calls", ()) or ():
        name = call.get("name", "") if isinstance(call, dict) else getattr(call, "name", "")
        args = call.get("args", {}) if isinstance(call, dict) else getattr(call, "args", {})
        if not isinstance(args, dict):
            args = {"raw": str(args)}
        records.append(ToolCallRecord(str(name), dict(args)))
    return tuple(records)


def _render_episode(number: int, episode: EpisodeRecord) -> str:
    lines = [f"[Search Episode {number}]", "tool_calls:"]
    lines.extend(
        f"- {call.name}({_compact_json(call.args)})"
        for call in episode.tool_calls
    )
    ids = ", ".join(episode.evidence_added)
    lines.append(f"evidence_added: [{ids}]")
    if episode.coverage_delta:
        lines.append("coverage_delta:")
        lines.extend(
            f"- {table_id}: +{count} cells"
            for table_id, count in episode.coverage_delta.items()
        )
    return "\n".join(lines)


def _compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def _insert_history(
    preamble: list[BaseMessage],
    history: SystemMessage,
    current: list[BaseMessage],
) -> list[BaseMessage]:
    """Keep system messages at the front for strict model providers."""
    index = 0
    while index < len(preamble) and getattr(preamble[index], "type", "") == "system":
        index += 1
    return [*preamble[:index], history, *preamble[index:], *current]


# Compatibility for existing imports and feature-flag wiring.
LayeredContextMiddleware = SearchEpisodeMiddleware


__all__ = [
    "EpisodeMark",
    "EpisodeRecord",
    "LayeredContextMiddleware",
    "SearchEpisodeMiddleware",
    "ToolCallRecord",
]
