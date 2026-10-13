"""原文摘录定位与数值支持检查。"""

from __future__ import annotations

import re

# 仅过滤整个单元格为空值标记的情况，不影响日期或带连字符的文本。
_NULL_VALUES = {"", "none", "null", "n/a", "/", "-", "–", "—", "--"}


def _provenance_fields(page_text: str, snippet: str) -> tuple[tuple[int, int] | None, str]:
    """Return (anchored span of snippet in page_text, sha1 text_hash).
    Tolerant matching — _extract_context collapses whitespace and judge
    excerpts arrive reflowed, so a raw find() never anchored in practice."""
    import hashlib

    from searchos.util.span_match import find_span

    if not snippet:
        return None, ""
    text_hash = f"sha1:{hashlib.sha1(snippet.encode('utf-8')).hexdigest()}"
    if not page_text:
        return None, text_hash
    span, _tier = find_span(page_text, snippet)
    return span, text_hash


def _anchored_excerpt(
    page_text: str,
    llm_excerpt: str,
    value: str,
    entity: str,
    attribute: str = "",
) -> tuple[str, tuple[int, int] | None, str]:
    """Excerpt to persist: the LLM-provided one if it anchors, else the
    harness-extracted context window when THAT anchors (LLM copies reflow
    or paraphrase too far to recover)."""
    excerpt = llm_excerpt or _extract_context(page_text, value, entity, attribute)
    span, text_hash = _provenance_fields(page_text, excerpt)
    if span is None and llm_excerpt:
        ctx = _extract_context(page_text, value, entity, attribute)
        if ctx:
            ctx_span, ctx_hash = _provenance_fields(page_text, ctx)
            if ctx_span is not None:
                return ctx, ctx_span, ctx_hash
    return excerpt, span, text_hash


def _fold_digits(s: str) -> str:
    """NFKC-fold and strip thousand separators so page and value numbers
    compare on digits alone ("673,622,371" == "673622371", full-width too)."""
    import unicodedata

    s = unicodedata.normalize("NFKC", s or "")
    return s.replace(",", "").replace("，", "")


def _ungrounded_number(page_text: str, value: str) -> str | None:
    """Reason string when a value's significant numbers are nowhere on the page.

    The zh_016 failure mode — one templated price ("全价票100元/人") stamped
    onto dozens of rows whose cited page is a name-list with no prices —
    satisfies every prompt-side rule but cannot satisfy this one. Only tokens
    of >=3 digits are checked: short tokens (day-of-month, list indexes,
    "3.5" split by the decimal point) false-positive; the observed
    fabrications are prices / counts / amounts. Values without such tokens
    pass (textual cells are governed by the excerpt rules instead)."""
    tokens = [t for t in re.findall(r"\d+", _fold_digits(value)) if len(t) >= 3]
    if not tokens:
        return None
    page = _fold_digits(page_text)
    missing = [t for t in tokens if t not in page]
    if missing:
        return "number_not_on_page:" + ",".join(missing[:3])
    return None


def _extract_context(
    page_text: str,
    value: str,
    entity: str,
    attribute: str = "",
    window: int = 120,
) -> str:
    """Return a short text window around the fact for offline verification.

    The window centers on the value occurrence NEAREST an entity mention, not
    the first one on the page: short generic values ("5A", "朝阳区",
    "9:00-18:00") recur across a page, and the first hit is routinely another
    entity's statement."""
    if not page_text:
        return ""
    haystack = page_text

    def _positions(needle: str) -> list[int]:
        if not needle or len(needle) < 2:
            return []
        pos = [m.start() for m in re.finditer(re.escape(needle), haystack)]
        if pos:
            return pos
        lowered = haystack.lower()
        return [m.start() for m in re.finditer(re.escape(needle.lower()), lowered)]

    def _window_at(idx: int, length: int) -> str:
        start = max(0, idx - window)
        end = min(len(haystack), idx + length + window)
        return " ".join(haystack[start:end].split())

    # Scraped pages carry a "Title: … URL Source: … Markdown Content:"
    # preamble; anything worth quoting is restated in the body, and viewers
    # strip the preamble — so prefer body occurrences when any exist.
    m = re.search(r"Markdown Content:\s*", haystack)
    body_start = m.end() if m else 0

    def _prefer_body(pos: list[int]) -> list[int]:
        body = [p for p in pos if p >= body_start]
        return body or pos

    val_pos = _prefer_body(_positions(value))
    ent_pos = _prefer_body(_positions(entity))
    if val_pos and ent_pos:
        idx = min(val_pos, key=lambda v: min(abs(v - e) for e in ent_pos))
        return _window_at(idx, len(value))
    if val_pos:
        return _window_at(val_pos[0], len(value))
    if ent_pos:
        return _window_at(ent_pos[0], len(entity))
    return ""
