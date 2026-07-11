"""Orchestrator schema + entity tools (paper §Coverage): create_schema,
add_entities, remove_entities, edit_entities, inspect_table.

Pure SOCM mutations over the orchestrator's bound workspace — no sub-agent
dispatch / scheduler coupling (those tools stay with the orchestrator
runtime). The runtime context (`_ctx`) is reached through a lazy handle so
this module imports standalone, ahead of the agents-layer migration.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.tools import tool

from searchos.util.coerce import coerce_str_list as _coerce_str_list

logger = logging.getLogger(__name__)


def _orch_ctx():
    """Lazy handle on the orchestrator runtime context (bound workspace)."""
    from searchos.agents.runtime import _ctx
    return _ctx


def _select_replay_model(context: Any) -> Any:
    """Explore 回放与在线 Evidence Intake 使用同一个 extraction profile。"""
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
    To change an existing table use ``add_entities`` / ``remove_entities`` /
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
              "seed_entities": [str] or [[str]]  # rows to pre-create, optional
                # Single PK: ["Harvard", "MIT"]
                # Multi PK: [["Arts and Humanities", "Harvard"], ["Engineering", "MIT"]]
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
    if _orch_ctx().workspace is None:
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
        ColumnCheck, ColumnDesc, Relation, ForeignKey, RelationKind,
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
        for si, s in enumerate(seeds):
            if isinstance(s, list):
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
        from searchos.socm import EvidenceNode
        import time, hashlib

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
            state.evidence_graph.add_node(node)
            cell_key = state.coverage_map.cell_key(tid, ent, col)
            cell = state.coverage_map.cells.get(cell_key)
            if cell is not None and eid not in cell.supporting_evidence_ids:
                cell.supporting_evidence_ids.append(eid)

    state = _orch_ctx().workspace.load_state()

    # ---- Dedup against existing tables (additive create) ----
    existing = state.coverage_map.tables
    headers_by_table = {tid: tuple(sch.attributes) for tid, sch in existing.items()}
    for t in parsed_tables:
        if t["table_id"] in existing:
            return (
                f"Error: table_id {t['table_id']!r} already exists. Modify it "
                "with add_entities / remove_entities / edit_entities, or use a "
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
            for ent in t["seed_entities"]:
                _seed_pk_evidence(state, t["table_id"], ent, list(t["primary_key"]))
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

    state = _orch_ctx().workspace.atomic_update_state(_commit)

    # Replay any pending explore final-summaries: they were stashed by
    # extraction's _flush_snapshot when no schema existed yet. Now that
    # tables are committed, run extraction synchronously so cells start
    # filled before the first dispatch round. Worth the wall-time cost
    # — fire-and-forget would race the next dispatch_agents and let
    # sub-agents observe an empty SOCM that explore already populated.
    pending_count = 0
    from searchos.config.settings import settings
    replay_model = _select_replay_model(_orch_ctx())
    if (
        settings.enable_explore_replay
        and state.pending_agent_summaries
        and replay_model is not None
    ):
        from searchos.harness.middleware.extraction.intake import (
            replay_pending_summaries,
        )
        try:
            pending_count = await replay_pending_summaries(
                _orch_ctx().workspace,
                replay_model,
                [t["table_id"] for t in parsed_tables],
                trajectory_logger=_orch_ctx().trajectory_logger,
            )
            state = _orch_ctx().workspace.load_state()
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
async def add_entities(
    entities_json: str,
    table_id: str = "",
    attributes_json: str = "",
) -> str:
    """Add new entity rows to a table, optionally asserting attribute values
    inline (skipping a redundant search round when a sub-agent summary
    already carried the values verbatim).

    Args:
        entities_json: JSON array of entity names to add (duplicates are
            silently skipped). Example: '["MIT","Stanford","ETH Zurich"]'.
        table_id: Target table id. Required in multi-table schemas.
            Defaults to the active table (single-table schemas).
        attributes_json: Optional JSON dict mapping PK value → {column: value}.
            Example: '{"Apollo 11": {"Launch_Date": "1969-07-16",
            "Commander": "Armstrong"}}'. Each provided value is written to
            the cell as a synthetic evidence node (confidence=0.7,
            alignment="full"). Use ONLY when the sub-agent's free-text
            summary you just read carries the value verbatim; do NOT guess.
            PK values omitted from this dict simply get empty rows (current
            behavior). List-valued columns: pass the value as a JSON array
            — it's stored as one evidence node with the items joined by "; ".
    """
    if _orch_ctx().workspace is None:
        return "Error: workspace not initialized"
    try:
        new_entities = json.loads(entities_json)
    except json.JSONDecodeError as e:
        return f"Error: invalid JSON — {e}"
    if not isinstance(new_entities, list) or not new_entities:
        return "Error: entities_json must be a non-empty JSON array"

    asserted: dict[str, dict[str, Any]] = {}
    if attributes_json:
        try:
            raw_attrs = json.loads(attributes_json)
        except json.JSONDecodeError as e:
            return f"Error: invalid attributes_json — {e}"
        if not isinstance(raw_attrs, dict):
            return "Error: attributes_json must be a JSON object {pk: {col: val}}"
        for pk, cols in raw_attrs.items():
            if not isinstance(cols, dict):
                return f"Error: attributes_json[{pk!r}] must be a JSON object"
            asserted[str(pk).strip()] = cols

    state = _orch_ctx().workspace.load_state()
    cmap = state.coverage_map
    if not cmap.tables:
        return "Error: schema is empty. Call ``create_schema`` first."
    if len(cmap.tables) > 1 and not table_id:
        return (
            f"Error: multi-table schema requires table_id. "
            f"Available: {list(cmap.tables)}"
        )
    tid = table_id or cmap.primary_table_id
    if tid not in cmap.tables:
        return f"Error: unknown table_id {tid!r}. Available: {list(cmap.tables)}"

    asserted_source = "agent://orchestrator/asserted"

    added: list[str] = []
    skipped: list[str] = []
    revived: list[str] = []
    backfill_delta = {"v": 0}
    asserted_cells = {"v": 0, "skipped_unknown_col": 0}

    def _apply(s: Any) -> Any:
        from searchos.socm import EvidenceNode
        import time as _time, hashlib as _hashlib

        for e in new_entities:
            if isinstance(e, (list, tuple)):
                name = "|".join(str(v).strip() for v in e)
            else:
                name = str(e).strip()
            if not name:
                continue
            # 此前被 remove_entities 排除的行：orchestrator 显式重加 = 复活
            if s.coverage_map.is_removed_entity(name, table_id=tid):
                if s.coverage_map.restore_entity(name, table_id=tid):
                    revived.append(name)
                continue
            if s.coverage_map.add_entity(name, table_id=tid):
                added.append(name)
            else:
                skipped.append(name)

        schema = s.coverage_map.tables[tid]
        valid_attrs = set(schema.attributes)
        pk_cols = set(schema.primary_key or [])
        for pk_value, col_vals in asserted.items():
            if pk_value not in schema.entities:
                continue
            for col, raw_val in col_vals.items():
                if col not in valid_attrs:
                    asserted_cells["skipped_unknown_col"] += 1
                    continue
                if col in pk_cols:
                    continue
                if isinstance(raw_val, list):
                    val = "; ".join(str(v).strip() for v in raw_val if str(v).strip())
                else:
                    val = str(raw_val).strip()
                if not val:
                    continue
                seed = f"asserted_{tid}_{pk_value}_{col}_{val}"
                eid = f"f_assert_{_hashlib.md5(seed.encode()).hexdigest()[:10]}"
                node = EvidenceNode(
                    id=eid,
                    finding=f"{pk_value} {col}: {val}",
                    value=val,
                    source=asserted_source,
                    source_excerpt="",
                    confidence=0.7,
                    entity=pk_value,
                    attribute=col,
                    alignment="full",
                    alignment_note="asserted by orchestrator from sub-agent summary",
                    source_authority="aggregator",
                    table_id=tid,
                    created_at=_time.time(),
                )
                s.evidence_graph.add_node(node)
                cell_key = s.coverage_map.cell_key(tid, pk_value, col)
                cell = s.coverage_map.cells.get(cell_key)
                if cell is not None and eid not in cell.supporting_evidence_ids:
                    cell.supporting_evidence_ids.append(eid)
                    asserted_cells["v"] += 1

        backfill_delta["v"] = s.coverage_map.backfill_from_evidence(s.evidence_graph)
        return s

    state = _orch_ctx().workspace.atomic_update_state(_apply)
    schema = state.coverage_map.tables[tid]
    backfill_msg = (
        f" Backfilled {backfill_delta['v']} cell(s) from existing evidence."
        if backfill_delta["v"] > 0 else ""
    )
    asserted_msg = ""
    if asserted_cells["v"] or asserted_cells["skipped_unknown_col"]:
        asserted_msg = (
            f" Asserted {asserted_cells['v']} cell value(s) from inline attributes"
            + (f" (skipped {asserted_cells['skipped_unknown_col']} unknown columns)"
               if asserted_cells["skipped_unknown_col"] else "")
            + "."
        )
    revived_msg = f" Revived {len(revived)} previously-removed row(s)." if revived else ""
    return (
        f"[{tid}] Added {len(added)}, skipped {len(skipped)} duplicates."
        f"{revived_msg}{backfill_msg}{asserted_msg} "
        f"Table now has {len(schema.entities)} entities × {len(schema.attributes)} attrs."
    )


@tool
async def remove_entities(
    entities_json: str,
    reason: str,
    table_id: str = "",
) -> str:
    """Remove out-of-scope entity rows (soft delete — auditable, reversible
    via ``add_entities``). Removed rows leave the final table and coverage.

    Use ONLY when an authoritative source POSITIVELY excludes the entity —
    e.g. the official list enumerates the full universe and this entity is
    not on it, or the entity fails an explicit task filter. "I could not
    find data for it" is NOT grounds for removal: keep the row and let
    coverage show the gap.

    Args:
        entities_json: JSON array of entity names (PK strings) to remove.
        reason: Required. Why these rows are out of scope — cite the
            excluding evidence (e.g. "SIPRI fact sheet lists exactly 4
            German companies; this one is not among them").
        table_id: Target table id. Required in multi-table schemas.
    """
    if _orch_ctx().workspace is None:
        return "Error: workspace not initialized"
    if not reason.strip():
        return "Error: reason is required — cite the evidence that excludes these rows"
    names = _coerce_str_list(entities_json)
    if not names:
        return "Error: entities_json must be a non-empty JSON array"

    state = _orch_ctx().workspace.load_state()
    cmap = state.coverage_map
    if not cmap.tables:
        return "Error: schema is empty. Call ``create_schema`` first."
    if len(cmap.tables) > 1 and not table_id:
        return (
            f"Error: multi-table schema requires table_id. "
            f"Available: {list(cmap.tables)}"
        )
    tid = table_id or cmap.primary_table_id
    if tid not in cmap.tables:
        return f"Error: unknown table_id {tid!r}. Available: {list(cmap.tables)}"

    removed: list[str] = []
    not_found: list[str] = []
    plan: list[str] = []
    for name in names:
        canonical = cmap.resolve_entity(name, table_id=tid)
        if canonical is None:
            not_found.append(name)
            continue
        plan.append(canonical)

    if plan:
        full_reason = reason.strip()

        def _apply(s: Any) -> Any:
            for canonical in plan:
                if s.coverage_map.remove_entity(canonical, table_id=tid, reason=full_reason):
                    removed.append(canonical)
            return s

        _orch_ctx().workspace.atomic_update_state(_apply)
        tlog = getattr(_orch_ctx(), "trajectory_logger", None)
        if tlog:
            tlog._append_raw({
                "type": "harness",
                "kind": "entities_removed",
                "table_id": tid,
                "entities": removed,
                "reason": reason[:300],
            })

    state = _orch_ctx().workspace.load_state()
    n_rows = len(state.coverage_map.tables[tid].entities)
    parts = [f"[{tid}] Removed {len(removed)} row(s): {removed}."]
    if not_found:
        parts.append(f"Not found (no matching row): {not_found}.")
    parts.append(
        f"Table now has {n_rows} entities. Removed rows are excluded from "
        "coverage and the final table; re-add via add_entities to undo."
    )
    return " ".join(parts)


@tool
async def edit_entities(
    edits_json: str,
    table_id: str = "",
) -> str:
    """Edit existing entity rows: rename PK and/or overwrite cell values.

    Args:
        edits_json: JSON array of edit operations. Each element is an object:
            - ``entity`` (required): current PK name of the row to edit.
            - ``rename`` (optional): new PK name. Preserves all cell state
              and evidence refs. Example: fix a typo "Apolo 11" → "Apollo 11".
            - ``set`` (optional): dict of {column: value} to overwrite.
              Each value is written as a synthetic evidence node
              (confidence=0.7, alignment="full"). An empty value
              ("", null, or []) CLEARS the cell instead: it resets to
              missing and its old evidence is rejected (kept for audit).
            Example: '[{"entity": "Apolo 11", "rename": "Apollo 11",
                        "set": {"Launch_Date": "1969-07-16"}}]'
        table_id: Target table id. Required in multi-table schemas.
    """
    if _orch_ctx().workspace is None:
        return "Error: workspace not initialized"
    try:
        edits = json.loads(edits_json)
    except json.JSONDecodeError as e:
        return f"Error: invalid JSON — {e}"
    if not isinstance(edits, list) or not edits:
        return "Error: edits_json must be a non-empty JSON array"

    state = _orch_ctx().workspace.load_state()
    cmap = state.coverage_map
    if not cmap.tables:
        return "Error: schema is empty. Call ``create_schema`` first."
    if len(cmap.tables) > 1 and not table_id:
        return (
            f"Error: multi-table schema requires table_id. "
            f"Available: {list(cmap.tables)}"
        )
    tid = table_id or cmap.primary_table_id
    if tid not in cmap.tables:
        return f"Error: unknown table_id {tid!r}. Available: {list(cmap.tables)}"

    asserted_source = "agent://orchestrator/edit"
    renamed: list[str] = []
    set_cells = {"v": 0, "cleared": 0, "skipped_unknown_col": 0}
    errors: list[str] = []

    def _apply(s: Any) -> Any:
        from searchos.socm import CellStatus, EvidenceNode, EvidenceStatus
        import time as _time, hashlib as _hashlib

        for item in edits:
            if not isinstance(item, dict) or "entity" not in item:
                errors.append("each edit must be an object with 'entity' key")
                continue
            raw_name = str(item["entity"]).strip()
            new_name = str(item.get("rename", "")).strip() or None
            set_vals = item.get("set")

            # Rename
            if new_name:
                ok, msg, canonical_old = s.coverage_map.edit_entity(
                    raw_name, new_name, table_id=tid,
                )
                if ok:
                    renamed.append(msg)
                    if canonical_old and canonical_old != new_name:
                        for node in s.evidence_graph.nodes:
                            if node.entity == canonical_old and (
                                not node.table_id or node.table_id == tid
                            ):
                                node.entity = new_name
                    raw_name = new_name
                else:
                    errors.append(f"rename {raw_name!r}: {msg}")
                    continue

            # Set cell values
            if set_vals and isinstance(set_vals, dict):
                canonical = s.coverage_map.resolve_entity(raw_name, table_id=tid)
                if canonical is None:
                    errors.append(f"set {raw_name!r}: entity not found")
                    continue
                schema = s.coverage_map.tables[tid]
                valid_attrs = set(schema.attributes)
                pk_cols = set(schema.primary_key or [])
                for col, raw_val in set_vals.items():
                    if col not in valid_attrs:
                        set_cells["skipped_unknown_col"] += 1
                        continue
                    if col in pk_cols:
                        continue
                    if isinstance(raw_val, list):
                        val = "; ".join(
                            str(v).strip() for v in raw_val if str(v).strip()
                        )
                    elif raw_val is None:
                        val = ""
                    else:
                        val = str(raw_val).strip()
                    if not val:
                        # Empty value = clear the cell: reset it to MISSING
                        # and reject its evidence (kept for audit, not cited).
                        cell_key = s.coverage_map.cell_key(tid, canonical, col)
                        cell = s.coverage_map.cells.get(cell_key)
                        if cell is None or (
                            cell.status == CellStatus.MISSING
                            and not cell.supporting_evidence_ids
                        ):
                            continue
                        rejected_ids = set(cell.supporting_evidence_ids)
                        for node in s.evidence_graph.nodes:
                            if node.id in rejected_ids:
                                node.status = EvidenceStatus.REJECTED
                        cell.status = CellStatus.MISSING
                        cell.supporting_evidence_ids = []
                        cell.best_alignment = ""
                        cell.best_confidence = 0.0
                        cell.best_tier = 1
                        cell.display_hint = ""
                        cell.primary_evidence_id = ""
                        cell.has_conflict = False
                        cell.conflict_evidence_ids = []
                        set_cells["cleared"] += 1
                        continue
                    seed = f"edit_{tid}_{canonical}_{col}_{val}"
                    eid = f"f_edit_{_hashlib.md5(seed.encode()).hexdigest()[:10]}"
                    node = EvidenceNode(
                        id=eid,
                        finding=f"{canonical} {col}: {val}",
                        value=val,
                        source=asserted_source,
                        source_excerpt="",
                        confidence=0.7,
                        entity=canonical,
                        attribute=col,
                        alignment="full",
                        alignment_note="edited by orchestrator",
                        source_authority="aggregator",
                        table_id=tid,
                        created_at=_time.time(),
                    )
                    s.evidence_graph.add_node(node)
                    cell_key = s.coverage_map.cell_key(tid, canonical, col)
                    cell = s.coverage_map.cells.get(cell_key)
                    if cell is not None:
                        if eid not in cell.supporting_evidence_ids:
                            cell.supporting_evidence_ids.append(eid)
                        cell.primary_evidence_id = eid
                        cell.display_hint = val[:120]
                        cell.best_alignment = "full"
                        cell.best_confidence = 0.7
                        cell.best_tier = 2
                        cell.status = CellStatus.FILLED
                        cell.has_conflict = False
                        cell.conflict_evidence_ids = []
                    set_cells["v"] += 1
        return s

    state = _orch_ctx().workspace.atomic_update_state(_apply)
    schema = state.coverage_map.tables[tid]

    parts: list[str] = [f"[{tid}]"]
    if renamed:
        parts.append(f"Renamed {len(renamed)}: {renamed}.")
    if set_cells["v"]:
        parts.append(
            f"Set {set_cells['v']} cell value(s)."
        )
    if set_cells["cleared"]:
        parts.append(
            f"Cleared {set_cells['cleared']} cell(s) (reset to missing)."
        )
    if set_cells["skipped_unknown_col"]:
        parts.append(
            f"Skipped {set_cells['skipped_unknown_col']} unknown column(s)."
        )
    if errors:
        parts.append(f"Errors: {errors}.")
    if not renamed and not set_cells["v"] and not set_cells["cleared"] and not errors:
        parts.append("No changes applied.")
    parts.append(f"Table has {len(schema.entities)} entities.")
    return " ".join(parts)



@tool
async def inspect_table(
    table_id: str = "", status: str = "all", with_values: bool = True,
) -> str:
    """Enumerate a table's rows with their fill state AND current cell
    values — the pull counterpart to the SOCM block, which elides long
    name lists ("… (+N more)") on wide tables. Call this when you need the
    COMPLETE row list for a scope audit, targeted dispatch, or to answer a
    follow-up directly from data already collected.

    Args:
        table_id: table to inspect; empty = the active table.
        status: "filled" | "partial" | "empty" | "all" (default).
            filled = every data column filled; partial = some; empty = none.
        with_values: include a ``values`` map of the current cell values for
            every row with at least one filled cell (default True). Set False
            for a pure scope audit on very wide tables.

    Returns:
        JSON — always complete, never truncated:
        ``{"table_id", "total_rows", "columns": [data cols...],
        "filled": [pk...], "partial": {pk: [missing columns...]},
        "empty": [pk...], "values": {pk: {col: value, ...}, ...}}``
        (only the groups selected by ``status``; ``values`` omitted when
        ``with_values`` is False or ``status`` is "empty").
    """
    if _orch_ctx().workspace is None:
        return json.dumps({"error": "workspace not initialized"})
    if status not in ("filled", "partial", "empty", "all"):
        return json.dumps(
            {"error": "status must be filled|partial|empty|all"})
    state = _orch_ctx().workspace.load_state()
    cmap = state.coverage_map
    tid = (table_id or "").strip() or cmap.primary_table_id
    ts = cmap.tables.get(tid)
    if ts is None:
        return json.dumps({
            "error": f"unknown table_id {tid!r}",
            "available": list(cmap.tables),
        }, ensure_ascii=False)

    pk = set(ts.primary_key or [])
    data_cols = [a for a in ts.attributes if a not in pk]
    filled: list[str] = []
    partial: dict[str, list[str]] = {}
    empty: list[str] = []
    values: dict[str, dict[str, str]] = {}
    for ent in ts.entities:
        cells = {a: cmap.cells.get(cmap.cell_key(tid, ent, a))
                 for a in data_cols}
        # Mirrors the SOCM render: hard_cell (confirmed unreachable)
        # does not count as missing.
        missing = [
            a for a, c in cells.items()
            if c is None or c.status.value not in ("filled", "hard_cell")
        ]
        n_filled = sum(
            1 for c in cells.values()
            if c is not None and c.status.value == "filled"
        )
        # Current value per filled cell (display_hint = best-alignment snippet).
        row_vals = {
            a: c.value for a, c in cells.items()
            if c is not None and c.status.value == "filled" and c.value
        }
        if row_vals:
            values[ent] = row_vals
        if not missing:
            filled.append(ent)
        elif n_filled == 0:
            empty.append(ent)
        else:
            partial[ent] = missing

    out: dict[str, Any] = {
        "table_id": tid, "total_rows": len(ts.entities), "columns": data_cols,
    }
    if status in ("filled", "all"):
        out["filled"] = sorted(filled)
    if status in ("partial", "all"):
        out["partial"] = dict(sorted(partial.items()))
    if status in ("empty", "all"):
        out["empty"] = sorted(empty)
    if with_values and status != "empty":
        # Restrict to rows in the selected groups so `values` stays aligned.
        if status == "all":
            selected = values
        elif status == "filled":
            selected = {k: v for k, v in values.items() if k in set(filled)}
        else:  # partial
            selected = {k: v for k, v in values.items() if k in partial}
        out["values"] = dict(sorted(selected.items()))
    return json.dumps(out, ensure_ascii=False)




def get_schema_tools() -> list:
    """Orchestrator schema + entity surface (paper §Coverage)."""
    return [create_schema, add_entities, remove_entities, edit_entities, inspect_table]
