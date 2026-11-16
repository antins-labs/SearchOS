"""按字段创建实体，通过结构化引用编辑、删除和恢复行。"""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from langchain_core.tools import tool
from pydantic import BaseModel, ConfigDict, Field

from searchos.agents.runtime import _ctx
from searchos.socm.coverage import (
    CellEvidenceBinding,
    bind_cell_evidence,
    clear_cell_evidence,
    refresh_cells,
    validate_row,
)
from searchos.socm.coverage.projection import cell_source_error
from searchos.socm.evidence.missing_values import is_missing_value
from searchos.socm.refs import RowRef, cell_parts, cell_ref, row_key, row_ref, row_values

from .cells import _cell_value, set_inferred_value


def _normalize_add_entity_rows(
    rows: list[dict[str, Any]], *, table_id: str, schema: Any,
    entity_values: dict[str, dict[str, str]],
) -> tuple[list[str], dict[str, dict[str, Any]], str | None]:
    """创建与抽取共用逐字段行对象；完整主键由代码编码。"""
    normalized, asserted = [], {}
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            return [], {}, f"Error: rows[{index}] must be an object containing every primary-key field"
        values = {key: _cell_value(row.get(key)) for key in schema.primary_key}
        if not values or any(not value or value.lower() in {"null", "none", "n/a"} for value in values.values()):
            return [], {}, f"Error: rows[{index}] requires every primary-key field of {table_id}"
        name = schema.make_entity_key(values, schema.primary_key)
        normalized.append(name)
        entity_values[name] = values
        asserted.setdefault(name, {}).update({col: row[col] for col in schema.data_columns if col in row})
    return normalized, asserted, None


@tool(parse_docstring=True)
async def add_entities(rows: list[dict[str, Any]], table_id: str) -> str:
    """Add rows to an existing table or fill inferable fields on known rows. Returns added, skipped
    and rejected row references, an asserted_cells count, and any source_required fields.

    Duplicate keys reuse the existing row. Restore an excluded row with edit_entities and
    restore=true.

    Args:
        rows: Array of row objects with a value for every primary-key field. Supply established non-key values inline for requires_search=false columns. Retrieve source-required values separately. For example, pass {"table_id":"products","rows":[{"Brand":"Acme","Product":"Blue|Label"}]}.
        table_id: ID of the table that owns the rows.
    """
    workspace = _ctx.workspace
    if workspace is None:
        return "Error: workspace not initialized"
    result = {"added": [], "skipped": [], "rejected": [], "asserted_cells": 0}

    def update(state):
        cmap = state.coverage_map
        schema = cmap.tables.get(table_id)
        if schema is None or not rows:
            raise ValueError("An existing table and non-empty rows are required")
        values = {}
        entities, asserted, error = _normalize_add_entity_rows(
            rows, table_id=table_id, schema=schema, entity_values=values,
        )
        if error:
            raise ValueError(error)
        for entity in entities:
            ref = row_ref(table_id, entity)
            violations = validate_row(schema, {**values[entity], **asserted[entity]})
            if violations or cmap.is_removed_entity(entity, table_id=table_id):
                result["rejected"].append({"row": ref, "reason": violations or "Row is excluded; explicitly restore it"})
                continue
            added = cmap.add_entity(entity, table_id=table_id, key_values=values[entity])
            canonical = cmap.resolve_entity(entity, table_id=table_id)
            result["added" if added else "skipped"].append(row_ref(table_id, canonical))
            for col, raw in asserted[entity].items():
                if is_missing_value(raw):
                    continue
                if schema.requires_search(col):
                    result.setdefault("source_required", []).append({**ref, "attribute": col})
                elif not cmap.cells[cmap.cell_key(table_id, canonical, col)].supporting_evidence_ids:
                    set_inferred_value(cmap, table_id, canonical, col, raw)
                    result["asserted_cells"] += 1
        return state

    try:
        workspace.atomic_update_state(update)
    except ValueError as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False)
    return json.dumps(result, ensure_ascii=False)


