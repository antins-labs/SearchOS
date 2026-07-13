"""Report synthesis — deterministic coverage-table render + writer-finalize message.

The legacy LLM multi-stage prose fallback (build_prose_*) was dropped — the
writer agent produces the report body.

Output quality priorities:
1. Match user's language (Chinese query → Chinese report, English → English)
2. Tabular queries → markdown table as the primary answer
3. Every factual claim carries an inline [n] citation
4. Clean visual hierarchy: headers, bullets, table, sources block
"""

from __future__ import annotations

from typing import Any


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _detect_language(query: str) -> str:
    """Simple heuristic: if query has CJK chars, treat as Chinese."""
    cjk_count = sum(1 for c in query if '\u4e00' <= c <= '\u9fff')
    return "zh" if cjk_count > len(query) * 0.1 else "en"


# ---------------------------------------------------------------------------
# Deterministic synthesis: code-rendered coverage table + URL citations.
# The LLM never rewrites the table; prose (if any) is the writer agent's job.
# ---------------------------------------------------------------------------


def build_url_citation_map(evidence: list[Any]) -> dict[str, int]:
    """Return ``{source_url: citation_number}`` assigned in first-seen
    order. Findings from the same URL share one ``[N]`` in the rendered
    report, so the final "信息来源" list has each URL exactly once.
    """
    mapping: dict[str, int] = {}
    for n in evidence:
        url = (getattr(n, "source", "") or "").strip()
        if not url or url in mapping:
            continue
        mapping[url] = len(mapping) + 1
    return mapping


_ALIGN_RANK = {"full": 3, "partial": 2, "loose": 1, "": 0}
_AUTH_RANK = {"official": 5, "aggregator": 4, "industry_pr": 3,
              "news": 2, "blog": 1, "unclear": 0, "": 0}


def _normalize_token(s: str) -> str:
    """Strip wrapping quotes/whitespace, lowercase, collapse internal spaces.

    Used as the leaf of list-value normalization so that ``"Buzz Aldrin"``,
    ``'Buzz Aldrin'``, and ``Buzz  Aldrin`` all map to the same key.
    """
    import re
    s = (s or "").strip().strip("'\"`").strip()
    return re.sub(r"\s+", " ", s).lower()


def _canonicalize_list_value(text: str) -> str:
    """Normalize a cell value so equivalent surface forms collapse to one key.

    Different sub-agents extracting the same Wikipedia infobox produce the
    same crew list as ``['A', 'B', 'C']`` / ``"A, B, C"`` / ``[B, A, C]`` —
    surface forms differ but the information is identical. We strip outer
    brackets, split on common list separators (``, ; 、 ，``), normalize
    each item, sort for order-invariance, and join. Equivalent inputs
    collapse to the same string; non-list scalars fall through to
    ``_normalize_token``.

    This is a surface-level canonicalizer — it cannot bridge entity aliases
    (e.g. ``Buzz Aldrin`` vs ``Edwin "Buzz" Aldrin``); that's
    ``alias_resolver``'s job. The 80/20 win here is collapsing serialization
    variants of the SAME tokens, which is the bulk of duplication in wide-
    search outputs.
    """
    import re
    s = (text or "").strip()
    if not s:
        return ""
    # Strip outer list-literal / tuple brackets if balanced.
    if (s.startswith("[") and s.endswith("]")) or (
        s.startswith("(") and s.endswith(")")
    ):
        s = s[1:-1].strip()
    parts = re.split(r"[,;、，]\s*", s)
    if len(parts) <= 1:
        return _normalize_token(s)
    items = sorted({_normalize_token(p) for p in parts if _normalize_token(p)})
    return "|".join(items)


def _active_only(findings: list) -> list:
    """Conflict arbitration marks losing nodes superseded — never render them."""
    return [f for f in findings if getattr(f, "status", "active") == "active"]


def _is_trivial_for_list_cell(text: str) -> bool:
    """Filter values that the LLM wrongly stuffed into a list-typed cell.

    Pure-integer values (e.g. ``"3"``) are almost always a crew_size /
    item_count that the row-extraction prompt mis-routed into a person-
    list column. Keeping them produces false-positive variants in the
    rendered cell. Threshold of 100 is generous — any list of >100 named
    items would be unusual and we'd rather false-negative-keep than
    false-positive-drop on a genuine count cell rendered as list.
    """
    s = (text or "").strip().strip("'\"`")
    if not s:
        return False
    return s.isdigit() and len(s) <= 4


