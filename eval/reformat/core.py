"""Convert SearchForge raw output → benchmark-shaped prediction strings.

The harness writes a long-form ``report.md`` (5-section markdown) with
``[N]`` citation markers in every cell. Both GISA and WideSearch evaluators
expect a clean tabular payload:

* GISA — TSV inside ```tsv ... ``` (or raw)
* WideSearch — Markdown table inside ```markdown ... ```

This module extracts a single markdown table out of the harness output,
strips ``[N]`` / ``【N】`` citations, and emits both shapes.

When column names diverge ("Song_Title" vs "song title"), the official
WideSearch scorer already runs ``primary_key_preprocess`` (LLM column
alignment); GISA's matching is column-name lower+strip+spaceless so most
divergences vanish there too.
"""

from __future__ import annotations

import json
import logging
import re
from io import StringIO
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)


_CITE_RE = re.compile(r"\s*[\[【]\s*\d+(?:\s*[,，]\s*\d+)*\s*[\]】]")
# Synthesizer hedge decorations on partial cells (◇ … （部分）/（待确认）);
# strip so the scored value is the bare fact, not "◇ 355（部分）".
_HEDGE_RE = re.compile(r"◇\s*|\s*[（(](?:部分|待确认)[）)]")


def strip_citations(text: str) -> str:
    return _HEDGE_RE.sub("", _CITE_RE.sub("", text))


def _candidate_tables(text: str) -> list[str]:
    """Return all markdown table substrings in *text*, longest first."""
    out = []
    # ```markdown ... ``` blocks first.
    # Originally ``r"```(?:markdown)?\s*((?:\|[^\n]*\n?)+)```"`` — the
    # combination of ``\s*``, optional ``\n?``, and greedy ``+`` caused
    # catastrophic backtracking on outputs that started a ``` block but
    # never closed it (one wedged regex blocked the whole asyncio loop
    # because Python regex can hold the GIL). Now require an actual
    # newline after the lang tag and after each row, with a lazy ``+?``.
    for m in re.findall(r"```(?:markdown)?\n((?:\|[^\n]*\n)+?)```", text):
        if "|" in m:
            out.append(m.strip())
    # bare pipe-tables (allow last line to lack trailing newline)
    for m in re.findall(r"((?:^[ \t]*\|[^\n]*(?:\n|$)){2,})", text, re.MULTILINE):
        out.append(m.strip())
    out.sort(key=len, reverse=True)
    return out


def _markdown_to_df(md_table: str) -> Optional[pd.DataFrame]:
    lines = [ln.strip() for ln in md_table.split("\n") if ln.strip()]
    new_lines = []
    for ln in lines:
        if set(ln).issubset(set("|- :")) or "|" not in ln:
            continue
        cells = [c.strip() for c in ln.split("|")]
        if cells and cells[0] == "":
            cells = cells[1:]
        if cells and cells[-1] == "":
            cells = cells[:-1]
        new_lines.append("\t".join(cells))
    if len(new_lines) < 2:
        return None
    try:
        df = pd.read_csv(StringIO("\n".join(new_lines)), sep="\t", dtype=str).fillna("")
        df = df.loc[:, ~df.columns.astype(str).str.startswith("Unnamed")]
        if df.shape[0] >= 1 and df.shape[1] >= 1:
            return df
    except Exception as e:
        logger.debug("md→df parse failed: %s", e)
    return None


def extract_table_df(text: str) -> Optional[pd.DataFrame]:
    text = strip_citations(text)
    for cand in _candidate_tables(text):
        df = _markdown_to_df(cand)
        if df is not None:
            return df
    return None


def extract_all_tables(text: str) -> list[pd.DataFrame]:
    """Return every parseable markdown table in *text* (deduped, in
    document order). Used when the harness produced multiple sub-tables
    from multi-table planning that must be joined for evaluation."""
    text = strip_citations(text)
    seen = set()
    out: list[pd.DataFrame] = []
    cands = _candidate_tables(text)
    # candidates are sorted longest-first; preserve that ordering for join
    for cand in cands:
        key = cand.strip()
        if key in seen:
            continue
        seen.add(key)
        df = _markdown_to_df(cand)
        if df is None or df.empty:
            continue
        out.append(df)
    return out


