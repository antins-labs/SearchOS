"""Constrain explicit table targets while preserving untargeted discovery."""

from __future__ import annotations

from typing import Any

from searchos.socm import TableSchema
from searchos.socm.evidence.missing_values import is_missing_value


def capture_task_targets(state: Any, item: dict) -> dict:
    """Snapshot queued targets and fill missing snapshots before log or source replay."""
    if "task_target_cells" in item:
        return item
    task = next((task for task in state.frontier.questions
                 if task.id == item.get("task_id")), None)
    return {
        **item,
        "task_target_cells": list(task.target_cells) if task else [],
        "task_target_table": task.table_id if task else item.get("target_table", ""),
    }


def _target_keys(state: Any, targets: list[str], table_id: str) -> set[str]:
    cmap = state.coverage_map
    keys = set()
    for raw in targets:
        key = cmap.resolve_cell_reference(raw, table_id=table_id)
        # 有目标但不能解析，表示拒绝写入，不能当作无目标。
        if key is None:
            return set()
        keys.add(key)
    return keys


def task_target_keys(state: Any, items: list[dict]) -> set[str] | None:
    """合并观察快照与当前任务约束；空集合保留拒绝写入语义。"""
    constraints = []
    tasks = {task.id: task for task in state.frontier.questions}
    for raw in items:
        item = capture_task_targets(state, raw)
        if targets := item.get("task_target_cells"):
            constraints.append(_target_keys(state, targets, item.get("task_target_table", "")))
        task = tasks.get(item.get("task_id"))
        if task and task.target_cells:
            constraints.append(_target_keys(state, task.target_cells, task.table_id))
    return set.intersection(*constraints) if constraints else None


def restrict_task_rows(state: Any, items: list[dict], table_id: str, bundles: list[tuple]):
    """Filter rows and columns inside the transaction before row creation and projection."""
    allowed = task_target_keys(state, items)
    if allowed is None:
        return bundles, []
    schema = state.coverage_map.tables.get(table_id)
    if schema is None:
        return [], [{"row": "", "column": "", "reason": "task_target_table_missing"}]
    filtered, rejected = [], []
    for bundle in bundles:
        row = bundle[0]
        key_values = {key: str(row.get(key, "")).strip() for key in schema.primary_key}
        if any(is_missing_value(row.get(key)) for key in schema.primary_key):
            rejected.append({"row": "", "column": "", "reason": "task_target_entity_unresolved"})
            continue
        entity = TableSchema.make_entity_key(key_values, schema.primary_key)
        canonical = state.coverage_map.resolve_entity(entity, table_id=table_id)
        scoped = dict(row)
        keep = False
        for attr in schema.data_columns:
            if is_missing_value(row.get(attr)):
                continue
            key = state.coverage_map.cell_key(table_id, canonical or entity, attr)
            if canonical is not None and key in allowed:
                keep = True
            else:
                scoped.pop(attr, None)
                rejected.append({
                    "row": entity, "column": attr, "reason": "outside_task_target_cells",
                })
        if keep:
            filtered.append((scoped, *bundle[1:]))
    return filtered, rejected


def route_observations(state: Any, items: list[dict]) -> tuple[list[dict], list[tuple[dict, str]]]:
    tables = state.coverage_map.tables
    if not tables:
        return [{**item, "target_table": ""} for item in items], []
    routed, rejected = [], []
    tasks = {task.id: task for task in state.frontier.questions}
    for item in items:
        task = tasks.get(item.get("task_id"))
        target = item.get("target_table") or (task.table_id if task else "")
        if target and target not in tables:
            rejected.append((item, target))
            continue
        for table_id in [target] if target else tables:
            routed.append({
                **item,
                "target_table": table_id,
                "all_schema_targets": not bool(target),
            })
    return routed, rejected