def _rank_f(f: Any) -> tuple:
    return (
        _ALIGN_RANK.get(getattr(f, "alignment", "") or "", 0),
        _AUTH_RANK.get(getattr(f, "source_authority", "") or "", 0),
        float(getattr(f, "confidence", 0.0) or 0.0),
    )


def _render_scalar_cell(
    findings: list[Any], url_map: dict[str, int],
) -> str:
    """Scalar cell: pick best finding; hedge with ◇（部分）when not full.

    Prefers ``EvidenceNode.value`` (cell-level value alone, e.g.
    "$97,690 million") over ``finding`` (the structured form with
    entity|attr prefix that's only useful in evidence logs).
    """
    best = max(findings, key=_rank_f)
    raw = (getattr(best, "value", "") or "").strip() or (getattr(best, "finding", "") or "")
    snippet = raw.replace("\n", " ").strip()
    url = (getattr(best, "source", "") or "").strip()
    cite = f" [{url_map[url]}]" if url in url_map else ""
    if (getattr(best, "alignment", "") or "") == "full":
        return f"{snippet}{cite}"
    return f"◇ {snippet}（部分）{cite}"


def _render_list_cell(
    findings: list[Any], url_map: dict[str, int], max_items: int = 5,
) -> str:
    """List cell: enumerate up to ``max_items`` distinct findings with
    inline citations. Each finding is a valid list item (partial ≠ hedge
    for lists). Falls back to hedged single item when only loose
    findings are available."""
    def _node_text(n: Any) -> str:
        return (getattr(n, "value", "") or "").strip() or (getattr(n, "finding", "") or "")

    non_loose = [
        f for f in findings
        if (getattr(f, "alignment", "") or "") in ("full", "partial")
    ]
    if not non_loose:
        best = max(findings, key=_rank_f)
        snippet = _node_text(best).replace("\n", " ").strip()
        url = (getattr(best, "source", "") or "").strip()
        cite = f" [{url_map[url]}]" if url in url_map else ""
        return f"◇ {snippet}（待确认）{cite}" if snippet else "—"

    ordered = sorted(non_loose, key=_rank_f, reverse=True)
    seen: set[str] = set()
    items: list[str] = []
    # Walk every finding to populate ``seen`` (the equivalence-class count
    # for the suffix), but only append the first ``max_items`` to
    # ``items``. Don't ``break`` early — that would undercount the
    # distinct classes and produce a wrong "(N items total)" suffix.
    for f in ordered:
        raw = _node_text(f)
        if _is_trivial_for_list_cell(raw):
            # Pure-integer dropped — LLM mis-routed crew_size into a
            # person-list cell. Don't surface it as a "candidate".
            continue
        snip = raw.replace("\n", " ").strip()
        if not snip:
            continue
        # Canonicalize the FULL raw value (not the truncated display form)
        # so that ``['A', 'B', 'C']`` / ``"A, B, C"`` / ``[B, A, C]``
        # collapse to one key. Display still uses the first-seen surface
        # form so the user sees readable text, not the canonical sort.
        key = _canonicalize_list_value(raw)
        if not key or key in seen:
            continue
        seen.add(key)
        if len(items) < max_items:
            url = (getattr(f, "source", "") or "").strip()
            cite = f" [{url_map[url]}]" if url in url_map else ""
            items.append(f"{snip}{cite}")
    if not items:
        return "—"
    joined = "; ".join(items)
    # ``items total`` reflects distinct equivalence classes (after canonical
    # collapse), NOT raw finding count — otherwise the suffix would read
    # ``11 items total`` when only 4 are actually different facts.
    if len(seen) > len(items):
        joined += f" ({len(seen)} items total)"
    return joined


