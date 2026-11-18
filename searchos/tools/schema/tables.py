"""创建表结构，维护列定义，并校验列约束、种子行和关系。"""

from __future__ import annotations

import base64
import json
import logging
from collections.abc import Iterable
from typing import Any

from langchain_core.tools import tool

from searchos.agents.runtime import _ctx
from searchos.socm.coverage import commit_evidence
from searchos.socm.refs import STATE_FORMAT_VERSION, RowRef, row_values
from searchos.socm.views.render import render_cell

from .cells import _cell_value, set_inferred_value

logger = logging.getLogger(__name__)


def _select_replay_model(context: Any) -> Any:
    """Explore 回放与在线 Evidence Extraction 使用同一个 extraction profile。"""
    return context.extraction_model or context.judge_model


# ---------------------------------------------------------------------------
# Schema-validation helpers
# ---------------------------------------------------------------------------

# Seed entity names rejected at create_schema time.
_PLACEHOLDERS = {"question", "entity", "unknown", "tbd", "n/a", "answer"}

# parenthetically glosses one magnitude as an unequal one (e.g.
# "亿美元（USD Billion）" — 亿=1e8, billion=1e9) poisons every extracted
# value by the scale ratio: the judge follows the desc over arithmetic.
# Rejected at create_schema; explicit conversion statements
# ("1 billion = 10亿") contain "=" and pass.
_CJK_MAGNITUDES = {
    "千": 1e3, "万": 1e4, "十万": 1e5, "百万": 1e6, "千万": 1e7,
    "亿": 1e8, "十亿": 1e9, "百亿": 1e10, "千亿": 1e11, "万亿": 1e12,
}
_EN_MAGNITUDES = {
    "thousand": 1e3, "million": 1e6, "billion": 1e9, "trillion": 1e12,
    "billions": 1e9, "millions": 1e6,
}


def _unit_gloss_conflict(text: str) -> str | None:
    """First parenthetical magnitude gloss whose scale contradicts the
    magnitude it annotates, or None."""
    import re as _re
    for m in _re.finditer(r"[（(][^（）()]*[)）]", text or ""):
        inner = m.group(0)[1:-1]
        if "=" in inner or "≈" in inner:
            continue
        en = [(w, _EN_MAGNITUDES[w.lower()])
              for w in _re.findall(r"[A-Za-z]+", inner)
              if w.lower() in _EN_MAGNITUDES]
        if not en:
            continue
        before = (text or "")[max(0, m.start() - 8):m.start()]
        cjk = [(u, s) for u, s in _CJK_MAGNITUDES.items() if u in before]
        if not cjk:
            continue
        unit, scale = max(cjk, key=lambda x: len(x[0]))
        word, en_scale = en[0]
        if scale != en_scale:
            return (f"{unit!r} (×{scale:g}) glossed as {word!r} "
                    f"(×{en_scale:g})")
    return None


def _search_policy_error(table_id: str, columns: Iterable[tuple[str, Any]]) -> str | None:
    invalid = [name for name, spec in columns
               if not isinstance(spec, dict) or not isinstance(spec.get("requires_search"), bool)]
    if invalid:
        return (f"table {table_id!r}: set an explicit boolean requires_search for columns {invalid}. "
                "Use false for values reliably inferable from known row facts; "
                "use true for fields that require source evidence. Then retry the call.")
    return None


def _schema_error(message: str, **extra: Any) -> str:
    return json.dumps({"ok": False, "error": message, **extra}, ensure_ascii=False)


def _schema_ok(payload: dict[str, Any]) -> str:
    return json.dumps({"ok": True, **payload}, ensure_ascii=False)


_TABLE_KEYS = {
    "table_id", "attributes", "primary_key", "column_desc", "seed_entities",
    "table_label", "row_label",
}
_RELATION_KEYS = {
    "from_table", "to_table", "foreign_key", "kind", "target_columns", "label",
}


