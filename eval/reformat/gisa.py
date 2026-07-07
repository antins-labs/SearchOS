"""GISA-specific reformat: dispatch on the question's answer_type.

GISA grades four answer shapes (table / list / set / item) with different
mechanics — list and set are scored on the LAST column, item on the first
row — so a multi-column table output zeros any non-table question. Table
questions reuse the shared multi-table join in core; the other shapes get
a dedicated reduce prompt plus mechanical shape validation with retry.
"""

from __future__ import annotations

import logging
import re
from io import StringIO
from typing import Optional

import pandas as pd

from eval.reformat.core import (
    _strip_fence,
    invoke_reformat_model,
    join_and_reformat_with_llm,
    strip_citations,
)

logger = logging.getLogger(__name__)

_SHAPE_DIRECTIVES = {
    "list": (
        "a single-column TSV: one header line naming what the items are, "
        "then ONE item per line, in the order the question requires",
        "Item\nfirst item\nsecond item\nthird item",
    ),
    "set": (
        "a single-column TSV: one header line naming what the items are, "
        "then ONE item per line (order does not matter)",
        "Item\none item\nanother item",
    ),
    "item": (
        "a single-value TSV: one header line, then exactly ONE line holding "
        "the single answer value",
        "Answer\nthe single value",
    ),
}

_REDUCE_PROMPT = """\
You are producing the FINAL answer for a benchmark question, in a strict shape.

Below is a research report (prose and/or markdown tables) holding the data \
needed to answer. Reduce it to the answer — do NOT reproduce the report's \
table layout.

Required shape: {shape_directive}.

Rules:
1. Apply EVERY constraint the question states (time window, category, \
eligibility, jurisdiction, ...) before answering — drop anything that fails \
any stated constraint, even if the report lists it.
2. If the question asks for a ranked subset (top-N / first-N by some \
quantity), rank by that quantity using the report's data, keep exactly N.
3. If the question dictates an ordering, order the output lines accordingly \
— sort by the relevant quantity from the report BEFORE projecting it away. \
Sort directive: {sort_block}
4. Output ONLY the identifier/value the question asks for — no extra \
columns, no quantities alongside names, no rank prefixes, no units unless \
the value itself carries one.
5. When the question names entities or prescribes placeholder words, echo \
them verbatim — exact spelling, punctuation and suffixes.
6. Drop any [N] / 【N】 citation markers.
{item_rule}
{aggregation_block}Output: a single fenced block, exactly:
```tsv
{example_layout}
```
No commentary outside the block.

==== Question ====
{original_query}

==== Hard constraints (parsed from the question) ====
{filters_block}

==== Report ====
{report}
"""

_ITEM_RULE = (
    "7. The question has exactly ONE answer value. If the report holds a "
    "candidate table, apply the question's filters/aggregation to reduce it "
    "to that single value.\n"
)

_COUNT_QUESTION_RE = re.compile(
    r"(at least \w+ times|two or more|more than once|multiple times|"
    r"won .{0,20}(twice|two times|\d+ times)|"
    r"两次及以上|至少\s*[两二三四五\d]+\s*次|不少于\s*\d+\s*次|多次)",
    re.IGNORECASE,
)


def _aggregation_hint(question: str, report: str) -> str:
    """Code-computed occurrence counts for count-shaped questions.

    gisa#29: the data table was complete and correct ("who won >=2 times"),
    but the reduce LLM mis-counted across 18 rows and named the wrong
    person. When the question asks about repeated occurrences, count value
    frequencies per column deterministically and hand the LLM the tally —
    it keeps the filtering/selection job, but no longer counts by eye.
    Triggered by question SHAPE (count phrasing), never by content."""
    if not _COUNT_QUESTION_RE.search(question or ""):
        return ""
    from collections import Counter
    from eval.reformat.core import extract_all_tables
    tables = extract_all_tables(report or "")
    if not tables:
        return ""
    lines: list[str] = []
    for df in tables:
        for col in df.columns:
            vals = [str(v).strip() for v in df[col]
                    if str(v).strip() and str(v).strip().lower()
                    not in ("nan", "none", "-", "—", "n/a")]
            # 纯数字列（年份/数值）的重复无聚合意义
            if all(re.fullmatch(r"[-+\d.,]+", v) for v in vals[:10] if v):
                continue
            # Per-column cap BEFORE the global cap: one high-repetition
            # column (e.g. paper titles in author-exploded rows) must not
            # starve the column the question is actually about.
            col_lines = 0
            for val, c in Counter(vals).most_common():
                if c >= 2:
                    lines.append(f"- {col}: {val!r} appears {c} times")
                    col_lines += 1
                    if col_lines >= 5:
                        break
            if len(lines) >= 60:
                break
    if not lines:
        return ""
    return (
        "==== Code-computed occurrence counts (>=2, per column) ====\n"
        "The question involves repeated occurrences. These tallies were "
        "computed deterministically from the report tables — use them "
        "instead of counting rows by eye; you still apply the question's "
        "filters to pick the right entry.\n"
        + "\n".join(lines[:30]) + "\n\n"
    )


