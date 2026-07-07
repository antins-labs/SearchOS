"""Three-layer context management middleware for search agents.

Replaces DynamicTrimMiddleware with a structured approach:
  Layer 3: SOCM state snapshot (coverage gaps, evidence, open questions)
  Layer 2: Append-only episodic summaries of past search segments
  Layer 1: Current working memory (recent messages)

Cache-first design: prefix (system + L3 + L2) stays stable across LLM calls
within the same search segment, maximizing prompt cache hit rate.

Segmentation is done in awrap_model_call by scanning new messages for
search tool calls since the last model call.
"""

from __future__ import annotations

import logging
import re
from contextvars import ContextVar
from dataclasses import dataclass, field, replace
from typing import Any, Callable

from langchain.agents.middleware.types import AgentMiddleware
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, SystemMessage
from langchain_core.messages.utils import trim_messages

logger = logging.getLogger(__name__)

_SEARCH_TRIGGER_TOOLS = frozenset({"search"})

_SEGMENT_SUMMARY_PROMPT = """\
Summarize this search episode in 2-3 sentences. Cover: what was searched, \
key facts found (with numbers/names), and what was NOT found.

Search query: "{query}"
Tool: {tool}

Content:
{content}

Summary:"""

_segments_var: ContextVar[list["SearchSegment"] | None] = ContextVar(
    "sf_layered_segments", default=None
)


def get_segments() -> list["SearchSegment"]:
    return _segments_var.get() or []


@dataclass
class SearchSegment:
    segment_id: int
    trigger_query: str
    trigger_tool: str
    messages: list[BaseMessage] = field(default_factory=list)
    summary: str = ""
    keywords: list[str] = field(default_factory=list)


