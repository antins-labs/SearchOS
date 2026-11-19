from __future__ import annotations

import json
from datetime import date
from typing import Sequence

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

__all__ = [
    "COVERAGE_AWARE_ROW_PROMPT",
    "FILL_ROW_PROMPT",
    "DISCOVER_ROW_PROMPT",
    "build_coverage_aware_row_prompt",
    "build_discover_row_prompt",
    "build_fill_row_prompt",
    "build_coverage_aware_row_messages",
    "build_discover_row_messages",
    "build_fill_row_messages",
    "prompt_text",
]


def prompt_text(prompt: str | Sequence[BaseMessage | str]) -> str:
    """Flatten a string or chat messages for tests / length checks."""
    if isinstance(prompt, str):
        return prompt
    return "\n".join(
        part if isinstance(part, str) else str(getattr(part, "content", part))
        for part in prompt
    )


def _render_row_key_example(primary_key: list[str], data_columns: list[str]) -> str:
    return ", ".join(
        f'"{name}": "<value>"' for name in primary_key
    ) + "".join(f', "{name}": "<value or null>"' for name in data_columns)


def _render_column_desc_block(
    primary_key: list[str], data_columns: list[str], column_desc: dict | None,
) -> str:
    lines = []
    for col in primary_key + data_columns:
        cd = (column_desc or {}).get(col)
        if cd is None:
            continue
        parts = [getattr(cd, "type", "str") or "str", getattr(cd, "desc", "") or ""]
        check = getattr(cd, "check", None)
        rules = []
        if check is not None:
            if getattr(check, "enum", None) is not None:
                rules.append(f"one of {check.enum}")
            if getattr(check, "min", None) is not None:
                rules.append(f">= {check.min:g}")
            if getattr(check, "max", None) is not None:
                rules.append(f"<= {check.max:g}")
        if rules:
            parts.append(
                "HARD CHECK (ingest rejects violations; lists checked element-wise): "
                + ", ".join(rules)
            )
        lines.append(f"- {col}: {'. '.join(part for part in parts if part)}")
    return "\n## Column descriptions\n" + "\n".join(lines) + "\n" if lines else ""


_SCHEMA = """\
You are a structured data extractor.
## Primary key
{primary_key}
## Data columns
{data_columns}{column_desc_block}
"""

_OUTPUT = """\
## Output format
Return ONLY one JSON array of row objects; [] is valid when no row qualifies.
Include every schema column with its exact name; unstated data values are JSON null.
[{{{key_example}, "_source_page": 1, "_source_excerpt": "<verbatim passages>",
"_alignment": {{"<non-null column>": "full|partial"}}, "_alignment_note": "<support boundary>",
"_confidence": "high|medium|low", "_source_authority": "official|aggregator|news|blog|unclear"}}]
- ONE ROW = ONE PAGE. `_source_page` must match its "### Page N" number. Quote only that page.
For the same identity supported by several pages, emit separate objects per page with only
that page's values.
- `_source_excerpt` must quote the passages supporting the emitted values, under about 400
characters. Copy characters exactly; join distant passages with " … ". A value without a
supporting quote stays null.
JSON excerpts retain quoted keys; join exact field fragments with … . Use JSON string escaping
in output.
- On skill:// or agent:// pages, add `_source_urls`: a map from each non-null column, including
every primary-key field used to establish a new identity, to its
supporting original URLs or evidence:IDs copied from that observation or its Declared source
links. Keep provenance per field; unknown provenance is [].
- Each primary-key field keeps its own value, including literal `|` characters. Reuse a
canonical identity only when the page clearly matches it. Existing table values guide identity
matching; quoted pages support newly emitted facts.
- Linked directory records may supply identity when their observed target URL matches this
page's declared original URL. Parent fields keep their enclosing directory identity. Data values
and quotes still come from the current page; leave ambiguous identities unresolved.
"""