@tool(parse_docstring=True)
async def create_schema(
    tables: list[dict[str, Any]],
    relations: list[dict[str, Any]] | None = None,
) -> str:
    """Create result tables for a new entity type or level of detail. Returns JSON with ok,
    tables, relations, total_cells and any seed or exploration feedback.

    Use a new table_id for each table. Tables may share column names. Use add_columns to revise an
    existing table and add_entities, edit_entities or remove_entities to maintain its rows. Put
    each fact in the table whose primary key determines it and link related tables through foreign
    keys. There is no drop-table or drop-column tool; extend with add_columns instead.

    For schools, set column_desc to
    {"省份":{"type":"str","desc":"学校本部所在省份","requires_search":false},"分数线":{"type":"int","desc":"当年复试总分线","requires_search":true}}.
    For "since 2008" set check to {"min":2008}. For "count >= 2" use {"min":2}. Put semantic
    criteria such as "full paper only" in desc. For a ranked list, seed_entities can start with
    [{"Ranking":1,"Name":"IShowSpeed"}].

    Args:
        tables: Non-empty array of table objects. Each requires table_id, attributes (column names)
            and primary_key (an ordered, non-empty subset of attributes). Optional table_label
            names the table and row_label names one row.
            Set column_desc for every non-key column. Give its type (str, int, float, date,
            list[str], etc.), desc (format, meaning, unit or time basis) and a boolean
            requires_search. When a source gives several score lines, dates or units, specify which
            to extract. A self-explanatory column can have an empty desc.
            Optional check enforces numeric min/max or a closed enum of strings on each value,
            including every list element. Optional seed_entities contains row objects with a value
            for each key field. Include established non-key values inline for requires_search=false
            columns and retrieve evidence for source-required fields.
        relations: Optional array linking tables declared together in this call. Each object names
            from_table, to_table and foreign_key (columns in from_table). target_columns defaults
            to the target primary key.
            Supported kind values are one_to_many and many_to_many. Put the foreign key on the
            referencing table for a many-to-one link. Use label to describe the relationship. Omit
            for one table.
    """
    if _ctx.workspace is None:
        return _schema_error("workspace not initialized")

    if not isinstance(tables, list) or not tables:
        return _schema_error("tables must be a non-empty array")
    relations = relations or []
    if not isinstance(relations, list):
        return _schema_error("relations must be an array (or empty)")

    from searchos.socm import (
        ColumnCheck,
        ColumnDesc,
        ForeignKey,
        Relation,
        RelationKind,
        TableSchema,
    )

    # ---- Validate every table up-front (no partial writes) ----
    seen_ids: set[str] = set()
    source_fields: set[str] = set()
    parsed_tables: list[dict] = []
    for idx, t in enumerate(tables):
        if not isinstance(t, dict):
            return _schema_error(f"tables[{idx}] must be an object")
        unknown = set(t) - _TABLE_KEYS
        if unknown:
            return _schema_error(
                f"tables[{idx}] has unknown keys {sorted(unknown)} "
                f"(allowed: {sorted(_TABLE_KEYS)})"
            )
        tid = str(t.get("table_id") or "").strip()
        if not tid:
            return _schema_error(f"tables[{idx}].table_id is required")
        if tid in seen_ids:
            return _schema_error(f"duplicate table_id {tid!r}")
        seen_ids.add(tid)

        attrs = t.get("attributes") or []
        if not isinstance(attrs, list) or not attrs:
            return _schema_error(f"tables[{idx}].attributes must be a non-empty array")
        attrs = [str(a) for a in attrs]

        pk = t.get("primary_key") or []
        if not isinstance(pk, list) or not pk:
            return _schema_error(f"tables[{idx}].primary_key must be an array")
        pk = [str(k) for k in pk]
        bad_pk = [k for k in pk if k not in attrs]
        if bad_pk:
            return _schema_error(f"tables[{idx}].primary_key {bad_pk} not in attributes")

        raw_col_desc = t.get("column_desc") or {}
        if not isinstance(raw_col_desc, dict):
            return _schema_error(f"tables[{idx}].column_desc must be an object")
        data_cols = [a for a in attrs if a not in pk]
        if error := _search_policy_error(tid, ((col, raw_col_desc.get(col)) for col in data_cols)):
            return _schema_error(f"{error}")
        col_desc: dict[str, ColumnDesc] = {}
        for col, cd in raw_col_desc.items():
            if col not in attrs:
                continue
            if isinstance(cd, dict):
                check = None
                chk = cd.get("check")
                if chk is not None:
                    if not isinstance(chk, dict):
                        return _schema_error(
                            f"tables[{idx}].column_desc[{col!r}].check must be an object")
                    unknown = set(chk) - {"min", "max", "enum"}
                    if unknown:
                        return _schema_error(
                            f"tables[{idx}].column_desc[{col!r}].check has unknown keys "
                            f"{sorted(unknown)} (allowed: min, max, enum)")
                    try:
                        check = ColumnCheck(
                            min=float(chk["min"]) if chk.get("min") is not None else None,
                            max=float(chk["max"]) if chk.get("max") is not None else None,
                            enum=[str(e) for e in chk["enum"]]
                            if chk.get("enum") is not None else None,
                        )
                    except (TypeError, ValueError) as e:
                        return _schema_error(
                            f"tables[{idx}].column_desc[{col!r}].check invalid: {e}")
                requires_search = cd.get("requires_search", True)
                if not isinstance(requires_search, bool):
                    return _schema_error(f"column_desc[{col!r}].requires_search must be a boolean")
                col_desc[col] = ColumnDesc(
                    type=str(cd.get("type", "str")).strip(),
                    desc=str(cd.get("desc", "")).strip(),
                    check=check,
                    requires_search=requires_search,
                )
            elif isinstance(cd, str):
                col_desc[col] = ColumnDesc(desc=cd.strip())
            if col not in col_desc:
                continue
            conflict = _unit_gloss_conflict(f"{col}：{col_desc[col].desc}")
            if conflict:
                return _schema_error(
                    f"tables[{idx}].column_desc[{col!r}] unit gloss contradicts "
                    f"arithmetic: {conflict}. Never gloss two magnitudes of different "
                    "scale as equivalent — state the exact conversion instead "
                    "(e.g. \"1 billion = 10亿\") or drop the foreign-unit gloss."
                )

        seeds = t.get("seed_entities") or []
        if not isinstance(seeds, list):
            return _schema_error(f"tables[{idx}].seed_entities must be an array")
        normalized_seeds: list[str] = []
        seed_key_values: dict[str, dict[str, str]] = {}
        seed_assertions: dict[str, dict[str, Any]] = {}
        for si, s in enumerate(seeds):
            if isinstance(s, dict):
                if not pk:
                    return _schema_error(
f"tables[{idx}].seed_entities[{si}] is "
                        "an object, but this table has no primary_key. "
                        "Use row-key strings instead."
                    )
                key_vals: dict[str, str] = {}
                missing_pk: list[str] = []
                for key in pk:
                    val = _cell_value(s.get(key))
                    if not val or val.lower() in {"null", "none", "n/a"}:
                        missing_pk.append(key)
                    else:
                        key_vals[key] = val
                if missing_pk:
                    return _schema_error(
f"tables[{idx}].seed_entities[{si}] row "
                        f"object missing primary key value(s) {missing_pk}. "
                        "Row objects must include every primary_key column."
                    )
                joined = TableSchema.make_entity_key(key_vals, pk)
                if not joined:
                    continue
                normalized_seeds.append(joined)
                if joined in seed_key_values and seed_key_values[joined] != key_vals:
                    return _schema_error(f"conflicting primary-key fields for seed {joined!r}")
                seed_key_values[joined] = key_vals
                inline = {
                    col: s[col]
                    for col in data_cols
                    if col in s and _cell_value(s.get(col))
                }
                if inline:
                    for col, raw in inline.items():
                        desc = col_desc.get(col)
                        if desc is None or desc.requires_search:
                            source_fields.add(f"{tid}.{col}")
                            continue
                        if desc.check and (reason := desc.check.violation(raw)):
                            return _schema_error(f"{col}: {reason}")
                        seed_assertions.setdefault(joined, {})[col] = raw
            else:
                return _schema_error(f"tables[{idx}].seed_entities[{si}] must be a row object")
        bad_seed = [e for e in normalized_seeds if any(value.lower() in _PLACEHOLDERS for value in seed_key_values[e].values())]
        if bad_seed:
            return _schema_error(f"placeholder seed_entities rejected: {bad_seed}")

        parsed_tables.append({
            "table_id": tid,
            "table_label": str(t.get("table_label") or ""),
            "row_label": str(t.get("row_label") or ""),
            "attributes": attrs,
            "primary_key": pk,
            "column_desc": col_desc,
            "seed_entities": normalized_seeds,
            "seed_key_values": seed_key_values,
            "seed_assertions": seed_assertions,
        })

    # ---- Validate relations ----
    parsed_relations: list[dict] = []
    for idx, r in enumerate(relations):
        if not isinstance(r, dict):
            return _schema_error(f"relations[{idx}] must be an object")
        unknown = set(r) - _RELATION_KEYS
        if unknown:
            return _schema_error(
                f"relations[{idx}] has unknown keys {sorted(unknown)} "
                f"(allowed: {sorted(_RELATION_KEYS)})"
            )
        ft = str(r.get("from_table") or "").strip()
        tt = str(r.get("to_table") or "").strip()
        if ft not in seen_ids:
            return _schema_error(f"relations[{idx}].from_table {ft!r} not declared in tables")
        if tt not in seen_ids:
            return _schema_error(f"relations[{idx}].to_table {tt!r} not declared in tables")
        fk = r.get("foreign_key") or []
        if not isinstance(fk, list) or not fk:
            return _schema_error(f"relations[{idx}].foreign_key must be a non-empty array")
        fk = [str(c) for c in fk]
        ft_attrs = next(t["attributes"] for t in parsed_tables if t["table_id"] == ft)
        bad_fk = [c for c in fk if c not in ft_attrs]
        if bad_fk:
            return _schema_error(f"relations[{idx}].foreign_key {bad_fk} not in {ft}.attributes")
        target_cols = r.get("target_columns") or []
        if not isinstance(target_cols, list):
            return _schema_error(f"relations[{idx}].target_columns must be an array")
        target_cols = [str(c) for c in target_cols]
        if not target_cols:
            target_cols = list(next(t["primary_key"] for t in parsed_tables if t["table_id"] == tt))
        try:
            rk = RelationKind(str(r.get("kind") or "one_to_many"))
        except ValueError:
            rk = RelationKind.ONE_TO_MANY
        parsed_relations.append({
            "from_table": ft, "to_table": tt,
            "foreign_key": fk, "target_columns": target_cols,
            "kind": rk, "label": str(r.get("label") or ""),
        })

    # ---- Seed-PK evidence helper ----------------------------------------
    def _seed_pk_evidence(state: Any, tid: str, ent: str, pk: list[str]) -> None:
        """Attach a synthetic explore-source evidence node to each PK cell of
        a freshly-seeded row, so coverage_score (filled/total) and the
        SOCM headline (with-evidence/total) agree on the seeded row.
        """
        if not pk:
            return
        import hashlib
        import time

        from searchos.socm import EvidenceNode

        pk_values = state.coverage_map.primary_key_values(ent, table_id=tid)
        # Find the explore briefing source if present, else a generic stub.
        source_url = ""
        for p in (state.pending_agent_summaries or []):
            if "/final_summary" in (p.get("source_url") or ""):
                source_url = p["source_url"]; break
        if not source_url:
            source_url = "agent://explore_agent/seed"

        for col in pk:
            val = pk_values[col]
            eid_seed = state.coverage_map.cell_key(tid, ent, col)
            eid = f"f_seed_{hashlib.md5(eid_seed.encode()).hexdigest()[:10]}"
            node = EvidenceNode(
                id=eid,
                finding=f"{ent} {col}: {val}",
                value=val,
                source=source_url,
                source_excerpt="",
                confidence=0.95,
                entity=ent,
                attribute=col,
                alignment="full",
                alignment_note="seeded from explore briefing",
                source_authority="aggregator",
                table_id=tid,
                created_at=time.time(),
            )
            commit_evidence(state, [node])

    state = _ctx.workspace.load_state()

    # ---- Reject existing table IDs (additive create) ----
    existing = state.coverage_map.tables
    for t in parsed_tables:
        if t["table_id"] in existing:
            return _schema_error(
                f"table_id {t['table_id']!r} already exists. Modify it with "
                "add_columns / add_entities / remove_entities / edit_entities, or use a "
                "new table_id for a genuinely different table."
            )

    # ---- Required-attributes coverage check (eval mode), union over all tables ----
    required = state.required_attributes
    if required:
        all_attrs_lower = set()
        attr_lists = [t["attributes"] for t in parsed_tables]
        attr_lists += [sch.attributes for sch in existing.values()]
        for attrs in attr_lists:
            for a in attrs:
                all_attrs_lower.add(a.lower().replace("_", " ").replace("-", " ").strip())
        missing = [
            r for r in required
            if r.lower().replace("_", " ").replace("-", " ").strip() not in all_attrs_lower
        ]
        matched = [r for r in required if r not in missing]
        if missing:
            # Warn but proceed: an incomplete schema is still committed so
            # work can start, rather than blocking creation outright.
            logger.warning(
                "schema.create: schema does not cover all required "
                "columns — proceeding anyway. Required: %s. Matched: %s. "
                "Missing (%d): %s",
                required, matched, len(missing), missing,
            )

    # Row-identity (primary key) hint check — warn, don't block. When a run
    # seeded primary_key_hint (eval --seed-primary-key with the benchmark's
    # unique_columns), nudge the agent to keep the committed primary_key on the
    # same grain the scorer aligns rows on.
    pk_hint = getattr(state, "primary_key_hint", None) or []
    if pk_hint:
        def _norm_pk(s: str) -> str:
            return s.lower().replace("_", " ").replace("-", " ").strip()
        covered: set[str] = set()
        for t in parsed_tables:
            covered |= {_norm_pk(k) for k in t["primary_key"]}
        missing_pk = [c for c in pk_hint if _norm_pk(c) not in covered]
        if missing_pk:
            logger.warning(
                "schema.create: primary_key does not cover row-identity "
                "hint %s — committed keys: %s. Missing: %s",
                pk_hint, sorted(covered), missing_pk,
            )

    # ---- Atomic commit (purely additive — no existing table is touched) ----
    def _commit(state: Any) -> Any:
        for t in parsed_tables:
            state.coverage_map.add_table(
                t["table_id"], list(t["attributes"]),
                table_label=t["table_label"],
                primary_key=list(t["primary_key"]),
                row_label=t["row_label"],
                column_desc=dict(t["column_desc"]),
                entities=list(t["seed_entities"]),
                entity_values=t["seed_key_values"],
            )
            # add_table inserted rows + cells; anchor each seeded PK cell to a
            # synthetic explore evidence node so coverage_score and the SOCM
            # headline treat seeded rows as evidence-backed, not bare
            # placeholders.
            if (state.source_scope or {}).get("mode") != "hybrid":
                for ent in t["seed_entities"]:
                    _seed_pk_evidence(state, t["table_id"], ent, list(t["primary_key"]))
            for ent, col_vals in t["seed_assertions"].items():
                for col, raw_val in col_vals.items():
                    set_inferred_value(state.coverage_map, t["table_id"], ent, col, raw_val)
        for r in parsed_relations:
            state.coverage_map.add_relation(Relation(
                from_table=r["from_table"],
                foreign_key=ForeignKey(
                    target_table=r["to_table"],
                    columns=r["foreign_key"],
                    target_columns=r["target_columns"],
                ),
                kind=r["kind"],
                label=r["label"],
            ))
        return state

    state = _ctx.workspace.atomic_update_state(_commit)

    # Replay any pending explore final-summaries: they were stashed by
    # extraction's _flush_snapshot when no schema existed yet. Now that
    # tables are committed, run extraction synchronously so cells start
    # filled before the first dispatch round. Worth the wall-time cost
    # — fire-and-forget would race the next dispatch_agents and let
    # sub-agents observe an empty SOCM that explore already populated.
    pending_count = 0
    from searchos.config.settings import settings
    replay_model = _select_replay_model(_ctx)
    if (
        settings.enable_explore_replay
        and state.pending_agent_summaries
        and replay_model is not None
    ):
        from searchos.harness.middleware.extraction import (
            replay_pending_summaries,
        )
        try:
            pending_count = await replay_pending_summaries(
                _ctx.workspace,
                replay_model,
                [t["table_id"] for t in parsed_tables],
                trajectory_logger=_ctx.trajectory_logger,
            )
            state = _ctx.workspace.load_state()
        except Exception as e:  # noqa: BLE001 — replay is best-effort
            logger.warning(
                "explore-summary replay failed: %s(%s)",
                type(e).__name__, str(e).strip(), exc_info=True,
            )

    tables_out = []
    for t in parsed_tables:
        schema = state.coverage_map.tables[t["table_id"]]
        tables_out.append({
            "table_id": t["table_id"],
            "entities": len(schema.entities),
            "attributes": len(schema.attributes),
        })
    payload = {
        "tables": tables_out,
        "relations": len(parsed_relations),
        "total_cells": state.coverage_map.total_cells,
    }
    if pending_count:
        payload["explore_replay"] = {
            "items": pending_count,
            "evidence_nodes": state.evidence_graph.node_count,
            "coverage_score": state.coverage_map.coverage_score,
        }
    if source_fields:
        payload["source_required"] = sorted(source_fields)
        payload["next_step"] = (
            "Inline values skipped; retrieve sources for "
            + ", ".join(sorted(source_fields))
        )
    return _schema_ok(payload)


