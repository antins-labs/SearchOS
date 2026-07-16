"""Deterministic eval-table export from CoverageMap + EvidenceGraph.

Renders a clean markdown pipe-table with no hedge markers, no citations,
and no prose — suitable as direct input to the eval reformat LLM.
"""

from __future__ import annotations

import logging
from typing import Any

from searchos.socm import SearchState


logger = logging.getLogger(__name__)


_ALIGN_RANK = {"full": 3, "partial": 2, "loose": 1, "": 0}
_AUTH_RANK = {"official": 5, "aggregator": 4, "industry_pr": 3,
              "news": 2, "blog": 1, "unclear": 0, "": 0}


def _rank_f(f: Any) -> tuple:
    return (
        _ALIGN_RANK.get(getattr(f, "alignment", "") or "", 0),
        _AUTH_RANK.get(getattr(f, "source_authority", "") or "", 0),
        float(getattr(f, "confidence", 0.0) or 0.0),
    )


def _active_only(findings: list) -> list:
    return [f for f in findings if getattr(f, "status", "active") == "active"]


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


def _schema_table_id(cmap: Any, schema: Any) -> str:
    return getattr(schema, "table_id", "") or "_default"


def _cell_findings(cell: Any, evidence_by_id: dict) -> list[Any]:
    if cell is None or not getattr(cell, "supporting_evidence_ids", None):
        return []
    return _active_only([
        f for f in (evidence_by_id.get(fid) for fid in cell.supporting_evidence_ids)
        if f is not None
    ])


def _raw_scalar_value(findings: list[Any]) -> str:
    """Best-ranked finding value, no hedge, no citation."""
    best = max(findings, key=_rank_f)
    raw = (getattr(best, "value", "") or "").strip() or (getattr(best, "finding", "") or "")
    return raw.replace("\n", " ").strip()


def _raw_list_value(findings: list[Any]) -> str:
    """Semicolon-joined distinct values for list-typed cells."""
    non_loose = [
        f for f in findings
        if (getattr(f, "alignment", "") or "") in ("full", "partial")
    ]
    pool = non_loose if non_loose else findings
    ordered = sorted(pool, key=_rank_f, reverse=True)
    seen: set[str] = set()
    items: list[str] = []
    for f in ordered:
        raw = (getattr(f, "value", "") or "").strip() or (getattr(f, "finding", "") or "")
        snip = raw.replace("\n", " ").strip()
        if not snip:
            continue
        key = snip.lower()
        if key in seen:
            continue
        seen.add(key)
        items.append(snip)
    return "; ".join(items)


def _render_cell_raw(
    cell: Any, evidence_by_id: dict, is_list: bool,
) -> str:
    """Render a single cell as plain text (no hedge, no citation)."""
    findings = _cell_findings(cell, evidence_by_id)
    if not findings:
        return ""
    if is_list:
        return _raw_list_value(findings)
    return _raw_scalar_value(findings)


def _render_row(
    cmap: Any, schema: Any, entity: str, evidence_by_id: dict, data_cols: list[str],
) -> list[str]:
    """Render all data columns for one entity row."""
    tid = _schema_table_id(cmap, schema)
    pk_vals = _entity_pk_values(schema, entity)
    cells: list[str] = []
    for attr in data_cols:
        if attr in pk_vals and pk_vals[attr]:
            cells.append(pk_vals[attr])
            continue
        cell = cmap.cells.get(cmap.cell_key(tid, entity, attr))
        cells.append(_render_cell_raw(cell, evidence_by_id, _is_list_attr(schema, attr)))
    return cells


def _build_single_table(
    cmap: Any, schema: Any, evidence_by_id: dict,
) -> str:
    """Render one TableSchema as a markdown pipe-table."""
    if not schema.entities or not schema.attributes:
        return ""

    pk = list(schema.primary_key or [])
    if pk:
        data_cols = schema.data_columns
        header_cols = list(pk) + list(data_cols)
    else:
        data_cols = list(schema.attributes)
        header_cols = [schema.row_label or "Entity"] + list(data_cols)

    rows = [
        "| " + " | ".join(header_cols) + " |",
        "|" + "|".join(["---"] * len(header_cols)) + "|",
    ]

    for entity in sorted(schema.entities):
        data_cells = _render_row(cmap, schema, entity, evidence_by_id, list(data_cols))
        if pk:
            pk_parts = entity.split("|") if "|" in entity else [entity]
            pk_parts = pk_parts + [""] * (len(pk) - len(pk_parts))
            key_cells = pk_parts[:len(pk)]
        else:
            key_cells = [entity]
        rows.append("| " + " | ".join(key_cells + data_cells) + " |")

    return "\n".join(rows)


