"""Deterministic context folding at ``search`` episode boundaries.

Completed episodes retain tool inputs and SOCM progress deltas. Tool outputs
stay in graph state and telemetry for replay, but are removed from model input.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Any

from langchain.agents.middleware.types import AgentMiddleware
from langchain_core.messages import SystemMessage

from searchos.harness.middleware.context.core.models import EpisodeRecord
from searchos.harness.middleware.context.utils.episodes import (
    insert_history,
    render_episode,
    tool_calls,
)
from searchos.harness.middleware.utils.messages import unwrap_ai_message


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

    async def awrap_model_call(self, request: Any, handler: Callable) -> Any:
        # Reconstruct from the active checkpoint history. Compaction may remove any
        # previous boundary; no cached indices or preamble may override its handoff.
        messages = list(request.messages)
        starts = [
            i
            for i, msg in enumerate(messages)
            if any(call.name == "search" for call in tool_calls(msg))
        ]
        model_request = request
        if len(starts) > 1:
            episodes = []
            for start, end in zip(starts, starts[1:]):
                metadata = messages[end].additional_kwargs.get("sf_search_episode", {})
                record = metadata.get("previous", {})
                episodes.append(
                    EpisodeRecord(
                        tool_calls=tuple(
                            call for msg in messages[start:end] for call in tool_calls(msg)
                        ),
                        evidence_added=tuple(record.get("evidence_added", ())),
                        coverage_delta=dict(record.get("coverage_delta", {})),
                    )
                )
            history = SystemMessage(
                content=self._render_history(episodes),
                additional_kwargs={"sf_kind": "search_episode_history"},
            )
            # User corrections and existing compaction handoffs survive folding.
            preamble = messages[: starts[0]] + [
                msg for msg in messages[starts[0] : starts[-1]] if msg.type in {"human", "system"}
            ]
            model_request = replace(
                request,
                messages=insert_history(
                    preamble,
                    history,
                    messages[starts[-1] :],
                ),
            )

        response = await handler(model_request)
        message = unwrap_ai_message(response)
        if any(call.name == "search" for call in tool_calls(message)):
            previous = {}
            if starts:
                source = self._evidence_source
                if source is not None and hasattr(source, "await_idle"):
                    await source.await_idle(timeout=5.0)
                baseline = messages[starts[-1]].additional_kwargs.get("sf_search_episode", {})
                snapshot = self._snapshot()
                # Missing metadata on legacy history cannot justify a fabricated delta.
                if "evidence_ids" in baseline:
                    added = frozenset(snapshot["evidence_ids"]) - frozenset(
                        baseline["evidence_ids"]
                    )
                    previous = {
                        "evidence_added": sorted(added),
                        "coverage_delta": self._coverage_delta(
                            baseline=frozenset(baseline.get("filled_cells", ())),
                            evidence_ids=added,
                        ),
                    }
            # Plain JSON metadata persists with the accepted AIMessage in checkpoint.
            message.additional_kwargs = {
                **message.additional_kwargs,
                "sf_search_episode": {**self._snapshot(), "previous": previous},
            }
        return response

    def _snapshot(self) -> dict[str, list[str]]:
        state = self._workspace.load_state()
        cells = getattr(getattr(state, "coverage_map", None), "cells", {}) or {}
        filled = sorted(
            key
            for key, cell in cells.items()
            if getattr(getattr(cell, "status", None), "value", "") == "filled"
        )
        source_ids = getattr(self._evidence_source, "committed_node_ids", ())
        return {"evidence_ids": sorted(source_ids or ()), "filled_cells": filled}

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

    def _render_history(self, episodes: list[EpisodeRecord]) -> str:
        rendered = [render_episode(i + 1, episode) for i, episode in enumerate(episodes)]
        selected: list[str] = []
        used = 0
        for text in reversed(rendered):
            if selected and used + len(text) > self._history_max_chars:
                break
            selected.append(text[: self._history_max_chars])
            used += len(selected[-1])
        selected.reverse()
        omitted = len(rendered) - len(selected)
        header = "[PAST SEARCH EPISODES — tool outputs removed; facts remain in SOCM]"
        if omitted:
            header += f"\n[{omitted} older episode(s) omitted]"
        return header + "\n\n" + "\n\n".join(selected)
