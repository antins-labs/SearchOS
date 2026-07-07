"""Anti-pattern library — parse / index / rank (read path only).

The curate write-path (LLM-maintained anti_patterns.md) lives in the offline
evolver, outside v1.

Each strategy skill has an optional sibling ``anti_patterns.md`` file
carrying that skill's accumulated failure lessons. Split from ``skill.md``
(which carries methodology only) so sub-agent prompts can inject a cheap
one-line index by default and pull details on demand via
``load_anti_patterns``.

File format::

    # Anti-patterns — <skill_name>

    ## Index
    - **<name>** — <summary> (×<observed>, <last_seen>)
    ...

    ## Details

    ### <name>
    **踩坑**: <what_failed>
    **原因**: <why>
    **改用**: <instead>   (optional)
    **观察**: <N> 次  |  **最后**: <YYYY-MM-DD>  |  **来源**: "<trace query>"

    ### <name>
    ...

The Details section is the source of truth; the Index is derived. We
re-derive on render rather than trusting LLM curate output to keep them
in sync.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


@dataclass
class AntiPatternEntry:
    """One failure lesson recorded against a skill."""

    name: str           # the ### heading — serves as identity
    summary: str = ""   # one-line description used in the Index
    what_failed: str = ""
    why: str = ""
    instead: str = ""
    observed: int = 1
    last_seen: str = ""   # "YYYY-MM-DD"
    source: str = ""      # trace query excerpt, optional

    def has_required_fields(self) -> bool:
        return bool(self.name and self.what_failed and self.why)

    def to_index_line(self) -> str:
        summary = self.summary or self.what_failed
        summary = summary.split("\n")[0].strip()
        if len(summary) > 80:
            summary = summary[:77] + "..."
        date = self.last_seen or "—"
        return f"- **{self.name}** — {summary} (×{self.observed}, {date})"


# ---------------------------------------------------------------------------
# Parse
# ---------------------------------------------------------------------------

_HEADER_RE = re.compile(r"^#\s+Anti-patterns\s*[—-]\s*(\S+)", re.MULTILINE)
_DETAILS_SECTION_RE = re.compile(r"^##\s+Details\s*\n", re.MULTILINE)
_DETAIL_HEADING_RE = re.compile(r"^###\s+(.+?)\s*$", re.MULTILINE)

# Field line regex — tolerant of bold markers and punctuation variants.
# e.g. "**踩坑**: ...", "踩坑：...", "❌ 踩坑: ..."
_FIELD_RE = re.compile(
    r"^\s*(?:\*\*)?\s*(?:[❌✅])?\s*(?P<key>[^\s:：*][^:：*]*?)\s*(?:\*\*)?\s*[:：]\s*(?P<val>.+?)\s*$",
    re.MULTILINE,
)


def parse_anti_patterns_md(
    text: str,
) -> tuple[str, list[AntiPatternEntry]]:
    """Parse an anti_patterns.md file body.

    Returns ``(skill_name, entries)``. Missing / empty text yields
    ``("", [])``. Parse errors return a best-effort partial result with a
    warning logged — never raises.
    """
    if not text or not text.strip():
        return "", []

    header_match = _HEADER_RE.search(text)
    skill_name = header_match.group(1).strip() if header_match else ""

    # Find the Details section; entries live between "## Details" and EOF
    # (or the next top-level "## " section — none expected, but be safe).
    details_match = _DETAILS_SECTION_RE.search(text)
    if not details_match:
        return skill_name, []
    details_start = details_match.end()
    next_top = re.search(r"^## (?!Details)", text[details_start:], re.MULTILINE)
    details_end = details_start + next_top.start() if next_top else len(text)
    details_body = text[details_start:details_end]

    # Split into per-entry blocks by ### headings
    heading_matches = list(_DETAIL_HEADING_RE.finditer(details_body))
    entries: list[AntiPatternEntry] = []
    for i, hm in enumerate(heading_matches):
        block_start = hm.end()
        block_end = (
            heading_matches[i + 1].start()
            if i + 1 < len(heading_matches)
            else len(details_body)
        )
        block = details_body[block_start:block_end]
        entry = _parse_detail_block(name=hm.group(1).strip(), block=block)
        if entry.has_required_fields():
            entries.append(entry)

    return skill_name, entries


def _parse_detail_block(*, name: str, block: str) -> AntiPatternEntry:
    """Extract fields from one ``### <name>`` detail block."""
    entry = AntiPatternEntry(name=name)
    for m in _FIELD_RE.finditer(block):
        key = m.group("key").strip().lower()
        val = m.group("val").strip()
        # Tolerate bold artifacts ``**key**`` captured into key
        key = key.replace("*", "").strip()
        if key in ("踩坑", "what failed", "failed", "what_failed"):
            entry.what_failed = val
        elif key in ("原因", "why", "reason"):
            entry.why = val
        elif key in ("改用", "instead", "use instead"):
            entry.instead = val
        elif key == "summary":
            entry.summary = val
        elif "观察" in key or key.startswith("observed") or key == "seen":
            # Meta line combines observed + last_seen + source with pipes.
            _parse_meta_line(entry, val)
        elif "最后" in key or key == "last" or key == "last_seen":
            entry.last_seen = _normalize_date(val)
        elif "来源" in key or key == "source":
            entry.source = val.strip('"').strip("'")
    if not entry.last_seen:
        entry.last_seen = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return entry


