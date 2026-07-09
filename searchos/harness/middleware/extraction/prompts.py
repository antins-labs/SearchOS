from __future__ import annotations


__all__ = [
    "COVERAGE_AWARE_ROW_PROMPT",
    "FILL_ROW_PROMPT",
    "DISCOVER_ROW_PROMPT",
    "build_coverage_aware_row_prompt",
    "build_fill_row_prompt",
    "build_discover_row_prompt",
]


# ---------------------------------------------------------------------------
# Row-level extraction (for schemas with primary_key)
# ---------------------------------------------------------------------------


def _render_row_key_example(primary_key: list[str], data_columns: list[str]) -> str:
    parts = [f'"{k}": "<value>",' for k in primary_key]
    parts += [f'"{d}": "<value or null>",' for d in data_columns]
    return "\n      ".join(parts)


def _render_column_desc_block(
    primary_key: list[str], data_columns: list[str],
    column_desc: dict | None,
) -> str:
    if not column_desc:
        return ""
    lines = []
    for col in primary_key + data_columns:
        cd = column_desc.get(col)
        if cd is None:
            continue
        col_type = getattr(cd, "type", "str") or "str"
        desc = getattr(cd, "desc", "") or ""
        parts = [col_type]
        if desc:
            parts.append(desc)
        check = getattr(cd, "check", None)
        if check is not None:
            rules = []
            if getattr(check, "enum", None) is not None:
                rules.append(f"must be one of {check.enum}")
            if getattr(check, "min", None) is not None:
                rules.append(f"must be >= {check.min:g}")
            if getattr(check, "max", None) is not None:
                rules.append(f"must be <= {check.max:g}")
            if rules:
                parts.append(
                    "HARD CHECK (rows violating this are rejected at ingest, "
                    "list columns checked element-wise): " + ", ".join(rules)
                )
        lines.append(f"- {col}: {'. '.join(parts)}")
    if not lines:
        return ""
    return "\n## Column descriptions\n" + "\n".join(lines) + "\n"



# ---------------------------------------------------------------------------
# Dual-mode extraction — one flush, two judge calls with single-purpose
# prompts. The merged prompt above shows incomplete rows as a "待填表单"
# (rows + MISSING columns) while also demanding new-row discovery and
# forbidding empty output; under load the judge tends to copy a nearby
# visible value into a listed row just to satisfy the form. Splitting the
# goals lets each prompt carry hard counter-rules:
#   FILL    — only the incomplete-row view; emitting nothing is normal.
#   DISCOVER — only a PK inventory (no MISSING form at all); new rows only.
# ---------------------------------------------------------------------------

_PROMPT_HEADER = """\
You are a structured data extractor.
## Overall research goal (defines what is IN SCOPE for the table)
    {global_task}
## Current sub-agent assignment (the slice being worked right now)
    {sub_agent_task}
## Primary key (identifies each row)
{primary_key}
## Data columns (values to fill per row)
{data_columns}{column_desc_block}
"""

_OUTPUT_FORMAT_BLOCK = """\
## Output format — JSON array of row objects
Each row is an object with ALL column names as keys:
    {{{key_example}
      "_source_page": <the "### Page N" number the quoted passages come from>,
      "_source_excerpt": "<verbatim page passage(s) containing the values you emit>",
      "_alignment": "full" | "partial",
      "_alignment_note": "<one sentence>",
      "_confidence": "high" | "medium" | "low",
      "_source_authority": "official" | "aggregator" | "news" | "blog" | "unclear"}}
- ONE ROW = ONE PAGE. `_source_page` is the number in that page's "### Page N"
  header, and `_source_excerpt` quotes THAT page only. When several pages state
  values for the same primary key, emit one row object per page (same PK,
  different `_source_page`) — never merge values from different pages into one row.
- `_source_excerpt` is the factual warrant for the row: quote the page passage(s)
  that state the non-null data values (join distant fragments with " … ", keep it
  under ~400 chars). Copy characters exactly — no paraphrase, no reflow.
- A data value you cannot point to inside `_source_excerpt` (or another verbatim
  quote of this page) does not exist for this extraction → that cell is null.
"""

