"""创建表结构与追加列，并校验列约束、种子行和关系。"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.tools import tool

from searchos.socm.coverage import commit_evidence

from . import assertions

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


@tool
async def create_schema(
    tables_json: str,
    relations_json: str = "",
) -> str:
    """Define SOCM coverage tables. Additive — every call ADDS tables; none
    are ever wiped, and all tables coexist permanently.

    A table whose columns exactly match one that already exists is refused as
    a duplicate; a table whose ``table_id`` already exists is also refused.
    To add columns to an existing table use ``add_columns``; for rows use
    ``add_entities`` / ``remove_entities`` /
    ``edit_entities``. To introduce a genuinely new table (different columns,
    new ``table_id``), call this again — it is appended alongside the rest.

    Args:
        tables_json: JSON array of table objects. Each object:
            {
              "table_id": str,           # unique id, required
              "table_label": str,        # human label, optional
              "row_label": str,          # singular noun for a row, optional
              "attributes": [str],       # column names, required non-empty
              "primary_key": [str],      # subset of attributes, optional
              "column_desc": {col: {"type": "<str|int|float|date|list[str]|...>",
                                    "desc": "<format + semantic clarification>",
                                    "check": {"min": num, "max": num, "enum": [str]}}},
                # e.g. {"release_year": {"type": "int", "desc": "YYYY, earliest release year across all regions"},
                #        "score": {"type": "int", "desc": "总分分数线，非单科线"}}
                # type: data type for validation/rendering.
                # desc: format constraint + semantic clarification so the
                #   extractor knows WHICH value to pick when multiple
                #   candidates exist on a page (e.g. which score line,
                #   which date, which unit). Leave empty if the column
                #   name is self-explanatory.
                # check: OPTIONAL hard admission rule, enforced mechanically
                #   at ingest — rows violating it are rejected. RECOMMENDED
                #   when the task scope maps to an obvious numeric range /
                #   threshold / closed set (e.g. a year column scoped
                #   "since 2008" -> {"min": 2008}; "count >= 2" ->
                #   {"min": 2}). Do NOT force one for semantic constraints
                #   (e.g. "full paper only") — keep those in desc prose.
                #   For list columns the check applies to every element.
              "seed_entities": [str] or [[str]] or [{row object}]
                # rows to pre-create, optional
                # Single PK: ["Harvard", "MIT"]
                # Multi PK: [["Arts and Humanities", "Harvard"], ["Engineering", "MIT"]]
                # Row object: [{"Ranking": 1, "Name": "IShowSpeed"}]
                #   primary_key columns define the row key; non-PK columns are
                #   seeded as inline assertions.
            }
        relations_json: JSON array of relation objects (omit for single-table). Each:
            {
              "from_table": str, "to_table": str,
              "foreign_key": [str],          # columns in from_table
              "target_columns": [str],       # in to_table; default = its primary_key
              "kind": "one_to_many"|"many_to_one"|"many_to_many",
              "label": str
            }

    Multi-table guideline: each table's attributes are exactly its own
    primary_key + foreign-key columns + columns determined by its own
    primary_key. If the same non-PK value would appear in two tables,
    that's your signal to put it in one and reference via a relation.
    """
    if assertions._orch_ctx().workspace is None:
        return "Error: workspace not initialized"

    try:
        tables = json.loads(tables_json) if tables_json else []
    except json.JSONDecodeError as e:
        return f"Error: invalid tables_json — {e}"
    if not isinstance(tables, list) or not tables:
        return "Error: tables_json must be a non-empty JSON array"

    try:
        relations = json.loads(relations_json) if relations_json else []
    except json.JSONDecodeError as e:
        return f"Error: invalid relations_json — {e}"
    if not isinstance(relations, list):
        return "Error: relations_json must be a JSON array (or empty)"

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
    parsed_tables: list[dict] = []
    for idx, t in enumerate(tables):
        if not isinstance(t, dict):
            return f"Error: tables_json[{idx}] must be an object"
        tid = str(t.get("table_id") or "").strip()
        if not tid:
            return f"Error: tables_json[{idx}].table_id is required"
        if tid in seen_ids:
            return f"Error: duplicate table_id {tid!r}"
        seen_ids.add(tid)

        attrs = t.get("attributes") or []
        if not isinstance(attrs, list) or not attrs:
            return f"Error: tables_json[{idx}].attributes must be a non-empty array"
        attrs = [str(a) for a in attrs]

        pk = t.get("primary_key") or []
        if not isinstance(pk, list):
            return f"Error: tables_json[{idx}].primary_key must be an array"
        pk = [str(k) for k in pk]
        bad_pk = [k for k in pk if k not in attrs]
        if bad_pk:
            return f"Error: tables_json[{idx}].primary_key {bad_pk} not in attributes"

        raw_col_desc = t.get("column_desc") or {}
        if not isinstance(raw_col_desc, dict):
            return f"Error: tables_json[{idx}].column_desc must be an object"
        col_desc: dict[str, ColumnDesc] = {}
        for col, cd in raw_col_desc.items():
            if col not in attrs:
                continue
            if isinstance(cd, dict):
                check = None
                chk = cd.get("check")
                if chk is not None:
                    if not isinstance(chk, dict):
                        return (f"Error: tables_json[{idx}].column_desc[{col!r}]"
                                ".check must be an object")
                    unknown = set(chk) - {"min", "max", "enum"}
                    if unknown:
                        return (f"Error: tables_json[{idx}].column_desc[{col!r}]"
                                f".check has unknown keys {sorted(unknown)} "
                                "(allowed: min, max, enum)")
                    try:
                        check = ColumnCheck(
                            min=float(chk["min"]) if chk.get("min") is not None else None,
                            max=float(chk["max"]) if chk.get("max") is not None else None,
                            enum=[str(e) for e in chk["enum"]]
                            if chk.get("enum") is not None else None,
                        )
                    except (TypeError, ValueError) as e:
                        return (f"Error: tables_json[{idx}].column_desc[{col!r}]"
                                f".check invalid: {e}")
                col_desc[col] = ColumnDesc(
                    type=str(cd.get("type", "str")).strip(),
                    desc=str(cd.get("desc", "")).strip(),
                    check=check,
                )
            elif isinstance(cd, str):
                col_desc[col] = ColumnDesc(desc=cd.strip())
            if col not in col_desc:
                continue
            conflict = _unit_gloss_conflict(f"{col}：{col_desc[col].desc}")
            if conflict:
                return (
                    f"Error: tables_json[{idx}].column_desc[{col!r}] unit "
                    f"gloss contradicts arithmetic: {conflict}. Never gloss "
                    "two magnitudes of different scale as equivalent — "
                    "state the exact conversion instead (e.g. "
                    "\"1 billion = 10亿\") or drop the foreign-unit gloss."
                )

        seeds = t.get("seed_entities") or []
        if not isinstance(seeds, list):
            return f"Error: tables_json[{idx}].seed_entities must be an array"
        # Support nested lists for multi-PK: [["Arts", "Harvard"], ...]
        # Single PK: ["Harvard", "MIT", ...] (flat strings)
        normalized_seeds: list[str] = []
        seed_assertions: dict[str, dict[str, Any]] = {}
        data_cols = [a for a in attrs if a not in set(pk)]
        for si, s in enumerate(seeds):
            if isinstance(s, dict):
                if not pk:
                    return (
                        f"Error: tables_json[{idx}].seed_entities[{si}] is "
                        "an object, but this table has no primary_key. "
                        "Use row-key strings instead."
                    )
                key_vals: dict[str, str] = {}
                missing_pk: list[str] = []
                for key in pk:
                    val = assertions._cell_value(s.get(key))
                    if not val or val.lower() in {"null", "none", "n/a"}:
                        missing_pk.append(key)
                    else:
                        key_vals[key] = val
                if missing_pk:
                    return (
                        f"Error: tables_json[{idx}].seed_entities[{si}] row "
                        f"object missing primary key value(s) {missing_pk}. "
                        "Row objects must include every primary_key column."
                    )
                joined = TableSchema.make_entity_key(key_vals, pk)
                if not joined:
                    continue
                normalized_seeds.append(joined)
                inline = {
                    col: s[col]
                    for col in data_cols
                    if col in s and assertions._cell_value(s.get(col))
                }
                if inline:
                    seed_assertions.setdefault(joined, {}).update(inline)
            elif isinstance(s, list):
                if pk and len(s) != len(pk):
                    return (
                        f"Error: tables_json[{idx}].seed_entities[{si}] "
                        f"has {len(s)} values but primary_key has {len(pk)} columns. "
                        "seed_entities are PRIMARY-KEY values only — never full "
                        "data rows; non-PK cells are filled later by search "
                        "agents. Keep your table design, just fix the seeds."
                    )
                joined = "|".join(str(v).strip() for v in s)
                if not joined:
                    continue
                normalized_seeds.append(joined)
            else:
                val = str(s).strip()
                if val:
                    normalized_seeds.append(val)
        bad_seed = [e for e in normalized_seeds if e.lower() in _PLACEHOLDERS]
        if bad_seed:
            return f"Error: placeholder seed_entities rejected: {bad_seed}"

        parsed_tables.append({
            "table_id": tid,
            "table_label": str(t.get("table_label") or ""),
            "row_label": str(t.get("row_label") or ""),
            "attributes": attrs,
            "primary_key": pk,
            "column_desc": col_desc,
            "seed_entities": normalized_seeds,
            "seed_assertions": seed_assertions,
        })

    # ---- Validate relations ----
    parsed_relations: list[dict] = []
    for idx, r in enumerate(relations):
        if not isinstance(r, dict):
            return f"Error: relations_json[{idx}] must be an object"
        ft = str(r.get("from_table") or "").strip()
        tt = str(r.get("to_table") or "").strip()
        if ft not in seen_ids:
            return f"Error: relations_json[{idx}].from_table {ft!r} not declared in tables_json"
        if tt not in seen_ids:
            return f"Error: relations_json[{idx}].to_table {tt!r} not declared in tables_json"
        fk = r.get("foreign_key") or []
        if not isinstance(fk, list) or not fk:
            return f"Error: relations_json[{idx}].foreign_key must be a non-empty array"
        fk = [str(c) for c in fk]
        ft_attrs = next(t["attributes"] for t in parsed_tables if t["table_id"] == ft)
        bad_fk = [c for c in fk if c not in ft_attrs]
        if bad_fk:
            return f"Error: relations_json[{idx}].foreign_key {bad_fk} not in {ft}.attributes"
        target_cols = r.get("target_columns") or []
        if not isinstance(target_cols, list):
            return f"Error: relations_json[{idx}].target_columns must be an array"
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

        pk_values = ent.split("|") if "|" in ent else [ent]
        # Find the explore briefing source if present, else a generic stub.
        source_url = ""
        for p in (state.pending_agent_summaries or []):
            if "/final_summary" in (p.get("source_url") or ""):
                source_url = p["source_url"]; break
        if not source_url:
            source_url = "agent://explore_agent/seed"

        for idx, col in enumerate(pk):
            val = pk_values[idx] if idx < len(pk_values) else ent
            eid_seed = f"seed_{tid}_{col}_{ent}"
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

    state = assertions._orch_ctx().workspace.load_state()

    # ---- Dedup against existing tables (additive create) ----
    existing = state.coverage_map.tables
    headers_by_table = {tid: tuple(sch.attributes) for tid, sch in existing.items()}
    for t in parsed_tables:
        if t["table_id"] in existing:
            return (
                f"Error: table_id {t['table_id']!r} already exists. Modify it "
                "with add_columns / add_entities / remove_entities / edit_entities, or use a "
                "new table_id for a genuinely different table."
            )
        dup = next((tid for tid, hdr in headers_by_table.items()
                    if hdr == tuple(t["attributes"])), None)
        if dup is not None:
            return (
                f"Error: table {t['table_id']!r} has the same columns as "
                f"table {dup!r} — refusing duplicate. Add rows to "
                f"{dup!r} with add_entities instead."
            )
        headers_by_table[t["table_id"]] = tuple(t["attributes"])

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
                    val = assertions._cell_value(raw_val)
                    if not val:
                        continue
                    assertions._assert_cell_value(
                        state,
                        table_id=t["table_id"],
                        entity=ent,
                        attribute=col,
                        value=val,
                        source="agent://orchestrator/seed",
                        evidence_prefix="seed_attr",
                        alignment_note="seeded by orchestrator from row object",
                        raw_value=raw_val,
                    )
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

    state = assertions._orch_ctx().workspace.atomic_update_state(_commit)

    # Replay any pending explore final-summaries: they were stashed by
    # extraction's _flush_snapshot when no schema existed yet. Now that
    # tables are committed, run extraction synchronously so cells start
    # filled before the first dispatch round. Worth the wall-time cost
    # — fire-and-forget would race the next dispatch_agents and let
    # sub-agents observe an empty SOCM that explore already populated.
    pending_count = 0
    from searchos.config.settings import settings
    replay_model = _select_replay_model(assertions._orch_ctx())
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
                assertions._orch_ctx().workspace,
                replay_model,
                [t["table_id"] for t in parsed_tables],
                trajectory_logger=assertions._orch_ctx().trajectory_logger,
            )
            state = assertions._orch_ctx().workspace.load_state()
        except Exception as e:  # noqa: BLE001 — replay is best-effort
            logger.warning(
                "explore-summary replay failed: %s(%s)",
                type(e).__name__, str(e).strip(), exc_info=True,
            )

    summaries = []
    for t in parsed_tables:
        n_ent = len(state.coverage_map.tables[t["table_id"]].entities)
        n_attr = len(state.coverage_map.tables[t["table_id"]].attributes)
        summaries.append(f"{t['table_id']}({n_ent}×{n_attr})")
    rel_summary = (
        f", {len(parsed_relations)} relation(s)"
        if parsed_relations else ""
    )
    replay_note = ""
    if pending_count:
        has_open_set = any(
            ts.is_column_only for ts in state.coverage_map.tables.values()
        )
        if has_open_set:
            n_rows = sum(
                len(ts.entities) for ts in state.coverage_map.tables.values()
            )
            replay_note = (
                f" Replayed {pending_count} explore summary item(s) — "
                f"{n_rows} row(s) seeded so far, "
                f"{state.evidence_graph.node_count} evidence nodes."
            )
        else:
            replay_note = (
                f" Replayed {pending_count} explore summary item(s) — "
                f"cell fill rate now {state.coverage_map.coverage_score:.0%}, "
                f"{state.evidence_graph.node_count} evidence nodes."
            )
    return (
        f"Schema created: {len(parsed_tables)} table(s) — "
        + ", ".join(summaries)
        + f"{rel_summary}, total {state.coverage_map.total_cells} cells.{replay_note} "
        "Now dispatch sub-agents to fill the cells."
    )


@tool
async def add_columns(table_id: str, columns_json: str) -> str:
    """Add non-primary-key columns to an existing table without replacing its rows or evidence.

    columns_json is a non-empty JSON array, for example:
    [{"name":"Rate","type":"int","desc":"Requests per minute","check":{"min":0}}].
    Only name is required; type defaults to str. check supports min/max/enum.
    An identical retry is a no-op. Existing definitions and primary keys cannot change.
    New cells start missing. Dispatch focused table tasks to read source evidence for
    these columns; existing findings and assistant summaries are not cell values.
    This tool does not fetch sources, dispatch tasks or change source permissions.
    """
    import math

    from pydantic import ValidationError

    from searchos.socm import ColumnDesc

    workspace = assertions._orch_ctx().workspace
    if workspace is None:
        return "Error: workspace not initialized"
    try:
        rows = json.loads(columns_json)
        if not isinstance(rows, list) or not rows:
            raise ValueError("columns_json must be a non-empty JSON array")
        columns = {}
        for row in rows:
            if not isinstance(row, dict) or set(row) - {"name", "type", "desc", "check"}:
                raise ValueError("Each column must contain name and optional type/desc/check")
            name = row.get("name")
            if not isinstance(name, str) or not name.strip() or name != name.strip():
                raise ValueError("Column names must be non-empty and have no surrounding whitespace")
            if name in columns:
                raise ValueError(f"Duplicate column: {name}")
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
            columns[name] = description
    except (ValueError, TypeError, ValidationError) as exc:
        return f"Error: {exc}"

    added = []
    def commit(state):
        added[:] = state.coverage_map.add_columns(table_id, columns)
        return state

    try:
        state = workspace.atomic_update_state(commit)
    except ValueError as exc:
        return f"Error: {exc}"
    return json.dumps({"table_id": table_id, "added_columns": added,
                       "new_missing_cells": len(added) * len(state.coverage_map.tables[table_id].entities),
                       "next_step": "Read original sources in table tasks targeting the new columns."},
                      ensure_ascii=False)
