"""一次性迁移 SOCM 旧引用；完整校验后发布独立工作区副本。"""

from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path
import shutil
import tempfile

from searchos.socm.refs import STATE_FORMAT_VERSION, cell_key, row_key, row_ref, row_values


class ReferenceMigration:
    def __init__(self):
        self.rows: dict[tuple[str, str], str] = {}
        self.cells: dict[str, str] = {}
        self.schemas: dict[str, dict] = {}

    def collect(self, state: dict) -> None:
        cmap = state.get("coverage_map", {})
        for tid, schema in cmap.get("tables", {}).items():
            pk = schema.get("primary_key", [])
            previous = self.schemas.get(tid)
            if previous is not None and previous["primary_key"] != pk:
                raise ValueError(f"Primary-key schema changed across snapshots: {tid}")
            self.schemas[tid] = {"primary_key": pk, "attributes": set(schema.get("attributes", []))
                                 | (previous["attributes"] if previous else set())}
            for old in [*schema.get("entities", []), *schema.get("removed_entities", {})]:
                values = []
                for attr in pk:
                    key = f"{tid}/{old}.{attr}"
                    cell = cmap.get("cells", {}).get(key) or cmap.get("removed_cells", {}).get(key, {})
                    value = cell.get("full_value")
                    if value is None:
                        value = cell.get("value") or cell.get("display_hint")
                    values.append(str(value) if value is not None else "")
                if not pk:
                    values = [old]
                elif not all(values):
                    parts = [old] if len(pk) == 1 else old.split("|")
                    if len(parts) != len(pk) or not all(parts):
                        raise ValueError(f"Cannot recover primary-key fields: {tid}/{old}")
                    values = [value or parts[i] for i, value in enumerate(values)]
                if pk and "|".join(values) != old:
                    raise ValueError(f"Stored primary-key fields disagree with legacy identity: {tid}/{old}")
                new = row_key(values)
                self._put(self.rows, (tid, old), new)
                for attr in schema.get("attributes", []):
                    self._put(self.cells, f"{tid}/{old}.{attr}", cell_key(tid, new, attr))
            for alias, target in schema.get("entity_aliases", {}).items():
                parts = [alias] if len(pk) <= 1 else alias.split("|")
                if len(parts) != (len(pk) or 1) or not all(parts):
                    raise ValueError(f"Ambiguous alias requires repair: {tid}/{alias}")
                self._put(self.rows, (tid, alias), row_key(parts))
                for attr in schema.get("attributes", []):
                    self._put(self.cells, f"{tid}/{alias}.{attr}", cell_key(tid, row_key(parts), attr))

    @staticmethod
    def _put(mapping, key, value):
        if key in mapping and mapping[key] != value:
            raise ValueError(f"Ambiguous legacy reference: {key}")
        mapping[key] = value

    def row(self, old: str, table_id: str) -> str:
        if not old:
            return old
        if table_id:
            result = self.rows.get((table_id, old))
            if result:
                return result
        else:
            matches = {value for (tid, name), value in self.rows.items() if name == old}
            if len(matches) == 1:
                return matches.pop()
        raise ValueError(f"Unresolved row reference: {table_id}/{old}")

    def cell(self, old: str, table_id: str = "") -> str:
        candidates = {self.cells[key] for key in (old, f"{table_id}/{old}") if key in self.cells}
        if not table_id and not candidates:
            candidates = {new for key, new in self.cells.items() if key.partition("/")[2] == old}
        if not candidates:
            for tid, schema in self.schemas.items():
                if table_id and tid != table_id:
                    continue
                short = old.removeprefix(f"{tid}/")
                for attr in schema["attributes"]:
                    if not short.endswith(f".{attr}"):
                        continue
                    entity = short[:-(len(attr) + 1)]
                    # 旧工具曾接收逗号写法；仅用已恢复字段进行精确映射。
                    matches = {new for (table, _), new in self.rows.items()
                               if table == tid and ",".join(row_values(new)) == entity}
                    candidates.update(cell_key(tid, new, attr) for new in matches)
                    # 单字段旧目标即使没有落表，仍可保留为未匹配目标。
                    if not matches and entity and len(schema["primary_key"]) <= 1:
                        candidates.add(cell_key(tid, row_key([entity]), attr))
        if len(candidates) != 1:
            raise ValueError(f"Unresolved or ambiguous cell reference: {old}")
        return candidates.pop()

    def state(self, original: dict) -> dict:
        if original.get("format_version") == STATE_FORMAT_VERSION:
            return copy.deepcopy(original)
        data = copy.deepcopy(original)
        cmap = data.get("coverage_map", {})
        tables = cmap.get("tables", {})
        primary = next(iter(tables), "")
        for tid, schema in tables.items():
            schema["entities"] = [self.row(old, tid) for old in schema.get("entities", [])]
            schema["removed_entities"] = {self.row(old, tid): reason for old, reason in schema.get("removed_entities", {}).items()}
            schema["entity_aliases"] = {self.row(old, tid): self.row(target, tid) for old, target in schema.get("entity_aliases", {}).items()}
        for name in ("cells", "removed_cells", "evidence_bindings", "evidence_comparisons"):
            cmap[name] = {self.cell(old): value for old, value in cmap.get(name, {}).items()}
            if name in {"cells", "removed_cells"}:
                for cell in cmap[name].values():
                    if cell.get("full_value") is None and "value" in cell:
                        if not isinstance(cell["value"], str):
                            raise ValueError("Legacy cell value requires an explicit text conversion")
                        cell["full_value"] = cell["value"]
        for node in data.get("evidence_graph", {}).get("nodes", []):
            if node.get("entity"):
                node["entity"] = self.row(node["entity"], node.get("table_id") or primary)
        for task in data.get("frontier", {}).get("questions", []):
            task["target_cells"] = [self.cell(old, task.get("table_id") or primary) for old in task.get("target_cells", [])]
        for memory in data.get("failure_memory", {}).get("records", []):
            scope = memory.get("scope", {})
            tid = scope.get("table_id", "")
            scope["target_cells"] = [self.cell(old, tid) for old in scope.get("target_cells", [])]
            scope["entities"] = [self.row(old, tid) for old in scope.get("entities", [])]
        for scope in (data.get("research_plan") or {}).get("set_scope", []):
            tid = scope.get("table_id") or primary
            members = []
            for old in scope.get("expected_members", []):
                known = self.rows.get((tid, old))
                if known is None:
                    pk = self.schemas.get(tid, {}).get("primary_key", [])
                    parts = [old] if len(pk) == 1 else old.split("|")
                    if not pk or len(parts) != len(pk):
                        raise ValueError(f"Cannot recover expected member: {tid}/{old}")
                    known = row_key(parts)
                members.append(row_ref(tid, known))
            scope["expected_members"] = members
        self._reports(data)
        data["format_version"] = STATE_FORMAT_VERSION
        from searchos.socm.state import SearchState
        validated = SearchState.model_validate(data)
        for old, new in self.cells.items():
            if new in validated.coverage_map.evidence_comparisons:
                from searchos.socm.coverage.conflicts import rekey_comparisons
                binding = validated.coverage_map.cell_binding(new)
                if binding is None:
                    continue
                tid, _, attr = binding
                old_entity = next((name for (table, name), encoded in self.rows.items()
                                   if table == tid and old == f"{tid}/{name}.{attr}"), None)
                if old_entity is not None:
                    rekey_comparisons(validated, new, old, old_entity)
        return validated.model_dump()

    def _reports(self, obj):
        if isinstance(obj, list):
            for value in obj:
                self._reports(value)
        elif isinstance(obj, dict):
            for name, value in obj.items():
                if name in {"cells_filled", "task_target_cells", "cell_keys"} and isinstance(value, list):
                    obj[name] = [self.cell(old, obj.get("task_target_table", "")) for old in value]
                elif name == "discovered_entities" and isinstance(value, list):
                    obj[name] = [self.row(old, "") for old in value]
                elif name not in {"coverage_map", "evidence_graph", "frontier", "failure_memory"}:
                    self._reports(value)