@tool(parse_docstring=True)
async def add_columns(table_id: str, columns: list[dict[str, Any]]) -> str:
    """Add or revise non-key columns by exact name. Returns JSON with added_columns,
    updated_columns, new_missing_cells and reopened_inferred_cells.

    For example, to add a column, pass columns containing
    [{"name":"Rate","requires_search":true,"type":"int","desc":"Requests per minute","check":{"min":0}}].
    To revise only the search policy, pass [{"name":"院校层次","requires_search":false}]. Fill reliably
    inferable values with edit_entities. Enabling requires_search reopens inferred cells for source
    retrieval and preserves source-backed values.

    Args:
        table_id: ID of the existing table.
        columns: Non-empty array of column definitions. New columns require name and a boolean
            requires_search. Optional type defaults to str. For existing columns, supply only the
            fields to change. desc explains the value. check replaces the entire min/max/enum
            admission rule for future writes. Set check to null to clear it.
    """
    import math

    from searchos.socm import ColumnDesc

    workspace = _ctx.workspace
    if workspace is None:
        return _schema_error("workspace not initialized")
    try:
        if not isinstance(columns, list) or not columns:
            raise ValueError("columns must be a non-empty array")
        specs = {}
        for row in columns:
            if not isinstance(row, dict) or set(row) - {"name", "type", "desc", "check", "requires_search"}:
                raise ValueError("Allowed column fields: name, requires_search, type, desc, check")
            name = row.get("name")
            if not isinstance(name, str) or not name.strip() or name != name.strip():
                raise ValueError("Column names must be non-empty and have no surrounding whitespace")
            if name in specs:
                raise ValueError(f"Duplicate column: {name}")
            specs[name] = row
    except (ValueError, TypeError) as exc:
        return _schema_error(str(exc))

    def commit(state):
        schema = state.coverage_map.get_table(table_id)
        if schema is None:
            raise ValueError(f"Unknown table: {table_id}")
        policies = ((name, row) for name, row in specs.items()
                    if name not in schema.attributes or "requires_search" in row)
        if error := _search_policy_error(table_id, policies):
            raise ValueError(error)
        column_defs = {}
        for name, row in specs.items():
            check = row.get("check")
            if check is not None and (not isinstance(check, dict) or set(check) - {"min", "max", "enum"}):
                raise ValueError("check supports only min/max/enum")
            description = ColumnDesc.model_validate({key: value for key, value in row.items() if key != "name"})
            if description.check:
                limits = description.check
                if any(value is not None and not math.isfinite(value) for value in (limits.min, limits.max)):
                    raise ValueError("Numeric limits must be finite")
                if limits.min is not None and limits.max is not None and limits.min > limits.max:
                    raise ValueError("Column min cannot exceed max")
            conflict = _unit_gloss_conflict(f"{name}：{description.desc}")
            if conflict:
                raise ValueError(f"Column unit gloss contradicts arithmetic: {conflict}")
            column_defs[name] = description
        added, updated, reopened = state.coverage_map.upsert_columns(table_id, column_defs)
        receipt.update(added_columns=added, updated_columns=updated, reopened_inferred_cells=reopened,
                       new_missing_cells=len(added) * len(schema.entities))
        return state

    receipt = {"table_id": table_id,
               "next_step": "Fill inferable fields with edit_entities; retrieve source-required fields."}
    try:
        workspace.atomic_update_state(commit)
    except (ValueError, TypeError) as exc:
        return _schema_error(str(exc))
    return _schema_ok(receipt)