_VALUE_RULES = """\
A ROW = one real-world entity that is in scope. For each row, decide (A) should it exist, then (B) what goes in each cell.

## Evidence discipline — every value must exist on THIS page
You are an extractor, not an analyst: a cell holds what a page STATES, or null.
- THE PAGE IS THE ONLY SOURCE. A value you know from memory, world knowledge, a typical/likely figure, or another entity's row is FABRICATION even if it happens to be correct. A page that merely LISTS entities (an announcement, a ranking, an index) states NO attribute values — extracting prices/dates/figures from such a page is fabrication. Null is a correct, expected answer; a guessed value is a defect.
- UNIFORMITY RED FLAG: if you notice the same value landing in the same column for many different entities (e.g. dozens of rows all "100元/人"), stop — real-world values are not that uniform. Re-check the page; keep the value ONLY for rows where the page states it.
- NO ARITHMETIC, NO CONVERSION: copy numbers exactly as printed, original unit and wording included — the harness converts units deterministically after ingest. Never produce a value by combining or transforming others — no sums, differences, averages, rate math, unit rescaling, and no completing an identity (total = sum of parts) however certain it seems. Sources need not share scope, period, or rounding basis, so a derived number is fabricated evidence even when the arithmetic is right.
    ✗ a page states a TOTAL and one COMPONENT; the column asks for the other component → null, do not subtract.
    ✗ a page lists per-period figures; the column asks for the whole period → null unless the page itself prints that total.

## (A) Emit a row ONLY if
- IN SCOPE for the OVERALL goal — date range, rank/top-N cutoff, region, language, include/exclude lists all bind. The sub-agent assignment only says where to LOOK: an in-scope entity counts even if the assignment never named it; an out-of-scope entity never does.
- The page ADDS data for it (at least one needed column). Never invent a row to "complete" a set.
- Its primary-key columns are stated on the page. Rows with a null PK are dropped.

## (B) Fill each data cell — stop at the FIRST step that applies
1. The page does not state the value FOR THIS entity → null. A value belonging to another row never fills a blank, and a value remembered from outside this page never fills a blank.
2. Quote VERBATIM — numbers, names, dates exactly as the page writes them, original unit and currency included (column header says 百万, page says "3.5亿" → write "3.5亿"; the harness rescales units in code, you never do).
3. Every non-null value must be findable inside `_source_excerpt`. If you cannot quote a passage stating the value, the value is null.
4. The page offers "varies / depends"-style text instead of a value → that is not a value. Take the figure stated for the column's pinned scope if any (keep all tiers when several are listed); no figure → null.
5. The page's value is COARSER than the column asks (a year where a full date is wanted, a rounded figure where an exact one is) → write the raw value, set `_alignment="partial"`. Never fabricate precision.
6. The page states a composite value → emit only the component the column asks for.
7. An authoritative source EXPLICITLY states the value does not exist / is not published → record that absence in the source's OWN words (never "null", "none", "n/a"). Failing to find a value is NOT absence → null.

## Entity vs. page operator
Site boilerplate (copyright lines, registration/filing numbers, contact blocks) describes the WEBSITE OPERATOR, not your entities — never pull it into a row's columns.

## Metadata
- _alignment: "full" when the page directly states the values you emit; "partial" ONLY per B5. Null columns do not downgrade alignment.
- _alignment_note: quote or paraphrase what the PAGE says — never assert provenance the page does not show (e.g. never write "based on the official listing" when the quoted page shows no such value).
- _confidence: "high" ONLY when every non-null value appears verbatim inside `_source_excerpt`; "medium" when the page states it but you had to read it off a table/chart context; anything weaker → "low".
- Do NOT return [] unless the pages genuinely contain nothing on-task.

Return ONLY the JSON array, no prose, no markdown fences.\
"""

FILL_ROW_PROMPT = _PROMPT_HEADER + """\
## Rows needing data (FILL MODE)
The table rows below still have empty columns; ``MISSING=[...]`` lists the columns still empty for that row. Your ONLY job is to fill these rows from the pages — a separate pass handles new-row discovery.
{coverage_snapshot}
## Pages
{pages_block}
""" + _OUTPUT_FORMAT_BLOCK + """\
## Rules
- FILL ONLY: output a row ONLY when a page EXPLICITLY mentions that row's entity AND states a value for at least one of its MISSING columns. Copy the row's primary-key text VERBATIM from the list above (do NOT reformat dates, names, casing, or punctuation).
- Do NOT output rows that are not in the list — new rows are out of scope for this call; skip them even if the pages describe them.
- An EMPTY array is a perfectly normal result. If no page mentions any listed row, return [].
""" + _VALUE_RULES