_RULES = """\
## Evidence rules
- Scope: emit real entities within the overall goal's dates, rank/top-N cutoff, region, language
and include/exclude lists. The assignment selects where to look; all entities within the overall
goal remain eligible unless explicit write targets restrict this call. Never invent members to
complete a set.
- Identity: at least one primary-key field must be supported by the page or an explicitly linked
directory record. Primary-key fields the page does not state are null (they normalize to "/").
A supported new identity qualifies with all attributes null (identity-only); its quoted page must
support every non-null primary-key value.
- Values: extract what this page explicitly states for this entity and column. Keep unknown
fields null. Memory, typical values, another entity's attributes and unsupported repetition cannot
supply a field. Verify repeated values for each entity separately. Exclude website-operator
boilerplate such as copyright, filing numbers and contact blocks.
- TEMPORAL FIT IS REQUIRED: match the fact's event/effective date or reporting period to the task
and column. The publication date is metadata; establish the fact's applicable period separately.
For current/latest/as-of columns, require support at the requested cutoff; choose matching periods
by meaning. A future target, forecast, schedule or announcement qualifies only for a column
requesting that planned status; preserve its date and status.
- Resolve relative dates using the runtime's authoritative current date
unless the task specifies another reference date.
A date later than your training cutoff does not by itself invalidate a record: evaluate the
source's stated event and status.
- NO ARITHMETIC, NO CONVERSION: copy source numbers, units, currency and wording. The runtime
converts units after ingest. Keep computed sums, differences, averages, rates, rescaling and
missing components null unless printed explicitly. A printed total and one component do not
support subtraction; per-period figures require a printed total for a whole-period column.
- Preserve source precision and qualifying scope: subgroup, version, period and other conditions.
Broader-group facts apply when the source explicitly covers the requested subgroup. Retain
incomplete scope or precision as `partial` for that field, quoting its actual scope. Keep unrelated
fields null. For composite values select the requested component; retain all relevant stated
tiers. A bare "varies/depends" supplies no figure.
- URLs: copy a complete observed URL/href, the page's Source address or a Declared source link.
Preserve the full address; leave bare-domain completions and invented paths null. An
original-article column requires its observed article address. Search snippets establish only
their visible content and links.
- Explicit absence: when an authoritative source states that a value does not exist or is
unpublished, copy that statement in its own words. An unsuccessful search leaves the cell null.
- `_alignment` evaluates each non-null field independently: `full` supports the requested entity
and conditions; `partial` has incomplete scope or precision. Include primary-key alignment for
identity-only rows. Null or partial fields leave other fields' support unchanged.
- `_alignment_note` describes the observed support and its limits. `_source_authority` describes
this page's publisher and role; a roundup quoting an official announcement remains `aggregator`.
- `_confidence`: high requires every non-null value verbatim in the quote; medium allows visible
table/chart context; weaker support is low. Return [] whenever the active mode has no supported row.

## Format examples
Example columns and facts apply only to their example. Use the active schema, mode and actual pages.
1. Missing attribute; single primary key ["Name"], data ["Size", "Power"].
Page 1: "Orion size: 500 ml."
Output: [{{"Name":"Orion","Size":"500 ml","Power":null,"_source_page":1,
"_source_excerpt":"Orion size: 500 ml.","_alignment":{{"Size":"full"}},
"_confidence":"high","_source_authority":"unclear"}}]
2. Composite key and literal separator; PK ["Maker", "Model"], data ["Size"].
Canonical row: ["Acme", "Blue|Label", null]. Page 1: "Maker Acme; model Blue|Label; size 375 ml."
Output: [{{"Maker":"Acme","Model":"Blue|Label","Size":"375 ml","_source_page":1,
"_source_excerpt":"Maker Acme; model Blue|Label; size 375 ml.","_alignment":{{"Size":"full"}},
"_confidence":"high","_source_authority":"unclear"}}]
3. Identity-only discovery; PK ["Maker", "Model"], data ["Size"].
Page 1: "Maker Acme lists model Nova."
Output: [{{"Maker":"Acme","Model":"Nova","Size":null,"_source_page":1,
"_source_excerpt":"Maker Acme lists model Nova.","_alignment":{{"Maker":"full","Model":"full"}},
"_confidence":"high","_source_authority":"unclear"}}]
4. Independent field support; PK ["Name"], data ["Size", "Power"].
Page 1: "Orion size 500 ml; Orion power about 80 W."
Output: [{{"Name":"Orion","Size":"500 ml","Power":"about 80 W","_source_page":1,
"_source_excerpt":"Orion size 500 ml; Orion power about 80 W.",
"_alignment":{{"Size":"full","Power":"partial"}},"_alignment_note":"Power is approximate.",
"_confidence":"high","_source_authority":"unclear"}}]
5. No supported row eligible for this mode: []
6. Separate sources; PK ["Name"], data ["Size", "Power"].
Page 1: "Orion size 500 ml." Page 2: "Orion power 80 W."
Output: [{{"Name":"Orion","Size":"500 ml","Power":null,"_source_page":1,
"_source_excerpt":"Orion size 500 ml.","_alignment":{{"Size":"full"}}}},
{{"Name":"Orion","Size":null,"Power":"80 W","_source_page":2,
"_source_excerpt":"Orion power 80 W.","_alignment":{{"Power":"full"}}}}]
7. JSON field fragments; PK ["Maker","Name"], data ["Size","Power"].
Page 1: {{"maker": "Acme", "items": [{{"name": "Orion", "skip": 0, "size": "500 ml"}}]}}
Output: [{{"Maker":"Acme","Name":"Orion","Size":"500 ml","Power":null,"_source_page":1,
"_source_excerpt":"\\\"maker\\\": \\\"Acme\\\" … \
\\\"name\\\": \\\"Orion\\\" … \\\"size\\\": \\\"500 ml\\\"",
"_alignment":{{"Size":"full"}}}}]
"""

