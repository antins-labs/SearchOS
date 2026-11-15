from __future__ import annotations

from datetime import date

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
## Runtime as-of date
    {current_date}

This date is supplied by the host runtime and is the authoritative current date. Resolve relative dates against it unless the task specifies another reference date. Assess temporal fit using the requested period and the source content; do not substitute a remembered current date or a model training cutoff. A date later than your training cutoff does not by itself make a source record a forecast, simulation, or invalid evidence.
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
Return exactly one JSON array. Each item contains every primary-key and data-column name from the current schema, plus the metadata shown below. Use the exact column names. Write JSON null for an unstated data value. Return [] when no row qualifies for the active extraction mode.
    [{{{key_example}
      "_source_page": <the "### Page N" number the quoted passages come from>,
      "_source_excerpt": "<verbatim page passage(s) containing the values you emit>",
      "_alignment": "full" | "partial",
      "_alignment_note": "<one sentence>",
      "_confidence": "high" | "medium" | "low",
      "_source_authority": "official" | "aggregator" | "news" | "blog" | "unclear"}}]
- Coverage tables declare their column names once. Each following row array supplies values in that same order; a cell object carries its value and unresolved status. Fill targets identify eligible cells by zero-based row and column indices.
- Each output primary-key field contains its own column value. For an existing row, copy each primary-key value exactly from its corresponding coverage column. Preserve punctuation inside a field, including a literal `|` in a product name. Current table values guide row matching; the actual source pages supply the evidence for newly emitted values.
- For skill:// or agent:// observations, add `_source_urls`: a map from each data column to the original source URLs (or evidence:IDs) supporting that value, copied from the observation or its Declared source links. Keep sources separate per value; never invent URLs or assign every result link to every cell. Unknown provenance is an empty list.
- ONE ROW = ONE PAGE. `_source_page` is the number in that page's "### Page N" header, and `_source_excerpt` quotes THAT page only. When several pages state values for the same primary key, emit one row object per page (same PK, different `_source_page`) — never merge values from different pages into one row.
- `_source_excerpt` is the factual warrant for the row: quote the page passage(s) that state the non-null data values (join distant fragments with " … ", keep it under ~400 chars). Copy characters exactly — no paraphrase, no reflow.
- A data value you cannot point to inside `_source_excerpt` (or another verbatim quote of this page) does not exist for this extraction → that cell is null.

## Format examples
These examples demonstrate serialization of eligible rows. Their column names and facts belong only to their own example; use the current schema, actual pages, and active extraction mode for your answer.

Example 1 — single-column primary key; an unstated field stays null.
Primary key: ["Product"]. Data columns: ["Size", "ABV"].
Page 1 text: Product: Orion. Size: 500 ml.
Output:
[{{"Product": "Orion", "Size": "500 ml", "ABV": null, "_source_page": 1, "_source_excerpt": "Product: Orion. Size: 500 ml.", "_alignment": "full", "_alignment_note": "The page states the product and size.", "_confidence": "high", "_source_authority": "unclear"}}]

Example 2 — composite primary key; each field keeps its own value.
Primary key: ["Brand", "Product"]. Data columns: ["Size"].
Coverage columns, when already present: ["Brand", "Product", "Size"].
Coverage row: ["Acme", "Classic", null].
Page 1 text: Brand: Acme. Product: Classic. Size: 500 ml.
Output:
[{{"Brand": "Acme", "Product": "Classic", "Size": "500 ml", "_source_page": 1, "_source_excerpt": "Brand: Acme. Product: Classic. Size: 500 ml.", "_alignment": "full", "_alignment_note": "The page identifies the brand, product and size.", "_confidence": "high", "_source_authority": "unclear"}}]

Example 3 — a literal separator inside a primary-key value is preserved.
Primary key: ["Brand", "Product"]. Data columns: ["Size"].
Coverage columns, when already present: ["Brand", "Product", "Size"].
Coverage row: ["Acme", "Blue|Label", null].
Page 1 text: Brand: Acme. Product: Blue|Label. Size: 375 ml.
Output:
[{{"Brand": "Acme", "Product": "Blue|Label", "Size": "375 ml", "_source_page": 1, "_source_excerpt": "Brand: Acme. Product: Blue|Label. Size: 375 ml.", "_alignment": "full", "_alignment_note": "The page names Blue|Label and states its size.", "_confidence": "high", "_source_authority": "unclear"}}]

Example 4 — no page supports a needed value for any eligible row.
Output:
[]
"""

_VALUE_RULES = """\
A ROW = one real-world entity that is in scope. For each row, decide (A) should it exist, then (B) what goes in each cell.

