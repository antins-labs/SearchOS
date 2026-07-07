"""WideSearch-specific reformat: always a markdown table joined from the
report's sub-tables; gold supplies the required column set."""

from __future__ import annotations

from typing import Optional

import pandas as pd

from eval.reformat.core import join_and_reformat_with_llm


async def reformat_widesearch(
    raw_text: str,
    *,
    original_query: str,
    required_columns: Optional[list[str]] = None,
    column_formats: Optional[dict[str, str]] = None,
    sort_hint: str = "",
    filters: Optional[list[str]] = None,
    role: str = "reformat",
    max_retries: int = 2,
) -> tuple[Optional[str], Optional[pd.DataFrame]]:
    return await join_and_reformat_with_llm(
        raw_text,
        target="widesearch",
        original_query=original_query,
        required_columns=required_columns,
        column_formats=column_formats,
        sort_hint=sort_hint,
        filters=filters,
        role=role,
        max_retries=max_retries,
    )
