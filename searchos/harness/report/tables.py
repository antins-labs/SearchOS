"""报告与评测共用的表结构、单元格证据与关系分组。"""

from __future__ import annotations

from typing import Any

from searchos.socm.coverage import project_cell_evidence


def is_list_attr(schema: Any, attr: str) -> bool:
    cd = (getattr(schema, "column_desc", None) or {}).get(attr)
    if cd is None:
        return False
    col_type = getattr(cd, "type", "") or ""
    return "list" in col_type.lower()


def entity_pk_values(schema: Any, entity: str) -> dict[str, str]:
    pk = list(getattr(schema, "primary_key", []) or [])
    if not pk:
        return {}
    vals = entity.split("|") if "|" in entity else [entity]
    vals = vals + [""] * (len(pk) - len(vals))
    return {attr: vals[i] for i, attr in enumerate(pk)}


def schema_table_id(schema: Any) -> str:
    return getattr(schema, "table_id", "") or "_default"


def cell_findings(
    cell: Any,
    evidence_by_id: dict,
    binding: tuple[Any, str, str, str] | None = None,
) -> list[Any]:
    """按目标单元格投影证据，仅返回有效事实。"""
    if cell is None or not getattr(cell, "supporting_evidence_ids", None):
        return []
    nodes = [
        evidence_by_id[fid]
        for fid in cell.supporting_evidence_ids
        if fid in evidence_by_id
    ]
    if binding is not None:
        nodes = [
            view
            for node in nodes
            if (view := project_cell_evidence(binding[0], node, *binding[1:])) is not None
        ]
    return [node for node in nodes if getattr(node, "status", "active") == "active"]


def connected_components(tables: dict, relations: list) -> list[list[str]]:
    """按关系分组，保留组内与组间的声明顺序。"""
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
    return list(groups.values())