def _render_cell_with_citation(
    cell: Any,
    evidence_by_id: dict,
    url_map: dict[str, int],
    attr_is_list: bool = False,
) -> str:
    """Render one CoverageCell as a markdown table cell string with [N]
    citations.

    Scalar (default): pick best finding. `full` → plain snippet;
    otherwise hedge with `◇（部分）`.

    List (``attr_is_list=True``): enumerate up to 5 distinct non-loose
    snippets joined with `; `; no hedge marker since list membership is
    additive, not an incomplete answer.

    Empty cell: `—`.
    """
    if cell is None or not cell.supporting_evidence_ids:
        return "—"
    findings = [evidence_by_id.get(fid) for fid in cell.supporting_evidence_ids]
    findings = _active_only([f for f in findings if f is not None])
    if not findings:
        return "—"
    if attr_is_list:
        return _render_list_cell(findings, url_map)
    return _render_scalar_cell(findings, url_map)


def _schema_table_id(cmap: Any, schema: Any) -> str:
    return getattr(schema, "table_id", "") or "_default"


def _is_list_attr(schema: Any, attr: str) -> bool:
    cd = (getattr(schema, "column_desc", None) or {}).get(attr)
    if cd is None:
        return False
    col_type = getattr(cd, "type", "") or ""
    return "list" in col_type.lower()


def _entity_pk_values(schema: Any, entity: str) -> dict[str, str]:
    pk = list(getattr(schema, "primary_key", []) or [])
    if not pk:
        return {}
    vals = entity.split("|") if "|" in entity else [entity]
    vals = vals + [""] * (len(pk) - len(vals))
    return {attr: vals[i] for i, attr in enumerate(pk)}


def _cell_findings(cell: Any, evidence_by_id: dict) -> list[Any]:
    if cell is None or not getattr(cell, "supporting_evidence_ids", None):
        return []
    return _active_only([
        f for f in (evidence_by_id.get(fid) for fid in cell.supporting_evidence_ids)
        if f is not None
    ])


def _raw_cell_value(cell: Any, evidence_by_id: dict) -> str:
    findings = _cell_findings(cell, evidence_by_id)
    if findings:
        best = max(findings, key=_rank_f)
        raw = ((getattr(best, "value", "") or "").strip()
               or (getattr(best, "finding", "") or ""))
        if raw:
            return raw.replace("\n", " ").strip()
    return (getattr(cell, "display_hint", "") or "").replace("\n", " ").strip()


def _row_raw_value(
    cmap: Any,
    schema: Any,
    entity: str,
    attr: str,
    evidence_by_id: dict,
) -> str:
    pk_vals = _entity_pk_values(schema, entity)
    if attr in pk_vals and pk_vals[attr]:
        return pk_vals[attr]
    tid = _schema_table_id(cmap, schema)
    cell = cmap.cells.get(cmap.cell_key(tid, entity, attr))
    return _raw_cell_value(cell, evidence_by_id) if cell is not None else ""


def _render_row_attr(
    cmap: Any,
    schema: Any,
    entity: str,
    attr: str,
    evidence_by_id: dict,
    url_map: dict[str, int],
) -> str:
    pk_vals = _entity_pk_values(schema, entity)
    if attr in pk_vals and pk_vals[attr]:
        return pk_vals[attr]
    tid = _schema_table_id(cmap, schema)
    cell = cmap.cells.get(cmap.cell_key(tid, entity, attr))
    return _render_cell_with_citation(
        cell, evidence_by_id, url_map, attr_is_list=_is_list_attr(schema, attr),
    )