def migrate_workspace(source: Path, destination: Path) -> dict:
    """先预检全部结构化状态，再原子发布新目录；原工作区保持可回溯。"""
    source, destination = source.resolve(), destination.resolve()
    if destination.exists() or destination.is_relative_to(source):
        raise ValueError("Destination must be a new directory outside the original workspace")
    files = [source / "search_state.json", *sorted((source / "turn_snapshots").glob("*.json"))]
    documents = {path: json.loads(path.read_text()) for path in files}
    migration = ReferenceMigration()
    for document in documents.values():
        state = document.get("search_state", document)
        if state.get("format_version") != STATE_FORMAT_VERSION:
            migration.collect(state)
    converted = {}
    for path, document in documents.items():
        if "search_state" in document:
            converted[path] = {**document, "search_state": migration.state(document["search_state"])}
        else:
            converted[path] = migration.state(document)
    for path in (source / "extraction_pending").glob("*/*.json"):
        record = json.loads(path.read_text())
        migration._reports(record)
        converted[path] = record
    coverage = source / "coverage_map.json"
    if coverage.exists():
        converted[coverage] = converted[source / "search_state.json"]["coverage_map"]
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".socm-v2-", dir=destination.parent))
    try:
        shutil.copytree(source, staging, dirs_exist_ok=True, symlinks=True)
        for path, document in converted.items():
            (staging / path.relative_to(source)).write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
        os.replace(staging, destination)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return {"workspace": str(destination), "format_version": STATE_FORMAT_VERSION,
            "rows": len(migration.rows), "cells": len(migration.cells), "files": len(converted)}


def replace_workspace(source: Path, backup: Path) -> dict:
    """离线替换：完整构造新目录，再备份旧目录并安装；失败恢复旧目录。"""
    source, backup = source.resolve(), backup.resolve()
    if backup.exists() or backup.is_relative_to(source):
        raise ValueError("Backup must be a new directory outside the workspace")
    staging = Path(tempfile.mkdtemp(prefix=".socm-install-", dir=source.parent))
    migrated = staging / source.name
    try:
        report = migrate_workspace(source, migrated)
        backup.parent.mkdir(parents=True, exist_ok=True)
        os.rename(source, backup)
        try:
            os.rename(migrated, source)
        except BaseException:
            os.rename(backup, source)
            raise
        return {**report, "workspace": str(source), "backup": str(backup)}
    finally:
        shutil.rmtree(staging)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--replace", action="store_true", help="Backend must be stopped; destination becomes the original workspace backup")
    args = parser.parse_args()
    try:
        report = (replace_workspace if args.replace else migrate_workspace)(args.source, args.destination)
    except (ValueError, OSError) as exc:
        args.report.write_text(json.dumps({"error": str(exc), "migrated": False}, ensure_ascii=False))
        raise SystemExit(str(exc)) from exc
    args.report.write_text(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