## Evidence discipline — every value must exist on THIS page
You are an extractor, not an analyst: a cell holds what a page STATES, or null.
- TEMPORAL FIT IS REQUIRED: match the value's event/effective date or reporting period to the task and column description. The page publication date is metadata, not automatically the date of the fact.
- For "current/latest/as of" columns, reject a value when the page does not establish that it applies at the requested cutoff. When several periods appear, extract only the matching one; never choose by visual order alone.
- A future target, forecast, schedule, or announcement is not a completed current value. Extract it only when the requested column explicitly asks for plans/forecasts, preserving its future date and status.
- THE PAGE IS THE ONLY SOURCE. A value you know from memory, world knowledge, a typical/likely figure, or another entity's row is FABRICATION even if it happens to be correct. An entity's presence in a list supports only the facts explicitly stated about it; extract attribute values only when the page actually provides them. Null is a correct, expected answer; a guessed value is a defect.
- URL VALUES: copy a complete observed URL or href, the page's own Source address, or a Declared source link. Never add a scheme to a bare domain, shorten an article URL to its homepage, or invent a path. When an original-article column is requested, an aggregator URL or publisher homepage does not satisfy it; leave it null until the article address is available. A search-engine snippet may omit links and does not establish that the full page was read.
- CHECK REPEATED VALUES: when the same value appears in several output rows, verify that the page supports it for each entity. A shared value can be valid, but repetition never justifies copying it into an unsupported cell.
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
5. Check the requested subgroup, version, period, and other qualifying conditions. A value for a broader group applies to the requested subgroup only when the source says the rule covers that subgroup. With incomplete scope or precision, emit the broader or coarser value in a separate row with `_alignment="partial"`, quote its actual scope, and set other data fields to null. Put fully supported fields in their own full row. An unrelated value stays null.
6. The page states a composite value → emit only the component the column asks for.
7. An authoritative source EXPLICITLY states the value does not exist / is not published → record that absence in the source's OWN words (never "null", "none", "n/a"). Failing to find a value is NOT absence → null.

## Entity vs. page operator
Site boilerplate (copyright lines, registration/filing numbers, contact blocks) describes the WEBSITE OPERATOR, not your entities — never pull it into a row's columns.

## Metadata
- _source_authority describes THIS observed page's publisher and role. A roundup quoting an official announcement remains "aggregator"; mentioning an official organization does not make the roundup "official".
- _alignment: "full" when the source supports the emitted values for the requested entity and conditions; "partial" retains the evidence as a candidate and leaves the target open. Null columns do not downgrade alignment.
- _alignment_note: quote or paraphrase what the PAGE says — never assert provenance the page does not show (e.g. never write "based on the official listing" when the quoted page shows no such value).
- _confidence: "high" ONLY when every non-null value appears verbatim inside `_source_excerpt`; "medium" when the page states it but you had to read it off a table/chart context; anything weaker → "low".
- Return [] when no row satisfies the current extraction mode and evidence rules. Never create a row or fill a cell merely to avoid an empty output.

Return ONLY the JSON array, no prose, no markdown fences.
"""

FILL_ROW_PROMPT = _PROMPT_HEADER + """\
## Rows needing data (FILL MODE)
The table rows below have unresolved cells. Fill targets specify the eligible cells by row and column indices. Fill these targets using the source pages; a separate pass handles new-row discovery.
{coverage_snapshot}
## Pages
{pages_block}
""" + _OUTPUT_FORMAT_BLOCK + """\
## Rules
- FILL ONLY: output a row ONLY when a page EXPLICITLY mentions that row's entity AND states a value for at least one of its fill targets. Copy each primary-key column's value from the matching coverage row exactly, including dates, names, casing and punctuation. Set data columns outside the row's fill targets to null.
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
- For each new row, copy each primary-key field's own value verbatim from the page and fill every data column the page states; use null for the rest.
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
The rows already in this table are listed below. Fill targets specify the unresolved cells by row and column indices.
{coverage_snapshot}
## Pages
{pages_block}
""" + _OUTPUT_FORMAT_BLOCK + """\
## Rules
- For an EXISTING row (listed above): copy each primary-key column's value from its corresponding coverage column exactly. Output it ONLY when a page fills at least one of its fill targets; set the other data columns to null. Skip the listed complete rows.
- For a BRAND-NEW row (not listed above): copy each primary-key field's own value verbatim from the page and fill every data column the page states; null for the rest.
""" + _VALUE_RULES


def _render_pages_block(pages: list[dict[str, str]]) -> str:
    # Always numbered, even for a single page — `_source_page` in the output
    # format refers to these "### Page N" headers.
    parts = []
    for i, p in enumerate(pages):
        identity = f"\nPage ID: {p['page_id']}\n" if p.get("page_id") else ""
        parent = p.get("referring_page")
        origin = (f"Page linking to this attachment (subject and date context): {parent[1]} ({parent[0]})\n"
                  if parent else "")
        parts.append(
            f"### Page {i + 1}\n"
            f"Source: {p.get('source_url', '')}\n{identity}\n"
            f"{origin}Declared source links: {p.get('source_urls', [])}\n"
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
        current_date=date.today().isoformat(),
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
        current_date=date.today().isoformat(),
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
        current_date=date.today().isoformat(),
        global_task=global_task or sub_agent_task,
        sub_agent_task=sub_agent_task,
        primary_key=list(primary_key),
        data_columns=list(data_columns),
        column_desc_block=column_desc_block,
        coverage_snapshot=coverage_snapshot or "(no rows yet)",
        pages_block=pages_block,
        key_example=key_example,
    )