def df_to_tsv_block(df: pd.DataFrame) -> str:
    lines = ["\t".join(map(str, df.columns))]
    for _, row in df.iterrows():
        lines.append("\t".join(str(v) for v in row.tolist()))
    return "```tsv\n" + "\n".join(lines) + "\n```"


def df_to_markdown_block(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    lines = ["| " + " | ".join(map(str, cols)) + " |",
             "|" + "|".join(["---"] * len(cols)) + "|"]
    for _, row in df.iterrows():
        lines.append("| " + " | ".join(str(v) for v in row.tolist()) + " |")
    return "```markdown\n" + "\n".join(lines) + "\n```"


def trim_extra_columns(
    df: pd.DataFrame,
    required_cols: list[str],
    *,
    target: str,
) -> tuple[Optional[str], pd.DataFrame, list[str]]:
    """Drop columns beyond *required_cols* and rename matches to the
    verbatim required names — WideSearch's strict set-equality scoring
    zeros an instance over a single surplus LLM-added column.

    Matching is looser than the scorer's ``norm_column`` (underscores/
    hyphens also stripped) since the reformat LLM emits "Mission_Name"
    variants. Only fires when every required column is present; returns
    (None, df, []) otherwise so the scorer surfaces the real gap.
    """
    from eval.scorers.widesearch_official.data_loader import norm_column

    def _norm(c: str) -> str:
        return norm_column(str(c)).replace("_", "").replace("-", "")

    df_norm_to_orig = {_norm(c): c for c in df.columns}
    req_norm = {_norm(rc) for rc in required_cols}
    if not all(_norm(rc) in df_norm_to_orig for rc in required_cols):
        return None, df, []
    extras = [c for c in df.columns if _norm(c) not in req_norm]
    if not extras:
        return None, df, []
    df = df.rename(columns={
        df_norm_to_orig[_norm(rc)]: rc for rc in required_cols
    })[list(required_cols)]
    block = df_to_tsv_block(df) if target == "gisa" else df_to_markdown_block(df)
    return block, df, extras


def load_session_output(workspace_path: str | Path) -> Optional[str]:
    """Fallback chain: result.json[answer] → conversation.jsonl last AI msg."""
    ws = Path(workspace_path)
    rj = ws / "output" / "result.json"
    if rj.exists():
        try:
            data = json.loads(rj.read_text(encoding="utf-8"))
            ans = data.get("answer")
            if isinstance(ans, str) and ans.strip():
                return ans
        except Exception as e:
            logger.warning("result.json parse failed (%s): %s", rj, e)

    conv = ws / "conversations" / "conversation.jsonl"
    if conv.exists():
        last_ai = None
        for ln in conv.read_text(encoding="utf-8").splitlines():
            try:
                obj = json.loads(ln)
            except Exception:
                continue
            if obj.get("role") in ("assistant", "ai") or obj.get("type") == "ai":
                content = obj.get("content")
                if isinstance(content, str) and content.strip():
                    last_ai = content
        if last_ai:
            return last_ai
    return None


def reformat_for_benchmark(
    raw_text: str, target: str
) -> tuple[Optional[str], Optional[pd.DataFrame]]:
    """Rule-only fallback: pick the longest table, dump as TSV/markdown.

    For full multi-table-join + format-respecting output, use
    ``join_and_reformat_with_llm``.
    """
    df = extract_table_df(raw_text)
    if df is None:
        return None, None
    df, _ = canonicalize_cells(df)
    if target == "gisa":
        return df_to_tsv_block(df), df
    if target == "widesearch":
        return df_to_markdown_block(df), df
    raise ValueError(f"unknown target: {target}")


# ---------- LLM-driven join + reformat ----------

_JOIN_REFORMAT_PROMPT = """\
You are formatting the FINAL answer for a benchmark question.

Below are one or more sub-tables extracted from a research report. The \
tables may have been produced by a multi-table planning workflow and \
together hold the data needed to answer the user's question. Your job:

1. **Join / merge** the sub-tables into a single table that answers the \
question. If a column appears in multiple sub-tables, keep one. If \
sub-tables describe rows from different categories (e.g. one per \
year / per region), concatenate the rows.

2. **Drop confirmed-negative rows** — rows whose answer-column value \
explicitly states the entity does NOT satisfy the user's implicit \
predicate. Typical signals (any language): 「未招生」「不招生」「不开设」\
「未设置」「未开设」「无该专业」「停招」「not offered」「not \
available」「not enrolled」「does not offer」「discontinued」. These \
rows answer "this entity does not qualify" and MUST be removed.

   DO NOT drop rows whose answer column reads 「待确认」「需进一步核实」\
「未明确列出」「需查看附件」「—」「-」「N/A」 (empty / partial / \
uncertain). Those are data-gathering misses, not negative answers; keep \
them so the user sees the gap.

   DO NOT drop rows whose value is merely surprising in magnitude (very \
high / very low score, unusual price). Drop only on confirmed negative \
existence, not on the value itself.

3. **Respect the user's column directives**: emit columns in the order \
the user specified, with the user's column names verbatim.

3b. **Numeric values are VERBATIM**: copy every number exactly as it \
appears in the sub-tables. NEVER rescale, re-denominate, convert units, \
round, or "normalize" a number (e.g. 1310 must stay 1310 — not 131, not \
1310.0亿). Unit conversion was already done upstream; doing it again \
corrupts the data. NEVER pad decimals to a fixed width — even when the \
question demands a fixed decimal count ("retained to two decimals"), \
keep the minimal form: 19.0 stays 19.0 (not 19.00), 19 stays 19. \
Decimal-place directives in the question are presentation hints the \
scorer does not honor; padding zeros turns correct values into misses.
4. **Normalize every column to ONE consistent format.**
   a. Format directives come from three places, in priority order: \
(1) the explicit column-format block below; (2) a unit string LITERALLY \
written in the column name (e.g. a parenthesized unit) — convert values \
to that unit and emit the bare number; (3) format conventions stated \
anywhere in the user question. A column name that merely describes a \
quantity ("Battery Capacity", "RAM Size") carries NO unit directive.
   b. Apply format EXAMPLES exactly, including component ordering and \
separators: an example like "2340x1080" fixes the separator AND which \
component comes first — reorder values to match it.
   c. Dates with no explicit directive: use numeric ISO style (yyyy-mm-dd, \
or yyyy-mm when only year and month are known). Never spell out month names.
   d. Multi-value cells: plain values joined by "; " in ranked order — no \
"1st:/2nd:" labels, no line breaks inside a cell. Never rewrite a SINGLE \
value into a composite form the source doesn't show.
   e. Columns WITHOUT a unit directive: keep each value exactly as the \
source shows it, INCLUDING its unit suffix ("3GB" stays "3GB", "2550mAh" \
stays "2550mAh"). Do NOT strip units. Within such a column, when most \
values carry the same unit suffix and a few are bare numbers of \
compatible magnitude, append that same unit to the bare values (never \
invent a different unit).
   f. **Unit reconciliation** — only for columns WITH a unit directive \
(from a(1)/a(2)): when a MINORITY of rows clearly use a different scale \
(off by a clean power-of-ten, mixed-locale sources), convert that minority \
to the directed unit. The directed unit always wins; when judging which \
rows are off, the majority magnitude is the reference — NEVER rescale the \
majority to match a minority. If the source unit of a row cannot be \
determined, keep its original value; never guess a conversion.
   g. Use one canonical surface form for repeated names / enum values \
across rows; prefer the form the user's question itself uses, if any.
   If a cell cannot be normalized from the data shown, keep the original \
value rather than guessing.
5. **Enforce the question's row constraints** — apply every entry under \
"Hard row constraints" below; a row failing any of them must be dropped. \
When the question caps the row count (a top-N / first-N directive), sort \
by the stated quantity first, then emit EXACTLY N rows.
6. **Respect any sort directive** (chronological / by rank / etc.).
7. Drop any ``[N]`` citation markers — output plain values only.

Output format: a single fenced block, exactly:
```{fence_lang}
{example_layout}
```
No commentary, no extra prose.

==== User question ====
{original_query}

==== Required columns (in order) ====
{required_columns}

==== Column value formats ====
{column_formats_block}

==== Sort directive ====
{sort_block}

==== Hard row constraints ====
{filters_block}

==== Sub-tables extracted from the report ====
{tables_block}
"""


def _format_tables_block(tables: list[pd.DataFrame]) -> str:
    parts = []
    for i, df in enumerate(tables, 1):
        parts.append(f"--- table {i} ({df.shape[0]} rows × {df.shape[1]} cols) ---")
        parts.append("| " + " | ".join(map(str, df.columns)) + " |")
        parts.append("|" + "|".join(["---"] * len(df.columns)) + "|")
        for _, row in df.iterrows():
            parts.append("| " + " | ".join(str(v) for v in row.tolist()) + " |")
        parts.append("")
    return "\n".join(parts) if parts else "(no tables extracted)"


# ---------- code-side deterministic join (plan by LLM, execute by code) ----

_JOIN_PLAN_PROMPT = """\
You are planning how to JOIN several sub-tables into one answer table.

A multi-table research workflow produced the sub-tables below. Some hold the \
main rows (one row per answer entity); others are LOOKUP tables that map a \
key (e.g. a year + a score) to extra columns the answer needs (e.g. a count). \
Do NOT merge them by reasoning over values yourself — instead emit a PLAN and \
deterministic code will perform the join, so counts are never mis-associated \
or carried across the wrong key.

Decide:
1. Which table is the BASE (the one whose rows become the answer rows).
2. For each remaining table that supplies answer columns, the equi-join keys \
that connect it to the base, and which of its columns to bring over.

A lookup row matches a base row only when ALL key pairs are equal. If a base \
row has no matching lookup row, the brought columns stay EMPTY — that is \
correct; never substitute a value from a different key (e.g. don't fill a \
2020 row from 2024 lookup data just because the score matches).

Return STRICT JSON, no prose, exactly this shape:
{{
  "needs_join": true,
  "base_table": <int, 1-based index>,
  "joins": [
    {{
      "lookup_table": <int, 1-based index>,
      "on": [["<base column>", "<lookup column>"], ...],
      "bring": [["<output column>", "<lookup column>"], ...]
    }}
  ]
}}

Set "needs_join": false when the tables are NOT complementary — e.g. they are \
the same shape and should simply be stacked/concatenated, or there is only \
one table. In that case omit the other fields.

==== Required output columns (in order) ====
{required_columns}

==== Sub-tables (headers + sample rows) ====
{tables_sample}
"""


def _format_tables_for_plan(tables: list[pd.DataFrame], sample: int = 6) -> str:
    parts = []
    for i, df in enumerate(tables, 1):
        parts.append(f"--- table {i} ({df.shape[0]} rows × {df.shape[1]} cols) ---")
        parts.append("columns: " + " | ".join(map(str, df.columns)))
        parts.append("sample rows:")
        for _, row in df.head(sample).iterrows():
            parts.append("  " + " | ".join(str(v) for v in row.tolist()))
        parts.append("")
    return "\n".join(parts)


def _parse_plan_json(text: str) -> Optional[dict]:
    t = (text or "").strip()
    t = re.sub(r"^```[a-zA-Z]*[ \t]*\n?", "", t)
    t = re.sub(r"\n?[ \t]*```\s*$", "", t).strip()
    # Tolerate leading prose before the object.
    m = re.search(r"\{.*\}", t, re.DOTALL)
    if m:
        t = m.group(0)
    try:
        obj = json.loads(t)
        return obj if isinstance(obj, dict) else None
    except Exception as e:
        logger.debug("join plan JSON parse failed: %s", e)
        return None


def _execute_join_plan(
    tables: list[pd.DataFrame], plan: dict,
) -> Optional[pd.DataFrame]:
    """Run the LLM's join plan with pandas. Returns the merged frame, or
    None on any structural mismatch (so the caller falls back to handing
    the raw sub-tables to the formatting LLM)."""
    try:
        bi = int(plan["base_table"]) - 1
    except (KeyError, TypeError, ValueError):
        return None
    if not (0 <= bi < len(tables)):
        return None

    def _clean(df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df.columns = [str(c).strip() for c in df.columns]
        for c in df.columns:
            df[c] = df[c].astype(str).str.strip()
        return df

    base = _clean(tables[bi])
    for j in plan.get("joins", []) or []:
        try:
            li = int(j["lookup_table"]) - 1
            on_pairs = [(str(a).strip(), str(b).strip()) for a, b in j["on"]]
            bring = [(str(o).strip(), str(s).strip()) for o, s in j["bring"]]
        except (KeyError, TypeError, ValueError):
            return None
        if not (0 <= li < len(tables)) or not on_pairs or not bring:
            return None
        lk = _clean(tables[li])
        base_keys = [a for a, _ in on_pairs]
        lk_keys = [b for _, b in on_pairs]
        if any(k not in base.columns for k in base_keys):
            return None
        if any(k not in lk.columns for k in lk_keys):
            return None
        if any(s not in lk.columns for _, s in bring):
            return None
        right = lk[lk_keys + [s for _, s in bring]].drop_duplicates(subset=lk_keys)
        rename = {lk_keys[i]: base_keys[i] for i in range(len(lk_keys))}
        rename.update({s: o for o, s in bring})
        right = right.rename(columns=rename)
        # lookup-supplied columns win over any same-named base column
        for o, _ in bring:
            if o in base.columns:
                base = base.drop(columns=[o])
        base = base.merge(right, on=base_keys, how="left")
    return base.fillna("")


async def _maybe_code_join(
    tables: list[pd.DataFrame],
    *,
    original_query: str,
    required_columns: Optional[list[str]],
    role: str,
) -> Optional[pd.DataFrame]:
    """Plan (LLM) + execute (pandas) a deterministic join of *tables*.
    Returns the merged single frame, or None to fall back to LLM join."""
    prompt = _JOIN_PLAN_PROMPT.format(
        required_columns=", ".join(required_columns) if required_columns
        else "(unknown — infer from the sub-tables)",
        tables_sample=_format_tables_for_plan(tables),
    )
    content = await invoke_reformat_model(prompt, role=role)
    plan = _parse_plan_json(content)
    if not plan or not plan.get("needs_join") or not plan.get("joins"):
        logger.info("code-join: plan declined join (needs_join=%s)",
                    plan.get("needs_join") if plan else None)
        return None
    merged = _execute_join_plan(tables, plan)
    if merged is None or merged.empty:
        logger.warning("code-join: plan execution failed; falling back to LLM join")
        return None
    logger.info("code-join: merged %d sub-tables → %d rows × %d cols",
                len(tables), merged.shape[0], merged.shape[1])
    return merged


async def invoke_reformat_model(prompt: str, *, role: str = "reformat") -> str:
    """One reformat-LLM call; returns the text content ('' on failure)."""
    from langchain_core.messages import HumanMessage
    from searchos.config.models import get_model_for

    model = get_model_for(role)
    try:
        ai = await model.ainvoke([HumanMessage(content=prompt)])
        content = getattr(ai, "content", "") or ""
        if isinstance(content, list):
            content = "".join(
                p.get("text", "") if isinstance(p, dict) else str(p) for p in content
            )
        return content
    except Exception as e:
        logger.warning("reformat model call failed: %s", e)
        return ""


def _strip_fence(text: str, lang: str) -> str:
    """Iteratively peel off ```lang ... ``` fences, including nested or
    dangling variants. LLMs sometimes emit ```markdown\\n```markdown\\n table
    \\n```\\n``` — a non-greedy regex would match outer-open to first-close
    and leave a dangling inner fence. So we strip from BOTH ends until
    the layer is gone or a fixed point is reached.
    """
    text = (text or "").strip()
    for _ in range(4):
        changed = False
        new = re.sub(rf"^```{lang}[ \t]*\n?", "", text)
        if new != text:
            text, changed = new, True
        new = re.sub(r"^```[a-zA-Z]*[ \t]*\n?", "", text)
        if new != text:
            text, changed = new, True
        new = re.sub(r"\n?[ \t]*```\s*$", "", text)
        if new != text:
            text, changed = new, True
        if not changed:
            break
        text = text.strip()
    return text


_BARE_NUM_RE = re.compile(r"^[-+]?\d[\d,]*(?:\.\d+)?$")


def _cell_num(cell) -> Optional[float]:
    t = str(cell).strip()
    if not _BARE_NUM_RE.match(t):
        return None
    try:
        return float(t.replace(",", ""))
    except ValueError:
        return None


def enforce_numeric_fidelity(
    df_out: pd.DataFrame, src_tables: list[pd.DataFrame],
) -> tuple[pd.DataFrame, int]:
    """Restore bare-number cells the reformat LLM rescaled by 10^k.

    Observed failure (ws_zh_004, 2026-06-11): the LLM emitted an entire
    wealth column divided by 10 (1310 → 131) — and the corruption is
    nondeterministic across runs, so a deterministic guard is the fix.
    Conservative by construction; a cell is restored ONLY when:
      - it parses as a bare number that does NOT appear in the sources,
      - exactly ONE source value equals it × / ÷ {10,100,1000},
      - and that source row shares a non-numeric cell with the output row
        (so a genuinely different number is never "fixed").
    """
    src_rows: list[tuple[float, str, set]] = []
    src_nums: set[float] = set()
    for t in src_tables:
        for _, row in t.iterrows():
            texts = {str(c).strip() for c in row
                     if _cell_num(c) is None and str(c).strip()}
            for cell in row:
                v = _cell_num(cell)
                if v is not None:
                    src_nums.add(round(v, 6))
                    src_rows.append((v, str(cell).strip(), texts))
    if not src_rows:
        return df_out, 0
    fixed = 0
    for ri in range(len(df_out)):
        row = df_out.iloc[ri]
        row_texts = {str(c).strip() for c in row
                     if _cell_num(c) is None and str(c).strip()}
        for col in df_out.columns:
            v = _cell_num(df_out.iloc[ri][col])
            if v is None or v == 0 or round(v, 6) in src_nums:
                continue
            matches: set[str] = set()
            for k in (10.0, 100.0, 1000.0):
                for cand in (v * k, v / k):
                    for sv, ss, stexts in src_rows:
                        if sv and abs(sv - cand) <= abs(sv) * 1e-9 \
                                and (row_texts & stexts):
                            matches.add(ss)
            if len(matches) == 1:
                df_out.iat[ri, df_out.columns.get_loc(col)] = next(iter(matches))
                fixed += 1
    return df_out, fixed


_DECIMAL_CELL_RE = re.compile(r"^[+-]?\d+\.\d+$")
_SHORT_YEAR_DATE_RE = re.compile(r"^(\d{1,2})([-/.])(\d{1,2})\2(\d{2})$")


def _canon_cell(cell) -> str:
    s = str(cell).strip()
    if _DECIMAL_CELL_RE.match(s):
        # Match the scorer's gold surface form: gold CSVs are read by
        # pandas, so numeric columns become float64 and astype(str) yields
        # the Python float repr ('19.00 ' → '19.0'). A response cell padded
        # to fixed decimals ('19.00') therefore fails exact_match even when
        # the value is right (ws_en_019 zeroed 5/5 rows this way). Strip
        # trailing zeros but keep one fractional digit; integers stay
        # untouched (an int-typed gold column stringifies without '.0').
        s2 = s.lstrip("+").rstrip("0")
        return s2 + "0" if s2.endswith(".") else s2
    m = _SHORT_YEAR_DATE_RE.match(s)
    if m:
        # Two-digit years never survive exact/judge comparison against
        # gold's four-digit form ('08-16-04' vs '08-16-2004', ws_en_016).
        # Only fires when the WHOLE cell is a date with a trailing 2-digit
        # year; separators and zero-padding are preserved.
        century = "20" if int(m.group(4)) <= 49 else "19"
        return f"{m.group(1)}{m.group(2)}{m.group(3)}{m.group(2)}{century}{m.group(4)}"
    return cell


def canonicalize_cells(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Deterministic scorer-canonical surface forms for every data cell.

    Applied after any LLM reformat so a prompt-level miss (or a question
    that itself demands a scoring-hostile format, e.g. "retained to two
    decimals") cannot leak into the graded output. Cell-local and
    idempotent; never changes a value, only its surface form.
    """
    changed = 0
    out = df.copy()
    for ci in range(out.shape[1]):
        for ri in range(out.shape[0]):
            v = out.iat[ri, ci]
            nv = _canon_cell(v)
            if nv != str(v):
                out.iat[ri, ci] = nv
                changed += 1
    return out, changed


async def join_and_reformat_with_llm(
    raw_text: str,
    *,
    target: str,
    original_query: str,
    required_columns: Optional[list[str]] = None,
    column_formats: Optional[dict[str, str]] = None,
    sort_hint: str = "",
    filters: Optional[list[str]] = None,
    role: str = "reformat",
    max_retries: int = 2,
) -> tuple[Optional[str], Optional[pd.DataFrame]]:
    """Join multi-tables in *raw_text* + reformat per *original_query* via LLM.

    ``column_formats`` / ``sort_hint`` / ``filters`` come from the eval
    preprocess step (clean_query) and are passed verbatim into the prompt
    to spare the reformat LLM from re-parsing them out of the raw question.
    """
    tables = extract_all_tables(raw_text)
    if not tables:
        return None, None

    # Multi-table answers (e.g. a main table + a per-key lookup table) must
    # be joined on exact keys. Letting the formatting LLM "eyeball" the join
    # mis-associates values across rows/keys (ws_zh_008: 2024 lookup counts
    # bled onto 2020 rows). Do the join in code; hand the LLM ONE table.
    if len(tables) >= 2:
        merged = await _maybe_code_join(
            tables,
            original_query=original_query,
            required_columns=required_columns,
            role=role,
        )
        if merged is not None and not merged.empty:
            tables = [merged]

    if target == "gisa":
        fence_lang = "tsv"
        example_layout = "col1\tcol2\tcol3\nval1\tval2\tval3"
    elif target == "widesearch":
        fence_lang = "markdown"
        example_layout = "| col1 | col2 | col3 |\n|---|---|---|\n| val1 | val2 | val3 |"
    else:
        raise ValueError(f"unknown target: {target}")

    if column_formats:
        formats_block = "\n".join(f"- {c}: {f}" for c, f in column_formats.items() if f)
    else:
        formats_block = "(none specified — infer from question if needed)"
    sort_block = sort_hint.strip() or "(none specified)"
    filters_block = "\n".join(f"- {f}" for f in (filters or []) if str(f).strip()) \
        or "(none specified — apply any constraint stated in the question itself)"

    prompt = _JOIN_REFORMAT_PROMPT.format(
        fence_lang=fence_lang,
        example_layout=example_layout,
        original_query=original_query,
        required_columns=", ".join(required_columns) if required_columns else "(unknown — infer from question)",
        column_formats_block=formats_block,
        sort_block=sort_block,
        filters_block=filters_block,
        tables_block=_format_tables_block(tables),
    )

    last_content = ""
    for attempt in range(max_retries):
        content = await invoke_reformat_model(prompt, role=role)
        last_content = content
        body = _strip_fence(content, fence_lang)
        if not body:
            continue

        if target == "gisa":
            try:
                df = pd.read_csv(StringIO(body), sep="\t", dtype=str).fillna("")
                df = df.loc[:, ~df.columns.astype(str).str.startswith("Unnamed")]
                if df.shape[0] >= 1 and df.shape[1] >= 1:
                    df, nfix = enforce_numeric_fidelity(df, tables)
                    if nfix:
                        logger.warning(
                            "numeric fidelity: restored %d rescaled cell(s)", nfix)
                    df, ncanon = canonicalize_cells(df)
                    if nfix or ncanon:
                        body = "\n".join(
                            ["\t".join(map(str, df.columns))]
                            + ["\t".join(str(x) for x in r.tolist())
                               for _, r in df.iterrows()])
                    return f"```tsv\n{body}\n```", df
            except Exception as e:
                logger.debug("LLM TSV parse fail: %s", e)
        else:
            df = _markdown_to_df(body)
            if df is not None and not df.empty:
                df, nfix = enforce_numeric_fidelity(df, tables)
                if nfix:
                    logger.warning(
                        "numeric fidelity: restored %d rescaled cell(s)", nfix)
                df, ncanon = canonicalize_cells(df)
                if nfix or ncanon:
                    body = df_to_markdown_block(df)
                    body = body.removeprefix("```markdown\n").removesuffix("\n```")
                return f"```markdown\n{body}\n```", df

    logger.warning("join_and_reformat fell back to rule-only; raw[-200:]=%s",
                   (last_content or "")[-200:])
    return reformat_for_benchmark(raw_text, target=target)