def _render_single_coverage_table_with_citations(
    cmap: Any,
    schema: Any,
    evidence_by_id: dict,
    url_map: dict[str, int],
) -> str:
    """Markdown coverage table — deterministic render. The LLM never
    gets to rewrite this; it's inserted verbatim into the final report.
    Per-attribute shape (scalar vs list) drives cell rendering.
    """
    if not schema.entities or not schema.attributes:
        return ""

    # Build header: each primary-key attribute becomes its own column so
    # composite keys like "国家|年份" render as two columns instead of one
    # merged "国家 / 年份" column (which downstream reformat would preserve
    # as a single column and miss the gold schema).
    pk = list(schema.primary_key or [])
    if pk:
        data_cols = schema.data_columns
        header_cols = list(pk) + list(data_cols)
    else:
        data_cols = list(schema.attributes)
        header_cols = [schema.row_label or "Entity"] + list(data_cols)

    header = "| " + " | ".join(header_cols) + " |"
    sep = "|" + "|".join(["---"] * len(header_cols)) + "|"
    rows = [header, sep]
    # Render rows in deterministic order. ``schema.entities`` is the
    # discovery / dispatch order which is meaningful only at the
    # protocol layer; for a table where readers expect chronological /
    # alphabetical grouping (e.g. Year|Winner composite keys), insertion
    # order produces "2019, 2023, 2022, 2021, 2020" which reads as
    # noise. Lexicographic sort lines up zero-padded numeric prefixes
    # (years, ranks) AND alphabetic names; for non-prefix schemas it
    # at least guarantees the same query renders identically run-to-run.
    filled = 0
    total = 0
    for entity in sorted(schema.entities):
        cells = []
        for attr in data_cols:
            rendered = _render_row_attr(
                cmap, schema, entity, attr, evidence_by_id, url_map,
            )
            cells.append(rendered)
            total += 1
            if rendered != "—":
                filled += 1
        if pk:
            pk_vals = entity.split("|") if "|" in entity else [entity]
            pk_vals = pk_vals + [""] * (len(pk) - len(pk_vals))
            key_cells = pk_vals[:len(pk)]
        else:
            key_cells = [entity]
        rows.append("| " + " | ".join(key_cells + cells) + " |")
    table_md = "\n".join(rows)
    # Anti-hallucination footer: when most cells are placeholders, downstream
    # LLM reformat tends to fabricate plausible values. Surface the gap so
    # the reformat prompt's hard rule has something concrete to point at.
    if total > 0 and filled / total < 0.3:
        ratio = filled / total
        table_md += (
            f"\n\n> **WARNING**: only {filled}/{total} data cells filled "
            f"({ratio*100:.0f}%). Cells shown as `—` have no supporting "
            f"evidence. **Do NOT fabricate values for `—` cells in any "
            f"downstream rendering.**"
        )
    removed = getattr(schema, "removed_entities", None) or {}
    if removed:
        lines = [f"\n\n> Excluded rows (removed by orchestrator — not part of the answer):"]
        for ent, why in sorted(removed.items()):
            lines.append(f"> - {ent}: {why}")
        table_md += "\n".join(lines)
    return table_md


def _norm_join_value(text: str) -> str:
    return " ".join((text or "").strip().lower().split())


def _relation_matches(
    cmap: Any,
    rel: Any,
    parent_schema: Any,
    parent_entity: str,
    child_schema: Any,
    child_entity: str,
    evidence_by_id: dict,
) -> bool:
    child_cols = list(getattr(rel.foreign_key, "columns", []) or [])
    target_cols = list(getattr(rel.foreign_key, "target_columns", []) or [])
    if not target_cols:
        target_cols = list(getattr(parent_schema, "primary_key", []) or [])
    if not child_cols or len(child_cols) != len(target_cols):
        return False
    for child_col, target_col in zip(child_cols, target_cols):
        child_val = _norm_join_value(
            _row_raw_value(cmap, child_schema, child_entity, child_col, evidence_by_id)
        )
        parent_val = _norm_join_value(
            _row_raw_value(cmap, parent_schema, parent_entity, target_col, evidence_by_id)
        )
        if not child_val or not parent_val or child_val != parent_val:
            return False
    return True


