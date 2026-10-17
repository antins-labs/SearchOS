"""SOCM · Failure / Strategy Memory (paper §Failure Memory).

Anti-pattern records (atomic failure signals, deduped by signature) plus
LLM-distilled post-mortem summaries — propagated to later sub-agents so they
steer around known dead ends. NOT a positive-strategy store: reusable
methodology lives in the Skill Library.
"""

from __future__ import annotations

import time
from enum import Enum
from typing import Any
from urllib.parse import urlparse

from pydantic import Field

from searchos.util.base_model import CamelModel


class AntiPatternKind(str, Enum):
    QUERY = "query"    # query text that repeatedly yields nothing new
    SOURCE = "source"  # domain returning placeholder / paywalled content
    SKILL = "skill"    # skill that fails for the current cell
    BRANCH = "branch"  # a sub-tree that's all dropped
    CLAIM = "claim"    # rejected evidence claim (no re-cite)


class AntiPatternScope(CamelModel):
    """Where an anti-pattern applies. ``global_scope`` serializes as
    ``"global"`` (the Python word is reserved)."""
    target_cells: list[str] = Field(default_factory=list)  # "entity.attribute" keys
    global_scope: bool = Field(default=False, alias="global")


class StrategyPattern(CamelModel):
    """Anti-pattern record — only entries proven ineffective this session.
    No ``effective`` flag, no free-form pattern text (those belong to skills)."""

    id: str = ""
    kind: AntiPatternKind = AntiPatternKind.QUERY
    signature: str = ""  # normalized key (query / domain / skill_id / subtree / ev_id)
    scope: AntiPatternScope = Field(default_factory=AntiPatternScope)
    reason: str = ""     # NL "why it failed"
    observed_count: int = 1
    first_seen: float = 0.0
    last_seen: float = 0.0
    created_by: str = ""  # perception | broker | orchestrator | sensor


class FailureMemory(CamelModel):
    """Post-mortem written after a sub-agent fails — the LLM-distilled "why"
    + "what to do instead", so the next agent changes strategy rather than
    just dodging the exact signature. Stored separately from ``patterns`` so
    StrategyMemory.record dedup stays untouched."""

    id: str = ""
    source: str = "post_mortem"
    failure_class: str = ""          # e.g. "source_blocks_anonymous"
    what_failed: str = ""            # one line, <=500 chars
    advice: str = ""                 # one-line actionable advice, <=500 chars
    do_not_retry: list[str] = Field(default_factory=list)  # ["search_query: X", "source: Y"]
    applies_to: str = "global"       # global | entity:<name> | cell:<entity>.<attr>
    confidence: str = "medium"       # low | medium | high
    created_at: float = 0.0
    superseded: bool = False


class StrategyMemory(CamelModel):
    """Anti-pattern store. Dedup by (kind, signature) + observed_count."""

    patterns: list[StrategyPattern] = Field(default_factory=list)
    failure_memories: list[FailureMemory] = Field(default_factory=list)

    def record(self, anti_pattern: StrategyPattern) -> StrategyPattern:
        """Dedup-aware write: same (kind, signature) bumps observed_count +
        last_seen; a fresh entry gets first/last_seen stamped if left zero."""
        now = time.time()
        if anti_pattern.signature:
            for existing in self.patterns:
                if (existing.kind == anti_pattern.kind
                        and existing.signature == anti_pattern.signature):
                    existing.observed_count += 1
                    existing.last_seen = now
                    return existing
        if anti_pattern.first_seen == 0.0:
            anti_pattern.first_seen = now
        anti_pattern.last_seen = now
        self.patterns.append(anti_pattern)
        return anti_pattern

    def by_kind(self, kind: AntiPatternKind | str) -> list[StrategyPattern]:
        key = kind.value if isinstance(kind, AntiPatternKind) else kind
        return [p for p in self.patterns if p.kind == key]


# ---------------------------------------------------------------------------
# Write helpers — the atomic StrategyMemory write contract. Sensors /
# middleware call these so detection sites stay free of persistence logic.
# ---------------------------------------------------------------------------


def normalize_source_signature(source_url: str) -> str:
    """Return the host-level signature used for source anti-patterns."""
    raw = (source_url or "").strip()
    if not raw:
        return ""
    try:
        parsed = urlparse(raw)
        host = parsed.netloc or parsed.path
    except Exception:
        host = raw
    host = host.lower().strip()
    if host.startswith("www."):
        host = host[4:]
    return host


def record_strategy_pattern(
    workspace: Any,
    *,
    kind: AntiPatternKind | str,
    signature: str,
    reason: str = "",
    scope: AntiPatternScope | None = None,
    target_cells: list[str] | None = None,
    global_scope: bool | None = None,
    created_by: str = "sensor",
) -> StrategyPattern | None:
    """Record a StrategyPattern through WorkspaceManager.atomic_update_state.

    Returns the stored pattern when possible. Returns None on missing inputs or
    write failure; callers are sensors/middleware and should never crash the
    agent loop because strategy logging failed.
    """
    if workspace is None:
        return None
    sig = (signature or "").strip()
    if not sig:
        return None

    if not isinstance(kind, AntiPatternKind):
        try:
            kind = AntiPatternKind(str(kind))
        except ValueError:
            return None

    if scope is None:
        cells = list(target_cells or [])
        scope = AntiPatternScope(
            target_cells=cells,
            global_scope=bool(global_scope) if global_scope is not None else not cells,
        )

    stored: dict[str, StrategyPattern | None] = {"value": None}

    def _apply(state: Any) -> Any:
        stored["value"] = state.strategy_log.record(StrategyPattern(
            kind=kind,
            signature=sig,
            scope=scope,
            reason=(reason or "").strip(),
            created_by=created_by,
        ))
        return state

    try:
        workspace.atomic_update_state(_apply)
    except Exception:
        return None
    return stored["value"]


def record_source_antipattern(
    workspace: Any,
    source_url: str,
    *,
    reason: str,
    created_by: str = "extraction",
) -> StrategyPattern | None:
    """Record a host-level source anti-pattern."""
    return record_strategy_pattern(
        workspace,
        kind=AntiPatternKind.SOURCE,
        signature=normalize_source_signature(source_url),
        reason=reason,
        global_scope=True,
        created_by=created_by,
    )