class LayeredContextMiddleware(AgentMiddleware):
    """Three-layer context assembly middleware.

    Segmentation happens in awrap_model_call: before each LLM call, scan
    messages added since the last call for search tool completions. Each
    search tool result boundary closes the current segment and opens a new one.

    The frozen prefix (Layer 3 + Layer 2) is append-only and only changes at
    segment boundaries, maximizing prompt cache hit rate.
    """

    name: str = "LayeredContextMiddleware"

    def __init__(
        self,
        judge_model: BaseChatModel,
        workspace: Any,
        *,
        layer1_max_tokens: int = 50_000,
        layer2_max_tokens: int = 8_000,
        layer3_max_tokens: int = 2_000,
    ) -> None:
        self._judge = judge_model
        self._workspace = workspace
        self._layer1_max_tokens = layer1_max_tokens
        self._layer2_max_tokens = layer2_max_tokens
        self._layer3_max_tokens = layer3_max_tokens

        self._segments: list[SearchSegment] = []
        self._current_segment_start: int = 0
        self._frozen_layer3: str = ""
        self._frozen_layer2_parts: list[str] = []
        self._frozen_prefix: str = ""
        self._last_scanned_msg_idx: int = 0
        self._call_count: int = 0

        _segments_var.set(self._segments)

    async def awrap_model_call(self, request: Any, handler: Callable) -> Any:
        self._call_count += 1
        messages = request.messages

        await self._scan_for_segment_boundaries(messages)

        if not self._segments and not self._frozen_prefix:
            estimated = self._estimate_tokens(messages)
            if estimated <= self._layer1_max_tokens + self._layer2_max_tokens:
                return await handler(request)

        layer1 = self._get_layer1(messages)
        assembled = self._assemble(layer1, request)

        total_est = self._estimate_tokens(assembled)
        logger.debug(
            "LayeredContext call #%d: %d segments, prefix=%d chars, "
            "L1=%d msgs, total~%d tokens",
            self._call_count, len(self._segments), len(self._frozen_prefix),
            len(layer1), total_est,
        )

        return await handler(replace(request, messages=assembled))

    # ---- Segment detection by scanning messages ----

    async def _scan_for_segment_boundaries(
        self, messages: list[BaseMessage]
    ) -> None:
        new_msgs = messages[self._last_scanned_msg_idx:]
        self._last_scanned_msg_idx = len(messages)

        for i, msg in enumerate(new_msgs):
            if not isinstance(msg, AIMessage):
                continue
            tool_calls = getattr(msg, "tool_calls", None) or []
            for tc in tool_calls:
                tc_name = tc.get("name", "") if isinstance(tc, dict) else getattr(tc, "name", "")
                if tc_name not in _SEARCH_TRIGGER_TOOLS:
                    continue
                tc_args = tc.get("args", {}) if isinstance(tc, dict) else getattr(tc, "args", {})
                query = tc_args.get("query", "") if isinstance(tc_args, dict) else ""

                abs_idx = self._last_scanned_msg_idx - len(new_msgs) + i
                if abs_idx > self._current_segment_start + 1:
                    seg_messages = list(messages[self._current_segment_start:abs_idx])
                    await self._close_segment(tc_name, query, seg_messages)
                    self._current_segment_start = abs_idx

    async def _close_segment(
        self, tool_name: str, query: str, seg_messages: list[BaseMessage]
    ) -> None:
        if not seg_messages:
            return

        seg = SearchSegment(
            segment_id=len(self._segments),
            trigger_query=query,
            trigger_tool=tool_name,
            messages=seg_messages,
        )

        seg.summary = await self._summarize_segment(seg)
        seg.keywords = self._extract_keywords(query)
        self._segments.append(seg)

        self._frozen_layer2_parts.append(
            f"[Episode {seg.segment_id}] ({seg.trigger_tool}: "
            f"{seg.trigger_query[:60]})\n{seg.summary}"
        )
        self._maybe_merge_oldest()
        self._refresh_layer3()
        self._rebuild_prefix()

        logger.info(
            "Closed segment %d: query=%s, %d msgs, summary=%d chars",
            seg.segment_id, query[:50], len(seg_messages), len(seg.summary),
        )

        try:
            import json
            from pathlib import Path
            log_dir = Path(str(self._workspace.path)) / "agent_logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            seg_log = log_dir / "layered_segments.jsonl"
            with open(seg_log, "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "segment_id": seg.segment_id,
                    "query": seg.trigger_query[:100],
                    "tool": seg.trigger_tool,
                    "msg_count": len(seg_messages),
                    "summary": seg.summary[:200],
                }, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def _refresh_layer3(self) -> None:
        try:
            state = self._workspace.load_state()
            self._frozen_layer3 = _build_compact_socm_summary(state)
        except Exception:
            logger.warning("Failed to refresh Layer 3 SOCM summary", exc_info=True)

    def _rebuild_prefix(self) -> None:
        parts = []
        if self._frozen_layer3:
            parts.append(self._frozen_layer3)
        if self._frozen_layer2_parts:
            header = (
                "[EPISODIC MEMORY — Past Search Episodes]\n"
                "These are summaries of your earlier searches. The original "
                "content has been compressed. Use look_back(segment_id) to "
                "retrieve full details from any episode.\n"
            )
            parts.append(header + "\n\n".join(self._frozen_layer2_parts))
        self._frozen_prefix = "\n\n".join(parts) if parts else ""

    def _maybe_merge_oldest(self) -> None:
        total = sum(self._estimate_tokens_str(p) for p in self._frozen_layer2_parts)
        while total > self._layer2_max_tokens and len(self._frozen_layer2_parts) >= 2:
            a = self._frozen_layer2_parts.pop(0)
            b = self._frozen_layer2_parts.pop(0)
            merged = self._merge_two_summaries(a, b)
            self._frozen_layer2_parts.insert(0, merged)
            total = sum(self._estimate_tokens_str(p) for p in self._frozen_layer2_parts)

    @staticmethod
    def _merge_two_summaries(a: str, b: str) -> str:
        first_lines_a = a.split("\n")[0] if a else ""
        first_lines_b = b.split("\n")[0] if b else ""
        summary_a = a.split("\n", 1)[1].strip() if "\n" in a else a
        summary_b = b.split("\n", 1)[1].strip() if "\n" in b else b
        return (
            f"[Merged Episodes] {first_lines_a} + {first_lines_b}\n"
            f"{summary_a[:200]} | {summary_b[:200]}"
        )

    # ---- Summarization ----

    async def _summarize_segment(self, seg: SearchSegment) -> str:
        raw_tokens = self._estimate_tokens(seg.messages)
        if raw_tokens < 800:
            return self._rule_based_summary(seg)

        content = self._messages_to_text(seg.messages, max_chars=6000)
        prompt = _SEGMENT_SUMMARY_PROMPT.format(
            query=seg.trigger_query,
            tool=seg.trigger_tool,
            content=content,
        )
        try:
            resp = await self._judge.ainvoke([{"role": "user", "content": prompt}])
            text = resp.content if hasattr(resp, "content") else str(resp)
            return text[:1500]
        except Exception:
            logger.warning(
                "Segment summarization failed, using rule-based", exc_info=True
            )
            return self._rule_based_summary(seg)

    @staticmethod
    def _rule_based_summary(seg: SearchSegment) -> str:
        parts = [f"Searched: {seg.trigger_query}"]
        for m in seg.messages:
            text = str(m.content) if hasattr(m, "content") else ""
            urls = re.findall(r"https?://[^\s\)\"']+", text)
            if urls:
                parts.append(f"URL: {urls[0][:100]}")
                break
        for m in seg.messages:
            text = str(m.content) if hasattr(m, "content") else ""
            facts = re.findall(r"[^.!?\n]{10,80}(?:\d[\d,.]+|%|\$)", text)
            for f in facts[:3]:
                parts.append(f.strip())
        return " | ".join(parts)[:500]

    # ---- Assembly ----

    def _get_layer1(self, messages: list[BaseMessage]) -> list[BaseMessage]:
        layer1 = list(messages[self._current_segment_start:])
        estimated = self._estimate_tokens(layer1)
        if estimated <= self._layer1_max_tokens:
            return layer1
        try:
            return trim_messages(
                layer1,
                strategy="last",
                max_tokens=self._layer1_max_tokens,
                start_on="human",
                end_on=["human", "tool"],
                include_system=True,
                token_counter=self._estimate_tokens,
            )
        except Exception:
            return layer1[-40:]

    def _assemble(
        self,
        layer1: list[BaseMessage],
        original_request: Any,
    ) -> list[BaseMessage]:
        all_msgs = original_request.messages
        system_msgs = [
            m for m in all_msgs if hasattr(m, "type") and m.type == "system"
        ]

        if self._frozen_prefix:
            context_msg = SystemMessage(content=self._frozen_prefix)
            return system_msgs + [context_msg] + layer1
        return system_msgs + layer1

    # ---- Utilities ----

    @staticmethod
    def _extract_keywords(query: str) -> list[str]:
        words = re.findall(r"\w{2,}", query.lower())
        stopwords = {
            "the", "is", "at", "in", "of", "and", "or", "to", "for",
            "what", "how", "who", "which", "a", "an",
        }
        return [w for w in words if w not in stopwords][:10]

    @staticmethod
    def _estimate_tokens(messages: list[BaseMessage]) -> int:
        total = sum(len(str(m.content)) for m in messages)
        return int(total / 2.5)

    @staticmethod
    def _estimate_tokens_str(text: str) -> int:
        return int(len(text) / 2.5)

    @staticmethod
    def _messages_to_text(messages: list[BaseMessage], max_chars: int = 6000) -> str:
        parts = []
        total = 0
        for m in messages:
            text = str(m.content) if hasattr(m, "content") else ""
            role = getattr(m, "type", "unknown")
            chunk = f"[{role}] {text[:1500]}"
            if total + len(chunk) > max_chars:
                break
            parts.append(chunk)
            total += len(chunk)
        return "\n".join(parts)


def _build_compact_socm_summary(state: Any) -> str:
    from searchos.socm.views import SearchStateSnapshot
    from searchos.socm.views import render_compact_summary
    snap = SearchStateSnapshot.from_state(state)
    return render_compact_summary(snap)