def _render_joined_coverage_table_with_citations(
    cmap: Any,
    tables: dict,
    relations: list,
    evidence_by_id: dict,
    url_map: dict[str, int],
) -> str:
    if len(tables) <= 1 or not relations:
        return ""

    child_tids = {rel.from_table for rel in relations}
    roots = [tid for tid in tables if tid not in child_tids]
    root_tid = roots[0] if roots else next(iter(tables))

    children_by_parent: dict[str, list[Any]] = {}
    parent_by_child: dict[str, Any] = {}
    for rel in relations:
        parent_tid = rel.foreign_key.target_table
        if rel.from_table in tables and parent_tid in tables:
            children_by_parent.setdefault(parent_tid, []).append(rel)
            parent_by_child[rel.from_table] = rel

    join_order: list[str] = []

    def _visit(tid: str) -> None:
        if tid in join_order:
            return
        join_order.append(tid)
        for rel in children_by_parent.get(tid, []):
            _visit(rel.from_table)

    _visit(root_tid)
    if len(join_order) != len(tables):
        return ""

    def _expand_contexts(contexts: list[dict[str, str]], parent_tid: str) -> list[dict[str, str]]:
        result = contexts
        for rel in children_by_parent.get(parent_tid, []):
            child_tid = rel.from_table
            parent_schema = tables[parent_tid]
            child_schema = tables[child_tid]
            expanded: list[dict[str, str]] = []
            for ctx in result:
                parent_entity = ctx.get(parent_tid)
                if not parent_entity:
                    expanded.append(ctx)
                    continue
                matches = [
                    child_entity for child_entity in sorted(child_schema.entities)
                    if _relation_matches(
                        cmap, rel, parent_schema, parent_entity,
                        child_schema, child_entity, evidence_by_id,
                    )
                ]
                if not matches:
                    expanded.append(dict(ctx))
                    continue
                for child_entity in matches:
                    child_ctx = dict(ctx)
                    child_ctx[child_tid] = child_entity
                    expanded.extend(_expand_contexts([child_ctx], child_tid))
            result = expanded
        return result

    root_schema = tables[root_tid]
    contexts = _expand_contexts(
        [{root_tid: entity} for entity in sorted(root_schema.entities)],
        root_tid,
    )

    skip_attrs: dict[str, set[str]] = {}
    for tid, rel in parent_by_child.items():
        skip_attrs.setdefault(tid, set()).update(rel.foreign_key.columns)

    col_specs: list[tuple[str, str]] = []
    for tid in join_order:
        schema = tables[tid]
        for attr in schema.attributes:
            if attr in skip_attrs.get(tid, set()):
                continue
            col_specs.append((tid, attr))
    if not col_specs:
        return ""

    attr_counts: dict[str, int] = {}
    for _, attr in col_specs:
        attr_counts[attr] = attr_counts.get(attr, 0) + 1

    header_cols = []
    for tid, attr in col_specs:
        if attr_counts[attr] > 1:
            label = getattr(tables[tid], "table_label", "") or tid
            header_cols.append(f"{label}.{attr}")
        else:
            header_cols.append(attr)

    rows = [
        "| " + " | ".join(header_cols) + " |",
        "|" + "|".join(["---"] * len(header_cols)) + "|",
    ]
    total = 0
    filled = 0
    for ctx in contexts:
        rendered_cells: list[str] = []
        for tid, attr in col_specs:
            schema = tables[tid]
            entity = ctx.get(tid, "")
            if not entity:
                rendered = "—"
            else:
                rendered = _render_row_attr(
                    cmap, schema, entity, attr, evidence_by_id, url_map,
                )
            rendered_cells.append(rendered)
            if attr not in set(getattr(schema, "primary_key", []) or []):
                total += 1
                if rendered != "—":
                    filled += 1
        rows.append("| " + " | ".join(rendered_cells) + " |")

    table_md = "\n".join(rows)
    if total > 0 and filled / total < 0.3:
        ratio = filled / total
        table_md += (
            f"\n\n> **WARNING**: only {filled}/{total} joined data cells filled "
            f"({ratio*100:.0f}%). Cells shown as `—` have no supporting "
            f"evidence. **Do NOT fabricate values for `—` cells in any "
            f"downstream rendering.**"
        )
    return table_md


def _connected_components(tables: dict, relations: list) -> list[list[str]]:
    """Group table ids into relation-connected components, preserving the
    declared table order both within and across components."""
    parent = {tid: tid for tid in tables}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for rel in relations:
        a, b = rel.from_table, rel.foreign_key.target_table
        if a in parent and b in parent:
            parent[find(a)] = find(b)

    groups: dict[str, list[str]] = {}
    for tid in tables:
        groups.setdefault(find(tid), []).append(tid)
    return [grp for grp in groups.values()]


