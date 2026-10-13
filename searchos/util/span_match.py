"""Markup/whitespace-tolerant verbatim anchoring.

Fix candidate for ``evidence_extraction._provenance_fields`` (which does a
raw ``str.find`` and therefore never matches excerpts whose whitespace was
collapsed by ``_extract_context`` or reflowed by the extraction judge).
Validated offline by scripts/span_fix_dryrun.py (0%→87% anchoring on real runs).

Matching tiers, strict → loose; every tier returns a span in ORIGINAL page
coordinates via an offset map:
  exact    raw substring (current production behavior)
  ws       whitespace runs collapsed to one space, both sides
  ws_fold  ws + casefold
  alnum    alphanumeric-only + casefold (tolerates markup/punctuation drift)
"""

from __future__ import annotations

import re
from typing import Optional

_ALNUM_MIN_CHARS = 15  # below this an alnum-only match is too easy to trust


def _normalize(text: str, *, fold: bool, alnum: bool) -> tuple[str, list[int]]:
    """Collapse whitespace (or drop non-alnum); return (normalized, offsets)
    where offsets[i] is the original index of normalized char i."""
    chars: list[str] = []
    offsets: list[int] = []
    pending_space = False
    for i, ch in enumerate(text):
        if ch.isspace() or (alnum and not ch.isalnum()):
            pending_space = not alnum
            continue
        if pending_space and chars:
            chars.append(" ")
            offsets.append(offsets[-1] + 1)
        pending_space = False
        chars.append(ch.casefold() if fold else ch)
        offsets.append(i)
    return "".join(chars), offsets


def find_span(page_text: str, excerpt: str, *, browser_lines: bool = False) -> tuple[Optional[tuple[int, int]], Optional[str]]:
    """Locate *excerpt* in *page_text*; returns ((start, end), tier) or (None, None)."""
    if not page_text or not excerpt or not excerpt.strip():
        return None, None
    idx = page_text.find(excerpt)
    if idx >= 0:
        return (idx, idx + len(excerpt)), "exact"

    for tier, fold, alnum in (("ws", False, False), ("ws_fold", True, False), ("alnum", True, True)):
        norm_page, offsets = _normalize(page_text, fold=fold, alnum=alnum)
        norm_ex, _ = _normalize(excerpt, fold=fold, alnum=alnum)
        if not norm_ex or (alnum and len(norm_ex) < _ALNUM_MIN_CHARS):
            continue
        j = norm_page.find(norm_ex)
        if j >= 0:
            return (offsets[j], offsets[j + len(norm_ex) - 1] + 1), tier
    if browser_lines:
        # Browser-rendered L<N>: labels are presentation, not source words.
        # Keep the original offsets: persisted excerpts still include labels.
        chars, offsets = [], []
        end = 0
        for match in re.finditer(r"(?m)^L\d+: ", page_text):
            chars.append(page_text[end:match.start()])
            offsets.extend(range(end, match.start()))
            end = match.end()
        if end:
            chars.append(page_text[end:])
            offsets.extend(range(end, len(page_text)))
            span, tier = find_span("".join(chars), excerpt)
            if span is not None:
                return (offsets[span[0]], offsets[span[1] - 1] + 1), f"browser_{tier}"
    return None, None