_DYNAMIC = """\
## Overall research goal
{global_task}
## Current sub-agent assignment
{sub_agent_task}
## Runtime as-of date
{current_date}
"""

_MODE_FILL = """\
## FILL MODE
Output only listed existing identities with a page-supported value for at least one eligible
fill target. Copy each primary-key field exactly from its coverage column; set other data columns
to null. Return [] when no listed target is supported.
Coverage columns define row-array order; cell objects give values and unresolved status.
Fill targets use zero-based row and column indices.
"""

_MODE_DISCOVER = """\
## DISCOVER MODE
Output only new primary keys absent from the known inventory. Date formatting, casing and
punctuation variants of a known identity remain known. Copy each new key's own value from the
page; fill supported attributes and keep others null. Identity-only rows qualify. Return [] if
all supported identities are already known.
"""

_MODE_COVERAGE = """\
## Source-driven extraction
Use source-driven extraction: read the pages using the schema and task scope. Emit supported
candidates for existing and new identities; evaluate every field independently. The commit layer
resolves canonical identities and table updates. Optional canonical identity hints assist a clear
match; they impose no inventory or completion requirement. Explicit task write targets constrain
all candidates.
"""

_HUMAN_FILL = _DYNAMIC + _MODE_FILL + """\
## Rows needing data
{coverage_snapshot}
## Pages
{pages_block}
"""

_HUMAN_DISCOVER = _DYNAMIC + _MODE_DISCOVER + """\
## Known rows
{known_pk_list}
## Pages
{pages_block}
"""

_HUMAN_COVERAGE = _DYNAMIC + _MODE_COVERAGE + """\
## Optional canonical identity hints
{coverage_snapshot}
## Pages
{pages_block}
"""

_SYSTEM_FILL = _SCHEMA + _OUTPUT + _RULES
_SYSTEM_DISCOVER = _SCHEMA + _OUTPUT + _RULES
_SYSTEM_COVERAGE = _SCHEMA + _OUTPUT + _RULES

# Concatenated templates kept for callers/tests that still inspect a single string.
FILL_ROW_PROMPT = _SYSTEM_FILL + _HUMAN_FILL
DISCOVER_ROW_PROMPT = _SYSTEM_DISCOVER + _HUMAN_DISCOVER
COVERAGE_AWARE_ROW_PROMPT = _SYSTEM_COVERAGE + _HUMAN_COVERAGE


def _render_pages_block(pages: list[dict[str, str]]) -> str:
    parts = []
    for i, page in enumerate(pages, 1):
        lines = [f"### Page {i}", f"Source: {page.get('source_url', '')}"]
        if page.get("page_id"):
            lines.append(f"Page ID: {page['page_id']}")
        if parent := page.get("referring_page"):
            lines.append(
                "Page linking to this attachment (subject and date context): "
                f"{parent[1]} ({parent[0]})"
            )
        if page.get("linked_records"):
            lines.append(
                "Linked directory records (entity identity only):\n"
                + json.dumps(page["linked_records"], ensure_ascii=False)
            )
        if page.get("source_urls"):
            lines.append(f"Declared source links: {page['source_urls']}")
        lines.append(page.get("content", ""))
        parts.append("\n".join(lines))
    return "\n\n".join(parts)


def _format_kwargs(
    *, global_task: str, sub_agent_task: str,
    primary_key: list[str], data_columns: list[str], column_desc: dict | None,
    pages: list[dict[str, str]], **view: str,
) -> dict[str, str]:
    return dict(
        current_date=date.today().isoformat(),
        global_task=global_task or sub_agent_task,
        sub_agent_task=sub_agent_task,
        primary_key=list(primary_key),
        data_columns=list(data_columns),
        column_desc_block=_render_column_desc_block(primary_key, data_columns, column_desc),
        pages_block=_render_pages_block(pages),
        key_example=_render_row_key_example(primary_key, data_columns),
        **view,
    )