def _parse_meta_line(entry: AntiPatternEntry, val: str) -> None:
    """A meta line may look like ``3 次  |  **最后**: 2026-04-23  |  **来源**: "..."``.

    The first fragment is always ``observed``; subsequent ``|``-separated
    fragments carry ``最后`` / ``来源`` in either ``key: value`` or
    ``**key**: value`` form.
    """
    parts = [p.strip() for p in val.split("|") if p.strip()]
    if not parts:
        return
    # Observed count — extract first integer from the first fragment
    obs_match = re.search(r"\d+", parts[0])
    if obs_match:
        entry.observed = max(1, int(obs_match.group(0)))
    for frag in parts[1:]:
        m = re.match(r"\s*(?:\*\*)?(?P<k>[^:：*]+?)(?:\*\*)?\s*[:：]\s*(?P<v>.+)", frag)
        if not m:
            continue
        k = m.group("k").strip().lower().replace("*", "")
        v = m.group("v").strip()
        if "最后" in k or k in ("last", "last_seen"):
            entry.last_seen = _normalize_date(v)
        elif "来源" in k or k == "source":
            entry.source = v.strip('"').strip("'")


def _normalize_date(s: str) -> str:
    m = re.search(r"\d{4}-\d{2}-\d{2}", s)
    return m.group(0) if m else s.strip()


# ---------------------------------------------------------------------------
# Render index (for sub-agent system-prompt injection)
# ---------------------------------------------------------------------------

def index_markdown(entries: list[AntiPatternEntry]) -> str:
    """Render just the index lines — injected into sub-agent system prompts."""
    if not entries:
        return ""
    return "\n".join(e.to_index_line() for e in entries)


# ---------------------------------------------------------------------------
# Context-aware retrieval ranking
# ---------------------------------------------------------------------------

# Latin/digit runs match as words; each CJK ideograph is its own token.
# Without per-char CJK splitting, "搜索未来会议" and "搜索论文" would be
# two disjoint tokens — cross-entry overlap would always be zero and
# Jaccard ranking degenerates into observed-count sort.
_LATIN_RE = re.compile(r"[a-z0-9]+")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def _tokenize(text: str) -> set[str]:
    lower = text.lower()
    tokens: set[str] = set()
    for m in _LATIN_RE.findall(lower):
        if len(m) >= 2:
            tokens.add(m)
    for ch in _CJK_RE.findall(lower):
        tokens.add(ch)
    return tokens


def rank_by_context(
    entries: list[AntiPatternEntry], context: str,
) -> list[AntiPatternEntry]:
    """Reorder entries so those most related to ``context`` come first.

    Scoring: Jaccard(context tokens, entry tokens) — entry tokens drawn
    from name + summary + what_failed. Ties broken by observed count.
    """
    if not context.strip() or not entries:
        return list(entries)
    ctx_tokens = _tokenize(context)
    if not ctx_tokens:
        return list(entries)
    scored: list[tuple[float, int, AntiPatternEntry]] = []
    for e in entries:
        entry_tokens = _tokenize(f"{e.name} {e.summary} {e.what_failed}")
        if not entry_tokens:
            scored.append((0.0, e.observed, e))
            continue
        overlap = len(ctx_tokens & entry_tokens)
        union = len(ctx_tokens | entry_tokens)
        jaccard = overlap / union if union else 0.0
        scored.append((jaccard, e.observed, e))
    scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
    return [t[2] for t in scored]
