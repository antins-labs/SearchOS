"""Benchmark-shaped reformatting of raw harness output.

``core`` holds the mechanics (table extraction, df/TSV/markdown conversion)
plus the shared multi-table join; ``gisa`` / ``widesearch`` own the
per-benchmark answer contracts. ``reformat_for_eval`` is the dispatch
entrypoint; the legacy ``join_and_reformat_with_llm`` import keeps working
for table-shaped callers.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

from typing import Optional

import pandas as pd

from eval.reformat.core import (
    df_to_markdown_block,
    df_to_tsv_block,
    extract_all_tables,
    extract_table_df,
    join_and_reformat_with_llm,
    load_session_output,
    reformat_for_benchmark,
    strip_citations,
    trim_extra_columns,
)
from eval.reformat.gisa import reformat_gisa
from eval.reformat.widesearch import reformat_widesearch

__all__ = [
    "df_to_markdown_block",
    "df_to_tsv_block",
    "extract_all_tables",
    "extract_table_df",
    "join_and_reformat_with_llm",
    "load_session_output",
    "reformat_for_benchmark",
    "reformat_for_eval",
    "reformat_gisa",
    "reformat_widesearch",
    "strip_citations",
    "trim_extra_columns",
]


def _is_empty_report(raw_text: str) -> bool:
    t = (raw_text or "").strip()
    if not t:
        return True
    return "_No report produced: 0 evidence nodes" in t


async def reformat_for_eval(
    raw_text: str,
    *,
    target: str,
    answer_type: str = "table",
    original_query: str,
    required_columns: Optional[list[str]] = None,
    column_formats: Optional[dict[str, str]] = None,
    sort_hint: str = "",
    filters: Optional[list[str]] = None,
) -> tuple[Optional[str], Optional[pd.DataFrame]]:
    # Zero-evidence guard (gisa#33: harness wrote an empty-marker report,
    # the reduce LLM then answered the QUESTION from prior knowledge and
    # scored 0.9 with zero search evidence — plausible-looking, ungrounded,
    # and it masks the infrastructure failure). Never hand an empty report
    # to an LLM that also sees the question.
    if _is_empty_report(raw_text):
        logger.warning("reformat: empty/marker report — refusing LLM reduce")
        return None, None

    common = dict(
        original_query=original_query,
        required_columns=required_columns,
        column_formats=column_formats,
        sort_hint=sort_hint,
        filters=filters,
    )
    if target == "gisa":
        return await reformat_gisa(raw_text, answer_type=answer_type, **common)
    if target == "widesearch":
        return await reformat_widesearch(raw_text, **common)
    raise ValueError(f"unknown target: {target}")