def _build_joined_table(
    cmap: Any, tables: dict, relations: list, evidence_by_id: dict,
) -> str:
    """Render multi-table join as a flat markdown pipe-table (same join logic as synthesis)."""
    child_tids = {rel.from_table for rel in relations}
    roots = [tid for tid in tables if tid not in child_tids]
    root_tid = roots[0] if roots else next(iter(tables))

    children_by_parent: dict[str, list[Any]] = {}
    for rel in relations:
        parent_tid = rel.foreign_key.target_table
        if rel.from_table in tables and parent_tid in tables:
            children_by_parent.setdefault(parent_tid, []).append(rel)

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

    def _norm(text: str) -> str:
        return " ".join((text or "").strip().lower().split())

    def _relation_matches(rel: Any, parent_schema: Any, parent_entity: str,
                          child_schema: Any, child_entity: str) -> bool:
        child_cols = list(getattr(rel.foreign_key, "columns", []) or [])
        target_cols = list(getattr(rel.foreign_key, "target_columns", []) or [])
        if not target_cols:
            target_cols = list(parent_schema.primary_key or [])
        for c_col, p_col in zip(child_cols, target_cols):
            p_val = _row_raw_val(cmap, parent_schema, parent_entity, p_col, evidence_by_id)
            c_val = _row_raw_val(cmap, child_schema, child_entity, c_col, evidence_by_id)
            if _norm(p_val) != _norm(c_val):
                return False
        return True

    def _row_raw_val(cm: Any, sch: Any, ent: str, attr: str, evi: dict) -> str:
        pk_vals = _entity_pk_values(sch, ent)
        if attr in pk_vals and pk_vals[attr]:
            return pk_vals[attr]
        tid = _schema_table_id(cm, sch)
        cell = cm.cells.get(cm.cell_key(tid, ent, attr))
        if cell is None:
            return ""
        findings = _cell_findings(cell, evi)
        if not findings:
            return ""
        best = max(findings, key=_rank_f)
        raw = (getattr(best, "value", "") or "").strip() or (getattr(best, "finding", "") or "")
        return raw.replace("\n", " ").strip()

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
                    ce for ce in sorted(child_schema.entities)
                    if _relation_matches(rel, parent_schema, parent_entity, child_schema, ce)
                ]
                if not matches:
                    expanded.append(dict(ctx))
                    continue
                for ce in matches:
                    child_ctx = dict(ctx)
                    child_ctx[child_tid] = ce
                    expanded.extend(_expand_contexts([child_ctx], child_tid))
            result = expanded
        return result

    root_schema = tables[root_tid]
    contexts = _expand_contexts(
        [{root_tid: entity} for entity in sorted(root_schema.entities)],
        root_tid,
    )

    # 关系导出不能让已有数据的子表行消失。过去外键零匹配或部分匹配时，
    # 这里会返回看似合理的父表空行，并对下游隐藏 Evidence Graph 中的事实。
    for tid, schema in tables.items():
        represented = {ctx.get(tid) for ctx in contexts if ctx.get(tid)}
        missing = [entity for entity in schema.entities if entity not in represented]
        if missing:
            logger.warning(
                "eval_table join would drop %d row(s) from table %s; "
                "falling back to lossless per-table export",
                len(missing), tid,
            )
            return ""

    skip_attrs: dict[str, set[str]] = {}
    for rel in relations:
        child_tid = rel.from_table
        skip_attrs.setdefault(child_tid, set()).update(
            getattr(rel.foreign_key, "columns", []) or []
        )

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

    for ctx in contexts:
        rendered_cells: list[str] = []
        for tid, attr in col_specs:
            schema = tables[tid]
            entity = ctx.get(tid, "")
            if not entity:
                rendered_cells.append("")
            else:
                pk_vals = _entity_pk_values(schema, entity)
                if attr in pk_vals and pk_vals[attr]:
                    rendered_cells.append(pk_vals[attr])
                else:
                    cell = cmap.cells.get(cmap.cell_key(tid, entity, attr))
                    rendered_cells.append(
                        _render_cell_raw(cell, evidence_by_id, _is_list_attr(schema, attr))
                    )
        rows.append("| " + " | ".join(rendered_cells) + " |")

    return "\n".join(rows)


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


def _render_component(
    cmap: Any, comp: dict, relations: list, evidence_by_id: dict,
) -> str:
    """Join a component's tables when related; render the lone table otherwise."""
    if len(comp) == 1:
        return _build_single_table(cmap, next(iter(comp.values())), evidence_by_id)

    # 若双表组件的父表只含主键，它不提供额外答案数据；同一值已作为外键存在
    # 于子表。直接渲染答案粒度的子表，既不损失关系信息，也避免 "46" 与
    # "第46届" 这类表面形式差异导致全部子表行被吞掉。
    if len(comp) == 2 and len(relations) == 1:
        rel = relations[0]
        parent = comp.get(rel.foreign_key.target_table)
        child = comp.get(rel.from_table)
        target_columns = list(rel.foreign_key.target_columns or parent.primary_key) \
            if parent is not None else []
        if (
            parent is not None
            and child is not None
            and child.entities
            and not parent.data_columns
            and rel.foreign_key.columns
            and len(rel.foreign_key.columns) == len(target_columns)
            and set(target_columns) == set(parent.attributes)
        ):
            return _build_single_table(cmap, child, evidence_by_id)

    joined = _build_joined_table(cmap, comp, relations, evidence_by_id)
    if joined:
        return joined
    # Cyclic / unjoinable component: fall back to per-table sections.
    return "\n\n".join(
        md for md in (
            _build_single_table(cmap, sch, evidence_by_id) for sch in comp.values()
        ) if md
    )


def build_eval_table(state: SearchState) -> str:
    """Build a clean markdown table from CoverageMap for evaluation.

    All tables are exported: related tables are joined, unrelated ones are
    emitted as separate sections. Returns "" if no structured data.
    """
    cmap = state.coverage_map
    if not cmap.cells:
        return ""

    evidence_by_id = {n.id: n for n in state.evidence_graph.nodes}
    tables = getattr(cmap, "tables", {}) or {}
    if not tables:
        return ""
    relations = list(getattr(cmap, "relations", []) or [])

    parts: list[str] = []
    for comp_tids in _connected_components(tables, relations):
        comp = {tid: tables[tid] for tid in comp_tids}
        comp_rels = [
            r for r in relations
            if r.from_table in comp and r.foreign_key.target_table in comp
        ]
        md = _render_component(cmap, comp, comp_rels, evidence_by_id)
        if md:
            parts.append(md)
    return "\n\n".join(parts)