@tool(parse_docstring=True)
async def remove_entities(rows: list[RowRef], reason: str) -> str:
    """Exclude rows when evidence shows they fall outside the requested scope. Returns removed and
    not_found row references.

    Keep rows with missing attributes in the table. Exclusion preserves evidence for audit. Use
    edit_entities with restore=true to bring a row back.

    Args:
        rows: Row references of the form {"table_id":"products","key":["Acme"]}, with key values in
            primary_key order.
        reason: Short explanation citing the evidence that excludes these rows.
    """
    workspace = _ctx.workspace
    if workspace is None:
        return "Error: workspace not initialized"
    if not rows or not reason.strip():
        return "Error: rows and an exclusion reason are required"
    result = {"removed": [], "not_found": []}

    def update(state):
        for ref in rows:
            ok = state.coverage_map.remove_entity(ref.row_key(), table_id=ref.table_id, reason=reason)
            result["removed" if ok else "not_found"].append(ref.model_dump())
        return state

    workspace.atomic_update_state(update)
    return json.dumps(result, ensure_ascii=False)


class CellEdit(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    value: Any = Field(description="Supported field value; null, empty values and '/' clear the cell.")
    evidence_ids: list[str] = Field(default_factory=list, description="Supporting evidence IDs. May be omitted for requires_search=false fields.")


class RowEdit(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    row: RowRef = Field(description="Reference to the row to edit.")
    rename: list[str] | None = Field(default=None, description="All replacement key values in primary_key order.")
    restore: bool = Field(default=False, description="Restore a previously excluded row before applying edits.")
    set: dict[str, CellEdit | None] = Field(default_factory=dict, description="Cell edits keyed by non-key column name. A null entry clears that cell.")


def _edit_cell(state, table_id: str, entity: str, col: str, change: CellEdit | None) -> bool:
    """写入字段并报告值、状态或证据绑定是否改变。"""
    raw = change.value if change is not None else None
    value = _cell_value(raw)
    if is_missing_value(raw) or is_missing_value(value):
        return clear_cell_evidence(state, table_id=table_id, entity=entity, attribute=col)

    cmap = state.coverage_map
    key = cmap.cell_key(table_id, entity, col)

    def current():
        return cmap.cells[key], cmap.evidence_bindings.get(key, [])

    before = deepcopy(current())
    if change is not None and change.evidence_ids:
        for fid in change.evidence_ids:
            node = state.evidence_graph.get_node(fid)
            if node is None:
                raise ValueError(f"Unknown evidence ID: {fid}")
            if error := cell_source_error(state, node):
                raise ValueError(f"Evidence {fid} {error}")
        bind_cell_evidence(
            state, [(key, CellEvidenceBinding(evidence_id=fid, value=value)) for fid in change.evidence_ids],
            overwrite=True,
            validation_values={(key, fid): raw for fid in change.evidence_ids},
        )
    else:
        set_inferred_value(cmap, table_id, entity, col, raw)
    return current() != before


def _rename_references(state: Any, table_id: str, old: str, new: str) -> None:
    """与 CoverageMap 重命名在同一状态事务中更新依赖引用。"""
    def replace(key):
        tid, entity, attr = cell_parts(key)
        return state.coverage_map.cell_key(tid, new, attr) if tid == table_id and entity == old else key

    for node in state.evidence_graph.nodes:
        if node.entity == old and (node.table_id or state.coverage_map.primary_table_id) == table_id:
            node.entity = new
    state.evidence_graph.invalidate_index()
    from searchos.socm.coverage.conflicts import rekey_comparisons
    for attr in state.coverage_map.tables[table_id].attributes:
        rekey_comparisons(state, state.coverage_map.cell_key(table_id, new, attr),
                          state.coverage_map.cell_key(table_id, old, attr), row_values(old))
    for task in state.frontier.questions:
        task.target_cells = [replace(key) for key in task.target_cells]
    for memory in state.failure_memory.records:
        memory.scope.target_cells = [replace(key) for key in memory.scope.target_cells]
        if memory.scope.table_id == table_id:
            memory.scope.entities = [new if key == old else key for key in memory.scope.entities]


@tool(parse_docstring=True)
async def edit_entities(edits: list[RowEdit]) -> str:
    """Correct row keys, restore excluded rows, or set cell values in existing rows. Returns
    updated rows, unchanged cells with their current status, and per-field errors.

    A rename updates evidence and task references atomically. For sourced values, use read_evidence
    to verify active, in-scope evidence, its original link and excerpt, including any formatting
    change or calculation. Successful edits replace cell bindings and preserve source facts. Failed
    fields keep their previous values.

    To set Size from evidence and clear Aroma in the same row, pass
    {"edits":[{"row":{"table_id":"products","key":["Classic"]},"set":{"Size":{"value":"500ml","evidence_ids":["f_size"]},"Aroma":null}}]}.

    Args:
        edits: Array of row edits. Supply table_id and key in primary_key order for each row.
            rename supplies all replacement key values. restore=true reinstates the row. set maps
            each non-key column to {value,evidence_ids}. For requires_search=false, omit
            evidence_ids to infer a value from established row facts. Keep ambiguous values empty.
            A null entry, null or empty value, or "/" clears a cell.
    """
    workspace = _ctx.workspace
    if workspace is None:
        return "Error: workspace not initialized"
    result = {"updated": [], "unchanged": [], "errors": []}

    def update(state):
        cmap = state.coverage_map
        for item in edits:
            tid, entity = item.row.table_id, item.row.row_key()
            schema = cmap.tables.get(tid)
            if schema is None:
                result["errors"].append({"row": item.row.model_dump(), "reason": "Unknown table"})
                continue
            updated = False
            if item.rename is not None:
                new = row_key(item.rename)
                schema.parse_entity_key(new)
                original, _ = cmap.resolve_row(entity, table_id=tid)
                target, status = cmap.resolve_row(new, table_id=tid)
                if target is not None and (target != original or status == "excluded" and not item.restore):
                    result["errors"].append({"row": item.row.model_dump(), "reason": "Rename target already exists or is excluded"})
                    continue
            if item.restore:
                updated = cmap.restore_entity(entity, table_id=tid)
                canonical = cmap.resolve_entity(entity, table_id=tid)
                if updated and canonical:
                    refresh_cells(state, {cmap.cell_key(tid, canonical, attr) for attr in schema.attributes})
            if item.rename is not None:
                ok, message, old = cmap.edit_entity(entity, new, table_id=tid)
                if not ok:
                    result["errors"].append({"row": item.row.model_dump(), "reason": message})
                    continue
                if old != new:
                    _rename_references(state, tid, old, new)
                    updated = True
                entity = new
            canonical = cmap.resolve_entity(entity, table_id=tid)
            if canonical is None:
                result["errors"].append({"row": item.row.model_dump(), "reason": "Row is missing or excluded"})
                continue
            for col, change in item.set.items():
                if col not in schema.data_columns:
                    result["errors"].append({"row": row_ref(tid, canonical), "attribute": col, "reason": "Unknown data column"})
                    continue
                try:
                    if _edit_cell(state, tid, canonical, col, change):
                        updated = True
                    else:
                        key = cmap.cell_key(tid, canonical, col)
                        result["unchanged"].append({**cell_ref(key), "status": cmap.cells[key].status})
                except ValueError as exc:
                    result["errors"].append({"row": row_ref(tid, canonical), "attribute": col, "reason": str(exc)})
            if updated:
                result["updated"].append(row_ref(tid, canonical))
        return state

    try:
        workspace.atomic_update_state(update)
    except ValueError as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False)
    return json.dumps(result, ensure_ascii=False)


for _tool in (add_entities, remove_entities, edit_entities):
    _tool.args_schema.model_config["extra"] = "forbid"
    _tool.args_schema.model_rebuild(force=True)
