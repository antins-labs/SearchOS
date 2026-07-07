"""Strip column-formatting demands from benchmark questions.

Many GISA / WideSearch prompts wrap the actual research goal with
boiler-plate of the form "请输出一个表，包含以下列：A、B、C…" or
"organize the results in one Markdown table with columns: …". When fed
verbatim to the orchestrator, the model defers to the user and produces
**one** wide table — fighting our multi-table planning workflow.

This filter asks the judge model to (a) restate the research goal without
the table/column directives and (b) lift the column list out as
metadata. The cleaned query goes to the harness; the columns are stashed
on the eval record for inspection.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


_PROMPT = """You are preprocessing a benchmark question for a research agent.

The question often includes formatting demands like "output a single Markdown \
table with the following columns: A, B, C" or "请以一个表格输出，列名依次为：…". \
These demands collapse the agent's multi-table planning. Your job:

1. Restate the **research goal** in clear, neutral phrasing — keep the entity \
constraints, time ranges, and source requirements intact, but DROP any wording \
that prescribes output format, column lists, single-table layout, sort order, \
or unit/format requirements for individual columns.
2. Extract the prescribed column names (if any) into a JSON list, preserving \
the user's original wording.
3. Extract any per-column format / unit / value-domain hints into a JSON \
object keyed by column name. Examples of hints to capture: \
"yyyy-mm-dd", "MM-DD-YYYY", "USD millions", "ISO 3166-1 alpha-3", \
"value must be one of X|Y|Z", "Arabic numerals only", "fill missing as '/'", \
"Day Month, Year e.g. 4th June, 2011". Use the user's original wording. \
If a column has no specific format hint, omit it from the object.
4. Extract row-level **filter** directives (range / threshold / membership / \
top-K predicates) into a JSON list of short imperative strings — each one \
describing a row admission rule. Examples: \
"only top 5 by Total Wins", "only years 2020-2024", \
"only rows where Score >= 80", "only Asian countries", \
"include rows where Award Year in {{2022,2023}}". \
Capture every filter the question imposes on which rows to keep. \
Return [] if there are no filters.
5. Extract the **sort** directive (if any) as a single short string, e.g. \
"by Total Wins desc", "by year asc, then rank asc", \
"by投档线总分由高到低". Return "" if no sort is specified.

Return strictly the following JSON, no commentary, no markdown fences:

{{"cleaned_query": "<rewritten question>", "columns": ["col1", ...], "column_formats": {{"col1": "hint", ...}}, "filters": ["..."], "sort": "..."}}

If no column directives exist, return columns as an empty list, \
column_formats / filters as empty, sort as empty string, and cleaned_query \
identical to the original.