DISCOVER_ROW_PROMPT = _PROMPT_HEADER + """\
## Known rows — already in the table (DISCOVER MODE)
Every primary key below already exists; its data is handled elsewhere. Your ONLY job is to find rows NOT in this list.
{known_pk_list}
## Pages
{pages_block}
""" + _OUTPUT_FORMAT_BLOCK + """\
## Rules
- DISCOVER ONLY: output ONLY brand-new rows — rows whose primary key is NOT in the known list above (including trivial reformattings of a listed key: same date written differently, same name with different casing / punctuation are NOT new rows).
- For each new row, use the page's verbatim primary-key text and fill every data column the page states; use null for the rest.
- If the pages only describe rows already in the known list, return [] — that is a normal result.
""" + _VALUE_RULES

# ---------------------------------------------------------------------------
# Coverage-aware row extraction — merges row extraction + coverage fill into a
# single judge call. The judge sees the table's current row inventory (with
# per-row MISSING columns) so it (a) skips already-complete rows, and (b)
# reuses the EXACT canonical primary-key text of existing rows.
# ---------------------------------------------------------------------------

COVERAGE_AWARE_ROW_PROMPT = _PROMPT_HEADER + """\
## Current table status
The rows already in this table are listed below. ``MISSING=[...]`` lists the columns still empty for that row.
{coverage_snapshot}
## Pages
{pages_block}
""" + _OUTPUT_FORMAT_BLOCK + """\
## Rules
- For an EXISTING row (listed above): reuse its EXACT primary-key text (do NOT reformat dates, names, casing, or punctuation). Output it ONLY when a page fills at least one of its MISSING columns. Do NOT re-output a row marked "(complete)".
- For a BRAND-NEW row (not listed above): use the page's verbatim PK text and fill every data column the page states; null for the rest.
""" + _VALUE_RULES


def _render_pages_block(pages: list[dict[str, str]]) -> str:
    # Always numbered, even for a single page — `_source_page` in the output
    # format refers to these "### Page N" headers.
    parts = []
    for i, p in enumerate(pages):
        parts.append(
            f"### Page {i + 1}\n"
            f"Source: {p.get('source_url', '')}\n"
            f"{p.get('content', '')}"
        )
    return "\n\n".join(parts)


def build_fill_row_prompt(
    *,
    global_task: str,
    sub_agent_task: str,
    primary_key: list[str],
    data_columns: list[str],
    column_desc: dict | None,
    pages: list[dict[str, str]],
    coverage_snapshot: str,
) -> str:
    return FILL_ROW_PROMPT.format(
        global_task=global_task or sub_agent_task,
        sub_agent_task=sub_agent_task,
        primary_key=list(primary_key),
        data_columns=list(data_columns),
        column_desc_block=_render_column_desc_block(primary_key, data_columns, column_desc),
        coverage_snapshot=coverage_snapshot or (
            "(every existing row currently has all columns filled — "
            "return [] unless a page explicitly contradicts that)"
        ),
        pages_block=_render_pages_block(pages),
        key_example=_render_row_key_example(primary_key, data_columns),
    )


def build_discover_row_prompt(
    *,
    global_task: str,
    sub_agent_task: str,
    primary_key: list[str],
    data_columns: list[str],
    column_desc: dict | None,
    pages: list[dict[str, str]],
    known_pk_list: str,
) -> str:
    return DISCOVER_ROW_PROMPT.format(
        global_task=global_task or sub_agent_task,
        sub_agent_task=sub_agent_task,
        primary_key=list(primary_key),
        data_columns=list(data_columns),
        column_desc_block=_render_column_desc_block(primary_key, data_columns, column_desc),
        known_pk_list=known_pk_list or "(table is empty — every row you identify is new)",
        pages_block=_render_pages_block(pages),
        key_example=_render_row_key_example(primary_key, data_columns),
    )


def build_coverage_aware_row_prompt(
    *,
    global_task: str = "",
    sub_agent_task: str,
    primary_key: list[str],
    data_columns: list[str],
    column_desc: dict | None,
    pages: list[dict[str, str]],
    coverage_snapshot: str,
) -> str:
    """Assemble the merged row-extraction + coverage-fill prompt.

    ``pages`` is a list of ``{"source_url": ..., "content": ...}`` dicts.
    All pages are rendered into a single prompt so the judge extracts
    rows from all of them in one call.
    """
    column_desc_block = _render_column_desc_block(primary_key, data_columns, column_desc)
    key_example = _render_row_key_example(primary_key, data_columns)
    pages_block = _render_pages_block(pages)

    return COVERAGE_AWARE_ROW_PROMPT.format(
        global_task=global_task or sub_agent_task,
        sub_agent_task=sub_agent_task,
        primary_key=list(primary_key),
        data_columns=list(data_columns),
        column_desc_block=column_desc_block,
        coverage_snapshot=coverage_snapshot or "(no rows yet)",
        pages_block=pages_block,
        key_example=key_example,
    )