_SHAPE_FEEDBACK = """\

==== Your previous attempt was REJECTED ====
{reason}
Re-emit the fenced tsv block obeying the required shape exactly.
"""


def _parse_tsv(body: str) -> Optional[pd.DataFrame]:
    try:
        df = pd.read_csv(StringIO(body), sep="\t", dtype=str).fillna("")
        df = df.loc[:, ~df.columns.astype(str).str.startswith("Unnamed")]
        if df.shape[0] >= 1 and df.shape[1] >= 1:
            return df
    except Exception as e:
        logger.debug("gisa reduce TSV parse fail: %s", e)
    return None


def _shape_error(df: pd.DataFrame, answer_type: str) -> str:
    if df.shape[1] != 1:
        return (f"Expected exactly 1 column, got {df.shape[1]} "
                f"(columns: {list(df.columns)}). Emit a header line plus one "
                f"value per line — nothing else on a line.")
    if answer_type == "item" and df.shape[0] != 1:
        return (f"Expected exactly 1 value row, got {df.shape[0]}. Reduce to "
                f"the single answer value.")
    return ""


async def reformat_gisa(
    raw_text: str,
    *,
    answer_type: str = "table",
    original_query: str,
    required_columns: Optional[list[str]] = None,
    column_formats: Optional[dict[str, str]] = None,
    sort_hint: str = "",
    filters: Optional[list[str]] = None,
    role: str = "reformat",
    max_retries: int = 2,
) -> tuple[Optional[str], Optional[pd.DataFrame]]:
    answer_type = (answer_type or "table").strip().lower()
    if answer_type not in _SHAPE_DIRECTIVES:
        return await join_and_reformat_with_llm(
            raw_text,
            target="gisa",
            original_query=original_query,
            required_columns=required_columns,
            column_formats=column_formats,
            sort_hint=sort_hint,
            filters=filters,
            role=role,
            max_retries=max_retries,
        )

    shape_directive, example_layout = _SHAPE_DIRECTIVES[answer_type]
    filters_block = "\n".join(f"- {f}" for f in (filters or []) if str(f).strip()) \
        or "(none parsed — apply the question's own wording)"
    prompt = _REDUCE_PROMPT.format(
        shape_directive=shape_directive,
        example_layout=example_layout,
        original_query=original_query,
        sort_block=sort_hint.strip() or "(none specified)",
        filters_block=filters_block,
        item_rule=_ITEM_RULE if answer_type == "item" else "",
        aggregation_block=_aggregation_hint(original_query, raw_text),
        report=strip_citations(raw_text),
    )

    last_block: Optional[str] = None
    last_df: Optional[pd.DataFrame] = None
    # +1: shape rejections get one extra round beyond transport retries
    for _ in range(max_retries + 1):
        content = await invoke_reformat_model(prompt, role=role)
        body = _strip_fence(content, "tsv")
        if not body:
            continue
        df = _parse_tsv(body)
        if df is None:
            prompt += _SHAPE_FEEDBACK.format(
                reason="Output was not parseable as TSV.")
            continue
        block = f"```tsv\n{body}\n```"
        last_block, last_df = block, df
        err = _shape_error(df, answer_type)
        if not err:
            return block, df
        prompt += _SHAPE_FEEDBACK.format(reason=err)

    if last_block is not None:
        logger.warning("gisa %s reformat: shape still invalid after retries", answer_type)
        return last_block, last_df
    logger.warning("gisa %s reformat: no parseable output", answer_type)
    return None, None