Original question:
\"\"\"
{query}
\"\"\"
"""


@dataclass
class CleanedQuery:
    original: str
    cleaned: str
    columns: list[str]
    column_formats: dict[str, str]
    filters: list[str]
    sort: str
    used_fallback: bool = False


def _parse_json_loose(content: str) -> Optional[dict]:
    if not content:
        return None
    # try fenced
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass
    # bare
    try:
        return json.loads(content.strip())
    except Exception:
        pass
    # last-ditch: first {...} block
    m = re.search(r"\{[\s\S]*\}", content)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            return None
    return None


async def _invoke_once(model, prompt: str) -> str:
    from langchain_core.messages import HumanMessage
    ai = await model.ainvoke([HumanMessage(content=prompt)])
    content = getattr(ai, "content", "") or ""
    if isinstance(content, list):
        content = "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in content)
    return content


async def clean_query(query: str, *, role: str = "judge", max_retries: int = 3) -> CleanedQuery:
    """LLM-driven query cleaner. Retries up to ``max_retries`` total attempts
    before falling back to the original. The judge model occasionally returns
    empty content (likely max_tokens / thinking-only), so a single retry
    typically rescues it."""
    from searchos.config.models import get_model_for

    model = get_model_for(role)
    try:
        model = model.bind(temperature=0)
    except Exception:
        pass
    prompt = _PROMPT.format(query=query)
    parsed = None
    last_raw = ""
    for attempt in range(max_retries):
        try:
            content = await _invoke_once(model, prompt)
        except Exception as e:
            logger.warning("clean_query attempt %d LLM call failed: %s", attempt + 1, e)
            content = ""
        last_raw = content
        parsed = _parse_json_loose(content)
        if parsed and "cleaned_query" in parsed:
            break
        logger.info("clean_query attempt %d empty/parse-fail; retrying", attempt + 1)

    if not parsed or "cleaned_query" not in parsed:
        logger.warning("clean_query gave up after %d attempts; raw[-200:]=%s",
                       max_retries, (last_raw or "")[-200:])
        return CleanedQuery(original=query, cleaned=query, columns=[],
                            column_formats={}, filters=[], sort="",
                            used_fallback=True)

    cleaned = str(parsed.get("cleaned_query") or "").strip() or query
    cols_raw = parsed.get("columns") or []
    cols = [str(c).strip() for c in cols_raw if isinstance(cols_raw, list) and str(c).strip()]
    fmt_raw = parsed.get("column_formats") or {}
    if not isinstance(fmt_raw, dict):
        fmt_raw = {}
    fmts = {str(k).strip(): str(v).strip() for k, v in fmt_raw.items() if str(v).strip()}
    filt_raw = parsed.get("filters") or []
    filters = [str(f).strip() for f in filt_raw if isinstance(filt_raw, list) and str(f).strip()]
    sort_directive = str(parsed.get("sort") or "").strip()
    return CleanedQuery(original=query, cleaned=cleaned, columns=cols,
                        column_formats=fmts, filters=filters, sort=sort_directive,
                        used_fallback=False)


_SCHEMA_HINTS_PROMPT = """\
You are helping a research agent understand the expected output format for each \
column in a table-retrieval task. You are given:

1. The original user question.
2. The first {n_rows} rows of the ground-truth answer (header + data).

For each column, produce a short `column_desc` string that tells the extractor \
what to fill and EXACTLY in what shape/format, so extraction is as precise as \
possible. Cover:
- Value semantics: what does this column actually represent? Disambiguate \
ambiguous column names (e.g. "选考科目要求的文字描述，非专业组编号").
- Format & shape: pin down the concrete TEMPLATE — date layout (YYYY-MM-DD vs \
MM/DD/YYYY), number format (integer / decimal places / thousands separators / \
unit suffix), casing, language, allowed value set, code scheme, length or \
structure. The more precisely you describe the shape, the better the extraction.

CRITICAL — the sample rows ARE the ground-truth ANSWER. NEVER copy, quote, or \
echo any value that appears (or plausibly could appear) in them. You MAY include \
an illustrative example, but ONLY a synthetic, obviously-fake placeholder you \
invent yourself — never a real data value. Strongly prefer abstract format \
templates over example values: "YYYY-MM-DD", "integer with thousands separators, \
e.g. 1,234,567", "ISO 3166-1 alpha-3 code", "<City>, <Province>", "decimal with \
two places plus unit suffix". If you do give a concrete example, make it generic \
and clearly unrelated to the real data (round placeholder numbers, names like \
'Acme Corp', dates like 'January 1, 2000'). If you cannot illustrate the format \
without risking a real value, describe the pattern only.

Return strictly JSON, no commentary, no markdown fences:

{{"column_descs": {{"col1": "description", "col2": "description", ...}}}}

Only include columns where the desc adds information beyond what the column name \
already says. Omit trivially obvious columns (e.g. "年份" clearly means a 4-digit year).

---

**Original question:**
\"\"\"
{query}
\"\"\"

**Ground-truth sample ({n_rows} rows):**
```
{golden_head}
```
"""


# For list/set/item answers there is no header row — every line is a VALUE.
# Describe the format of the values themselves (no column structure).
_VALUE_HINT_PROMPT = """\
You are helping a research agent understand the expected output format for a \
list/set/single-value answer (NOT a table — there is no header). You are given:

1. The original user question.
2. Up to {n_rows} example values from the ground-truth answer (each line is one VALUE, not a header).

Produce ONE short hint describing what each answer value should look like and \
EXACTLY in what shape/format, so extraction is precise: its semantics, naming \
convention, language, date layout, units, precision, casing, allowed value set, \
length or structure. Pin down the concrete TEMPLATE wherever possible.