_CURSOR_QUERY_FIELDS = ("table_id", "status", "row", "attribute", "unassigned_only")
_VALUE_COUNTS_TOP = 50


def _cursor_error(*, decoded: dict | None = None, expected: list | None = None) -> str:
    payload = {
        "error": "Invalid cursor or changed filters; restart with cursor=''.",
        "hint": "Keep status, row, attribute, and unassigned_only unchanged across pages. "
                "with_values and limit may change. After table edits, restart from the first page.",
    }
    if decoded is not None and expected is not None and isinstance(decoded.get("query"), list):
        got = decoded["query"]
        changed = [
            name for index, name in enumerate(_CURSOR_QUERY_FIELDS)
            if index >= len(got) or got[index] != expected[index]
        ]
        if decoded.get("version") != STATE_FORMAT_VERSION:
            changed.append("version")
        if changed:
            payload["changed_filters"] = changed
    return json.dumps(payload, ensure_ascii=False)


@tool(parse_docstring=True)
async def read_table(
    table_id: str = "", status: str = "all", with_values: bool = True,
    row: RowRef | None = None, attribute: str = "", unassigned_only: bool = False,
    limit: int = 30, cursor: str = "",
) -> str:
    """Read table coverage statistics and one page of rows. Row identity uses RowRef
    {table_id, key} with key values in primary_key order.

    Returns table_id, primary_key, columns, summary, rows, count, total_matched and next_cursor.
    When attribute is set, also returns value_counts for that column over all matched rows.
    Row arrays follow column order, starting with key values. Cell objects flag comparisons,
    conflicts, unavailable values or active_task_ids. Pages keep each row intact and target
    12,000 characters. For citations, supply an exact row and set with_values=true.

    Args:
        table_id: Table to read. Defaults to the row's table or the active table.
        status: Row filter applied to the selected columns: all, filled, partial, empty,
            unresolved, actionable, conflict or unavailable. Filled means every selected cell
            is settled. Pending comparisons await review.
        with_values: True returns full values and null for missing cells. False returns cell
            states. May change between pages; does not invalidate the cursor.
        row: Optional exact RowRef or known alias.
        attribute: Exact non-key column name. Applies status and the row filter to that column
            and includes value_counts for its display values.
        unassigned_only: Show actionable cells without a pending, running or blocked search
            task. Other fields appear as status excluded. Reading reserves no work.
        limit: Maximum complete rows per page, default 30, capped at 200. May change between
            pages.
        cursor: Pass next_cursor while keeping status, row, attribute and unassigned_only the
            same. Restart with cursor='' after table mutations or when filters change.
    """
    if _ctx.workspace is None:
        return json.dumps({"error": "workspace not initialized"})
    if status not in {"filled", "partial", "empty", "all", "unresolved", "actionable",
                      "conflict", "unavailable"}:
        return json.dumps({"error": "unknown row status"})
    state = _ctx.workspace.load_state()
    cmap = state.coverage_map
    if row and table_id and row.table_id != table_id:
        return json.dumps({"error": "RowRef table does not match table_id"})
    tid = (row.table_id if row else table_id) or cmap.primary_table_id
    ts = cmap.tables.get(tid)
    if ts is None:
        return json.dumps({
            "error": f"unknown table_id {tid!r}",
            "available": list(cmap.tables),
        }, ensure_ascii=False)

    from searchos.socm.coverage import answer_evidence, project_cell_evidence
    from searchos.socm.coverage.models import cell_is_actionable, cell_is_complete
    from searchos.socm.evidence.provenance import evidence_citation
    from searchos.socm.views.snapshot import SearchStateSnapshot

    selected_entity = cmap.resolve_entity(row.row_key(), table_id=tid) if row else ""
    selected_attr = ts.attribute_aliases.get(attribute, attribute)
    if attribute and selected_attr not in ts.data_columns:
        return json.dumps({"error": f"unknown data column {attribute!r}"})
    query = [tid, status, row.model_dump() if row else None, selected_attr, unassigned_only]
    after = None
    if cursor:
        decoded = None
        try:
            decoded = json.loads(base64.urlsafe_b64decode(cursor.encode()))
            if (decoded.get("version") != STATE_FORMAT_VERSION
                    or decoded.get("query") != query
                    or not isinstance(decoded.get("after"), str)):
                raise ValueError("cursor filter mismatch")
            after = decoded["after"]
        except (ValueError, KeyError, TypeError, UnicodeError):
            return _cursor_error(decoded=decoded if isinstance(decoded, dict) else None,
                                 expected=query)
    snapshot = next(t for t in SearchStateSnapshot.from_state(state).tables if t.table_id == tid)
    primary_key = snapshot.primary_key or ["Entity"]
    attributes = [selected_attr] if attribute else snapshot.data_columns
    matched = []
    for record in snapshot.rows:
        if row and record.entity != selected_entity:
            continue
        cells = [c for c in record.cells if not attribute or c.attr == selected_attr]
        if unassigned_only:
            cells = [c for c in cells if cell_is_actionable(c) and not c.active_task_ids]
        if not cells and (attribute or unassigned_only):
            continue
        complete = all(cell_is_complete(c) for c in cells)
        has_value = any(c.status == "filled" or c.display_hint for c in cells)
        matches = {
            "all": True, "filled": complete, "partial": has_value and not complete,
            "empty": not has_value and not complete, "unresolved": not complete,
            "actionable": any(cell_is_actionable(c) for c in cells),
            "conflict": any(c.has_conflict or c.conflict_status == "confirmed" for c in cells),
            "unavailable": any(c.status == "hard_cell" for c in cells),
        }
        if matches[status]:
            matched.append((record.entity, cells))
    remaining = [(ent, cells) for ent, cells in matched if after is None or ent > after]
    include_citations = row is not None and with_values
    evidence = {node.id: node for node in answer_evidence(state)} if include_citations else {}
    summary = {**snapshot.summary(), "column_definitions": snapshot.column_descriptions}
    if snapshot.inferred_columns:
        summary["inferred_columns"] = snapshot.inferred_columns
    out = dict(table_id=tid, primary_key=primary_key, columns=primary_key + attributes,
               summary=summary, rows=[], count=0, total_matched=len(matched), next_cursor=None)
    if attribute:
        from collections import Counter
        counts: Counter[str] = Counter()
        for ent, cells in matched:
            info = next((c for c in cells if c.attr == selected_attr), None)
            cell = cmap.cells.get(cmap.cell_key(tid, ent, selected_attr))
            value = cell.value if cell and cell.value != "" else None
            if value is None:
                label = "_missing_"
            elif with_values:
                label = str(value)
            else:
                label = info.status if info else "_missing_"
            counts[label] += 1
        top = counts.most_common(_VALUE_COUNTS_TOP)
        out["value_counts"] = {
            "attribute": selected_attr,
            "total_matched": len(matched),
            "counts": {key: value for key, value in top},
            "truncated": len(counts) > len(top),
            "distinct": len(counts),
        }
    page_chars = len(json.dumps(out, ensure_ascii=False))
    page = remaining[:max(1, min(int(limit), 200))]
    for ent, cells in page:
        displayed = {}
        for info in cells:
            cell = cmap.cells.get(cmap.cell_key(tid, ent, info.attr)) if with_values else None
            value = cell.value if cell and cell.value != "" else None
            citation_fields = None
            if include_citations and value is not None and not info.inferred:
                node = evidence.get(cell.primary_evidence_id)
                if node is None or project_cell_evidence(cmap, node, tid, ent, info.attr) is None:
                    citation_fields = {"citation_gap": "evidence_unavailable"}
                elif citation := evidence_citation(node):
                    citation_fields = {"citation": citation}
                else:
                    citation_fields = {"citation_gap": "original_source_missing"}
            displayed[info.attr] = render_cell(info, value, with_values=with_values,
                                              include_tasks=True, citation=citation_fields)
        values = row_values(ent) + [displayed.get(attr, {"status": "excluded"}) for attr in attributes]
        page_chars += len(json.dumps(values, ensure_ascii=False)) + 2
        if out["rows"] and page_chars > 12_000:
            break
        out["rows"].append(values)
    out["count"] = count = len(out["rows"])
    if count and count < len(remaining):
        out["next_cursor"] = base64.urlsafe_b64encode(json.dumps(
            {"version": STATE_FORMAT_VERSION, "query": query, "after": page[count - 1][0]}, ensure_ascii=False,
        ).encode()).decode()
    return json.dumps(out, ensure_ascii=False)


read_table.args_schema.model_config["extra"] = "forbid"
read_table.args_schema.model_rebuild(force=True)