def build_coverage_table_with_citations(
    state: Any,
    evidence_by_id: dict,
    url_map: dict[str, int],
) -> str:
    """Markdown coverage table — deterministic render. The LLM never
    gets to rewrite this; it's inserted verbatim into the final report.

    All tables are rendered: related tables join into one table; unrelated
    ones become separate ``#### label`` sections (a header is added only when
    more than one component exists).
    """
    if state is None:
        return ""
    cmap = state.coverage_map
    if not cmap.cells:
        return ""
    tables = getattr(cmap, "tables", {}) or {}
    if not tables:
        return ""
    relations = list(getattr(cmap, "relations", []) or [])

    components = _connected_components(tables, relations)
    multi = len(components) > 1
    parts: list[str] = []
    for comp_tids in components:
        comp = {tid: tables[tid] for tid in comp_tids}
        comp_rels = [
            r for r in relations
            if r.from_table in comp and r.foreign_key.target_table in comp
        ]
        if len(comp) > 1:
            md = _render_joined_coverage_table_with_citations(
                cmap, comp, comp_rels, evidence_by_id, url_map,
            )
            if not md:
                md = "\n\n".join(
                    f"#### {getattr(sch, 'table_label', '') or tid}\n\n{tbl}"
                    for tid, sch in comp.items()
                    if (tbl := _render_single_coverage_table_with_citations(
                        cmap, sch, evidence_by_id, url_map))
                )
        else:
            md = _render_single_coverage_table_with_citations(
                cmap, next(iter(comp.values())), evidence_by_id, url_map,
            )
        if not md:
            continue
        if multi:
            label = (getattr(comp[comp_tids[0]], "table_label", "")
                     or comp_tids[0])
            md = f"#### {label}\n\n{md}"
        parts.append(md)
    return "\n\n".join(parts)


def build_sources_list(url_map: dict[str, int]) -> str:
    """Markdown ``[N] URL`` list for the final "信息来源" section.
    Deterministic — always matches whatever citations the prose used,
    because both come from the same ``url_map``.
    """
    lines = [f"[{n}] {url}" for url, n in sorted(url_map.items(), key=lambda kv: kv[1])]
    return "\n".join(lines)


def build_writer_finalize_message(
    *,
    query: str,
    coverage_table: str,
    sources_list: str,
    language: str,
    coverage_score: float,
    stop_reason: str = "",
) -> str:
    """HumanMessage content for the harness's final '定稿' turn to the
    writer sub-agent. Assumes the writer thread already has the full
    draft + evidence context in its MemorySaver history — this message
    only nudges it to polish and emit the final report body.

    The writer should NOT produce its own sources list: the harness
    appends the deterministic coverage_table + sources_list after its
    body. Citations ``[N]`` must be preserved.
    """
    cov_pct = f"{coverage_score * 100:.0f}%"
    reason_line = (
        f"Stop reason: {stop_reason}.\n" if stop_reason else ""
    )
    if language == "中文":
        return (
            f"搜索阶段已经结束（coverage {cov_pct}）。{reason_line}"
            f"请基于你先前写的 draft 产出**最终定稿** report markdown 正文：\n\n"
            f"- 保留所有 [N] 引用编号。\n"
            f"- 补齐空 section；若证据不足请显式写 \"证据不足\" 并简述缺口。\n"
            f"- 删除冗余和重复段落，统一表述口径。\n"
            f"- 若用户在 query 中明确要求『一张表』/『单个 markdown 表格』等单表输出，而下面的 coverage table 是多张子表，请在正文里**合并成一张表**输出（按用户给定的列名顺序），不要保留多张分表。\n"
            f"- **只输出正文 markdown**：不要加最外层 `# {query}` 大标题，也不要再列 sources / 信息来源（harness 会在末尾统一追加下面这张 coverage table 和 sources list）。\n\n"
            f"harness 将在你输出的正文后追加的块（仅供参考，不要重复输出）：\n\n"
            f"### 数据对比表\n{coverage_table or '_(no structured data)_'}\n\n"
            f"### 信息来源\n{sources_list or '_(no sources)_'}\n\n"
            f"现在请输出定稿正文。"
        )
    return (
        f"The search phase has ended (coverage {cov_pct}). {reason_line}"
        f"Produce the **final report body** in markdown based on your draft:\n\n"
        f"- Preserve all [N] citation markers.\n"
        f"- Fill any empty sections; if evidence is insufficient, say so explicitly.\n"
        f"- Remove redundancy, unify phrasing.\n"
        f"- If the user explicitly asked for a SINGLE markdown table and the coverage table below contains multiple sub-tables, **merge them into one table** in your body (column order following the user's spec); do not keep separate sub-tables.\n"
        f"- **Output only the body markdown**: do NOT add a top-level `# {query}` title, and do NOT emit a sources / references list "
        f"(the harness will append the coverage table and sources below your body).\n\n"
        f"For your reference (do not duplicate) the harness will append:\n\n"
        f"### Coverage Table\n{coverage_table or '_(no structured data)_'}\n\n"
        f"### Sources\n{sources_list or '_(no sources)_'}\n\n"
        f"Now emit the final body."
    )