CRITICAL — the example values ARE the ground-truth ANSWER. NEVER copy, quote, or \
echo any of them, nor any value that plausibly could appear in the answer. You \
MAY include an illustrative example, but ONLY a synthetic, obviously-fake \
placeholder you invent yourself — never a real value. Strongly prefer abstract \
format templates (e.g. "YYYY-MM-DD", "<Full Name>", "lowercase English noun \
phrase") over example values. If you cannot illustrate without risking a real \
value, describe the pattern only.

Return strictly JSON, no commentary, no markdown fences:

{{"value_format": "the hint"}}

Return {{"value_format": ""}} if the values are trivially self-explanatory.

---

**Original question:**
\"\"\"
{query}
\"\"\"

**Ground-truth example values (up to {n_rows}):**
```
{golden_values}
```
"""


async def generate_schema_hints(
    query: str,
    golden_csv_path: str,
    *,
    n_rows: int = 5,
    role: str = "judge",
    answer_type: str = "table",
) -> dict[str, str]:
    """Generate format hints from the golden CSV.

    For ``table`` answers: one ``column_desc`` per column, inferred from the
    header + first ``n_rows`` rows. Returns ``{col: desc}``.

    For ``list``/``set``/``item`` answers there is no header — every line is a
    value. We infer a single value-format hint from the content and return it
    under the ``"*"`` key (applies to whatever column the preprocess inferred).

    Used only during eval to help the orchestrator's create_schema.
    """
    import csv
    from pathlib import Path

    from searchos.config.models import get_model_for

    csv_path = Path(golden_csv_path)
    if not csv_path.exists():
        return {}

    # Read up to n_rows (+header for tables) rows.
    rows: list[list[str]] = []
    try:
        with csv_path.open(encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            for i, row in enumerate(reader):
                if i > n_rows:
                    break
                rows.append(row)
    except Exception:
        return {}

    if not rows:
        return {}
    lines = [",".join(r) for r in rows]

    model = get_model_for(role)
    try:
        model = model.bind(temperature=0)
    except Exception:
        pass

    is_table = (answer_type or "table") == "table"
    if is_table:
        if len(lines) < 2:  # need header + ≥1 data row
            return {}
        prompt = _SCHEMA_HINTS_PROMPT.format(
            query=query, golden_head="\n".join(lines), n_rows=n_rows,
        )
        result_key = "column_descs"
    else:
        # No header: every line is a VALUE — infer the value format directly.
        prompt = _VALUE_HINT_PROMPT.format(
            query=query, golden_values="\n".join(lines[:n_rows]), n_rows=n_rows,
        )
        result_key = "value_format"

    for attempt in range(2):
        try:
            content = await _invoke_once(model, prompt)
        except Exception as e:
            logger.warning("generate_schema_hints attempt %d failed: %s", attempt + 1, e)
            content = ""
        parsed = _parse_json_loose(content)
        if parsed and result_key in parsed:
            raw = parsed[result_key]
            if is_table and isinstance(raw, dict):
                return {str(k).strip(): str(v).strip() for k, v in raw.items() if str(v).strip()}
            if not is_table and isinstance(raw, str) and raw.strip():
                return {"*": raw.strip()}
            if not is_table:
                return {}  # empty value_format → nothing to add
        logger.info("generate_schema_hints attempt %d parse-fail; retrying", attempt + 1)

    return {}


async def _smoke():
    sample = (
        "Please provide a table listing the top 50 songs from Rolling Stone's 2020 list. "
        "The table must include the columns: Rank, Song Title, Release Date. "
        "Format the 'Release Date' column as MM-DD-YYYY. Sort by Rank ascending."
    )
    out = await clean_query(sample)
    print(json.dumps({"cleaned": out.cleaned, "columns": out.columns,
                      "column_formats": out.column_formats,
                      "filters": out.filters, "sort": out.sort,
                      "fallback": out.used_fallback}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    from pathlib import Path
    from dotenv import load_dotenv
    for cand in [Path.cwd() / ".env", Path(__file__).parent.parent / ".env"]:
        if cand.exists():
            load_dotenv(cand)
            break
    asyncio.run(_smoke())