def _build_parts(
    system_template: str, human_template: str, *, global_task: str, sub_agent_task: str,
    primary_key: list[str], data_columns: list[str], column_desc: dict | None,
    pages: list[dict[str, str]], **view: str,
) -> tuple[str, str]:
    fields = _format_kwargs(
        global_task=global_task, sub_agent_task=sub_agent_task,
        primary_key=primary_key, data_columns=data_columns, column_desc=column_desc,
        pages=pages, **view,
    )
    return system_template.format(**fields), human_template.format(**fields)


def _build_prompt(
    template: str, *, global_task: str, sub_agent_task: str,
    primary_key: list[str], data_columns: list[str], column_desc: dict | None,
    pages: list[dict[str, str]], **view: str,
) -> str:
    return template.format(**_format_kwargs(
        global_task=global_task, sub_agent_task=sub_agent_task,
        primary_key=primary_key, data_columns=data_columns, column_desc=column_desc,
        pages=pages, **view,
    ))


def build_fill_row_prompt(
    *, global_task: str, sub_agent_task: str, primary_key: list[str],
    data_columns: list[str], column_desc: dict | None, pages: list[dict[str, str]],
    coverage_snapshot: str,
) -> str:
    return _build_prompt(
        FILL_ROW_PROMPT, global_task=global_task, sub_agent_task=sub_agent_task,
        primary_key=primary_key, data_columns=data_columns, column_desc=column_desc, pages=pages,
        coverage_snapshot=coverage_snapshot or "(no eligible fill targets; return [])",
    )


def build_discover_row_prompt(
    *, global_task: str, sub_agent_task: str, primary_key: list[str],
    data_columns: list[str], column_desc: dict | None, pages: list[dict[str, str]],
    known_pk_list: str,
) -> str:
    return _build_prompt(
        DISCOVER_ROW_PROMPT, global_task=global_task, sub_agent_task=sub_agent_task,
        primary_key=primary_key, data_columns=data_columns, column_desc=column_desc, pages=pages,
        known_pk_list=known_pk_list or "(empty inventory)",
    )


def build_coverage_aware_row_prompt(
    *, global_task: str = "", sub_agent_task: str, primary_key: list[str],
    data_columns: list[str], column_desc: dict | None, pages: list[dict[str, str]],
    coverage_snapshot: str,
) -> str:
    """构建原文驱动提示；保留原签名，view 可提供明确关联的规范身份。"""
    return _build_prompt(
        COVERAGE_AWARE_ROW_PROMPT, global_task=global_task, sub_agent_task=sub_agent_task,
        primary_key=primary_key, data_columns=data_columns, column_desc=column_desc, pages=pages,
        coverage_snapshot=coverage_snapshot or "(none)",
    )


def build_fill_row_messages(
    *, global_task: str, sub_agent_task: str, primary_key: list[str],
    data_columns: list[str], column_desc: dict | None, pages: list[dict[str, str]],
    coverage_snapshot: str,
) -> list[BaseMessage]:
    system, human = _build_parts(
        _SYSTEM_FILL, _HUMAN_FILL, global_task=global_task, sub_agent_task=sub_agent_task,
        primary_key=primary_key, data_columns=data_columns, column_desc=column_desc, pages=pages,
        coverage_snapshot=coverage_snapshot or "(no eligible fill targets; return [])",
    )
    return [SystemMessage(content=system), HumanMessage(content=human)]


def build_discover_row_messages(
    *, global_task: str, sub_agent_task: str, primary_key: list[str],
    data_columns: list[str], column_desc: dict | None, pages: list[dict[str, str]],
    known_pk_list: str,
) -> list[BaseMessage]:
    system, human = _build_parts(
        _SYSTEM_DISCOVER, _HUMAN_DISCOVER, global_task=global_task, sub_agent_task=sub_agent_task,
        primary_key=primary_key, data_columns=data_columns, column_desc=column_desc, pages=pages,
        known_pk_list=known_pk_list or "(empty inventory)",
    )
    return [SystemMessage(content=system), HumanMessage(content=human)]


def build_coverage_aware_row_messages(
    *, global_task: str = "", sub_agent_task: str, primary_key: list[str],
    data_columns: list[str], column_desc: dict | None, pages: list[dict[str, str]],
    coverage_snapshot: str,
) -> list[BaseMessage]:
    system, human = _build_parts(
        _SYSTEM_COVERAGE, _HUMAN_COVERAGE, global_task=global_task, sub_agent_task=sub_agent_task,
        primary_key=primary_key, data_columns=data_columns, column_desc=column_desc, pages=pages,
        coverage_snapshot=coverage_snapshot or "(none)",
    )
    return [SystemMessage(content=system), HumanMessage(content=human)]
