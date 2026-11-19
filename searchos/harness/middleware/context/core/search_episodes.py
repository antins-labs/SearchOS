"""搜索 episode 的记录、工具调用解析与历史渲染。"""

import json
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from searchos.socm.refs import cell_parts


@dataclass(frozen=True)
class ToolCallRecord:
    name: str
    args: dict[str, Any]


@dataclass(frozen=True)
class EpisodeRecord:
    tool_calls: tuple[ToolCallRecord, ...]
    evidence_added: tuple[str, ...]
    coverage_delta: dict[str, int]


def tool_calls(message: BaseMessage) -> tuple[ToolCallRecord, ...]:
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


def render_episode(number: int, episode: EpisodeRecord) -> str:
    lines = [f"""[Search Episode {number}]""", "tool_calls:"]
    lines.extend(f"""- {call.name}({_compact_json(call.args)})""" for call in episode.tool_calls)
    ids = ", ".join(episode.evidence_added)
    lines.append(f"""evidence_added: [{ids}]""")
    if episode.coverage_delta:
        lines.append("coverage_delta:")
        lines.extend(
            f"""- {table_id}: +{count} cells""" for table_id, count in episode.coverage_delta.items()
        )
    return "\n".join(lines)


def _compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def insert_history(
    preamble: list[BaseMessage],
    history: BaseMessage,
    current: list[BaseMessage],
) -> list[BaseMessage]:
    """Insert episode history after any leading system messages."""
    index = 0
    while index < len(preamble) and getattr(preamble[index], "type", "") == "system":
        index += 1
    return [*preamble[:index], history, *preamble[index:], *current]


class SearchEpisodeHistory:
    def __init__(self, workspace: Any, evidence_source: Any, history_max_tokens: int) -> None:
        self._workspace = workspace
        self._evidence_source = evidence_source
        self._history_max_chars = history_max_tokens * 3

    def fold_messages(self, messages: list[BaseMessage]) -> tuple[list[BaseMessage], list[int]]:
        starts = [
            i
            for i, msg in enumerate(messages)
            if any(call.name == "search" for call in tool_calls(msg))
        ]
        folded = messages
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
            history = HumanMessage(
                content=self._render_history(episodes),
                additional_kwargs={
                    "sf_synthetic": True,
                    "sf_kind": "search_episode_history",
                },
            )
            # User corrections and existing compaction handoffs survive folding.
            preamble = messages[: starts[0]] + [
                msg for msg in messages[starts[0] : starts[-1]] if msg.type in {"human", "system"}
            ]
            folded = insert_history(preamble, history, messages[starts[-1] :])

        return folded, starts

    def record_message(self, message: Any, messages: list[BaseMessage], starts: list[int]) -> None:
        if any(call.name == "search" for call in tool_calls(message)):
            previous = {}
            if starts:
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
            table_id = cell_parts(key)[0]
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
        header = """[PAST SEARCH EPISODES — tool outputs removed; facts remain in SOCM]"""
        if omitted:
            header += f"""
[{omitted} older episode(s) omitted]"""
        episodes_text = "\n\n".join(selected)
        return f"""{header}

{episodes_text}"""
