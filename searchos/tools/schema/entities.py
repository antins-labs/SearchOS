"""添加、软删除和编辑实体行，保留行身份、证据及审计记录。"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.tools import tool

from searchos.socm.coverage import clear_cell_evidence, refresh_cells, validate_row
from searchos.util.coerce import coerce_str_list as _coerce_str_list

from . import assertions


def _resolve_attribute_entity(cmap: Any, table_id: str, raw_key: str) -> str | None:
    """Resolve an attributes_json key, accepting the common comma form for
    composite PKs in addition to the canonical ``|`` representation."""
    canonical = cmap.resolve_entity(raw_key, table_id=table_id)
    if canonical is not None:
        return canonical
    primary_key = cmap.tables[table_id].primary_key or []
    if len(primary_key) <= 1 or "|" in raw_key:
        return None
    parts = [part.strip() for part in raw_key.split(",")]
    if len(parts) != len(primary_key) or not all(parts):
        return None
    return cmap.resolve_entity("|".join(parts), table_id=table_id)


def _normalize_add_entity_rows(
    rows: list[Any],
    *,
    table_id: str,
    schema: Any,
    explicit_asserted: dict[str, dict[str, Any]],
) -> tuple[list[str], dict[str, dict[str, Any]], str | None]:
    """Normalize add_entities input to canonical row keys + inline attrs.

    ``add_entities`` historically accepted only primary-key values. Extraction,
    however, works with row objects. To keep those contracts aligned without
    silently stringifying dictionaries, accept both forms here:

    - scalar/list values become row keys;
    - dict values are treated like extraction rows: primary_key columns define
      the row key, and non-PK schema columns become inline assertions.
    """
    from searchos.socm import TableSchema

    primary_key = list(schema.primary_key or [])
    data_columns = [a for a in schema.attributes if a not in set(primary_key)]
    normalized: list[str] = []
    asserted: dict[str, dict[str, Any]] = {}

    for idx, row in enumerate(rows):
        if isinstance(row, dict):
            if not primary_key:
                return [], {}, (
                    f"Error: entities_json[{idx}] is an object, but table "
                    f"{table_id!r} has no primary_key. Pass row-key strings "
                    "instead."
                )
            key_vals: dict[str, str] = {}
            missing_pk: list[str] = []
            for key in primary_key:
                val = assertions._cell_value(row.get(key))
                if not val or val.lower() in {"null", "none", "n/a"}:
                    missing_pk.append(key)
                else:
                    key_vals[key] = val
            if missing_pk:
                return [], {}, (
                    f"Error: entities_json[{idx}] row object missing primary "
                    f"key value(s) {missing_pk}. Row objects must include "
                    "every primary_key column."
                )
            name = TableSchema.make_entity_key(key_vals, primary_key)
            if not name:
                continue
            normalized.append(name)
            inline = {
                col: row[col]
                for col in data_columns
                if col in row and assertions._cell_value(row.get(col))
            }
            if inline:
                asserted.setdefault(name, {}).update(inline)
            continue

        if isinstance(row, (list, tuple)):
            if primary_key and len(row) != len(primary_key):
                return [], {}, (
                    f"Error: entities_json[{idx}] has {len(row)} key value(s) "
                    f"but table {table_id!r} primary_key has "
                    f"{len(primary_key)} column(s). Pass exactly the primary "
                    "key values, or use a row object with primary_key fields."
                )
            name = "|".join(str(v).strip() for v in row)
        else:
            name = str(row).strip()
        if name:
            normalized.append(name)

    # Explicit attributes_json wins over attributes carried inline in row
    # objects; it is the more intentional input channel.
    for pk, cols in explicit_asserted.items():
        asserted.setdefault(pk, {}).update(cols)

    return normalized, asserted, None


@tool
async def add_entities(
    entities_json: str,
    table_id: str = "",
    attributes_json: str = "",
) -> str:
    """Add entity rows using stable primary keys. Dispatch source-reading
    tasks to collect missing facts, with target_table to focus extraction.

    Args:
        entities_json: JSON array of row keys to add (duplicates are
            silently skipped), or row objects whose primary_key columns define
            the row key. Examples: '["MIT","Stanford","ETH Zurich"]',
            '[[2025,"MIT"],[2025,"Stanford"]]', or
            '[{"Ranking":1,"Name":"IShowSpeed"}]'. Row-object non-PK
            values are treated like attributes_json inline assertions.
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
            Composite PK keys use ``"part1|part2"``; the common
            ``"part1,part2"`` form is also accepted when unambiguous.
    """
    if assertions._orch_ctx().workspace is None:
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

    state = assertions._orch_ctx().workspace.load_state()
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
    normalized_entities, asserted, normalize_error = _normalize_add_entity_rows(
        new_entities,
        table_id=tid,
        schema=cmap.tables[tid],
        explicit_asserted=asserted,
    )
    if normalize_error:
        return normalize_error
    if not normalized_entities:
        return "Error: entities_json did not contain any non-empty row keys"

    added: list[str] = []
    skipped: list[str] = []
    revived: list[str] = []
    rejected_rows: list[str] = []
    asserted_cells = {"v": 0, "skipped_unknown_col": 0, "unknown_entity": 0, "rejected": 0}

    def _apply(s: Any) -> Any:
        schema = s.coverage_map.tables[tid]
        valid_assertions: dict[str, dict[str, Any]] = {}
        rejected_names: set[str] = set()
        for raw_name, values in asserted.items():
            violations = validate_row(schema, values)
            if violations:
                rejected_names.add(raw_name)
                rejected_rows.append(f"{raw_name}: {violations[0]['reason']}")
            else:
                valid_assertions[raw_name] = values
        for name in normalized_entities:
            if s.coverage_map._resolve_name(name, list(rejected_names), schema.entity_aliases):
                continue
            parts = name.split("|") if len(schema.primary_key) > 1 else [name]
            pk_values = dict(zip(schema.primary_key, parts))
            violations = validate_row(schema, pk_values)
            if violations:
                rejected_rows.append(f"{name}: {violations[0]['reason']}")
                continue
            # 此前被 remove_entities 排除的行：orchestrator 显式重加 = 复活
            if s.coverage_map.is_removed_entity(name, table_id=tid):
                if s.coverage_map.restore_entity(name, table_id=tid):
                    canonical = s.coverage_map.resolve_entity(name, table_id=tid)
                    revived.append(canonical)
                    refresh_cells(s, {
                        s.coverage_map.cell_key(tid, canonical, attr)
                        for attr in s.coverage_map.tables[tid].attributes
                    })
                continue
            if s.coverage_map.add_entity(name, table_id=tid):
                added.append(name)
            else:
                skipped.append(name)

        schema = s.coverage_map.tables[tid]
        valid_attrs = set(schema.attributes)
        pk_cols = set(schema.primary_key or [])
        for pk_value, col_vals in valid_assertions.items():
            canonical = _resolve_attribute_entity(s.coverage_map, tid, pk_value)
            if canonical is None:
                asserted_cells["unknown_entity"] += 1
                continue
            for col, raw_val in col_vals.items():
                if col not in valid_attrs:
                    asserted_cells["skipped_unknown_col"] += 1
                    continue
                if col in pk_cols:
                    continue
                val = assertions._cell_value(raw_val)
                if not val:
                    continue
                if assertions._assert_cell_value(
                    s,
                    table_id=tid,
                    entity=canonical,
                    attribute=col,
                    value=val,
                    source="agent://orchestrator/asserted",
                    evidence_prefix="assert",
                    alignment_note="asserted by orchestrator from sub-agent summary",
                    raw_value=raw_val,
                ):
                    asserted_cells["v"] += 1
                else:
                    asserted_cells["rejected"] += 1
        return s

    state = assertions._orch_ctx().workspace.atomic_update_state(_apply)
    schema = state.coverage_map.tables[tid]
    asserted_msg = ""
    if (state.source_scope or {}).get("mode") == "hybrid" and asserted_cells["rejected"]:
        asserted_msg = (
            " Structure-only operation: inline values were NOT written. "
            'Read relevant original sources; Extraction automatically fills the existing schema. '
            "Dispatch a focused source-reading task for missing facts; do not retry attributes_json."
        )
    elif any(asserted_cells.values()):
        asserted_msg = (
            f" Asserted {asserted_cells['v']} cell value(s) from inline attributes"
            + (f" (skipped {asserted_cells['skipped_unknown_col']} unknown columns)"
               if asserted_cells["skipped_unknown_col"] else "")
            + (f" (skipped {asserted_cells['unknown_entity']} unknown PK rows)"
               if asserted_cells["unknown_entity"] else "")
            + (f" (rejected {asserted_cells['rejected']} invalid or inactive assertions)"
               if asserted_cells["rejected"] else "")
            + "."
        )
    revived_msg = f" Revived {len(revived)} previously-removed row(s)." if revived else ""
    rejected_msg = f" Rejected {len(rejected_rows)} row(s): {rejected_rows}." if rejected_rows else ""
    return (
        f"[{tid}] Added {len(added)}, skipped {len(skipped)} duplicates."
        f"{revived_msg}{asserted_msg}{rejected_msg} "
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
    if assertions._orch_ctx().workspace is None:
        return "Error: workspace not initialized"
    if not reason.strip():
        return "Error: reason is required — cite the evidence that excludes these rows"
    names = _coerce_str_list(entities_json)
    if not names:
        return "Error: entities_json must be a non-empty JSON array"

    state = assertions._orch_ctx().workspace.load_state()
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

        assertions._orch_ctx().workspace.atomic_update_state(_apply)
        tlog = getattr(assertions._orch_ctx(), "trajectory_logger", None)
        if tlog:
            tlog._append_raw({
                "type": "harness",
                "kind": "entities_removed",
                "table_id": tid,
                "entities": removed,
                "reason": reason[:300],
            })

    state = assertions._orch_ctx().workspace.load_state()
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
    """Edit existing rows. Every non-empty set value MUST include its original
    http/https/local source and supporting source_excerpt in the same edit object.
    Read these with read_evidence first; for skill/agent evidence use source_urls.
    Never cite skill://, agent:// or edit:// as the original. Formatting changes
    must preserve meaning and attribution; use separate items for different sources.

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
            - ``source``: original http/https or local URL supporting the set values.
              Required for every non-empty set in all source modes; not needed for
              a pure rename or clear. Use the original inputs for calculations.
            - ``source_excerpt``: required supporting source text for non-empty sets;
              for a calculation, identify the original text supporting the
              inputs. Do not present calculated values as verbatim source quotes.
              Source fields apply to all set values in this item; use separate
              items when sources differ.
            Example: '[{"entity": "Apolo 11", "rename": "Apollo 11"}]'
        table_id: Target table id. Required in multi-table schemas.
    """
    if assertions._orch_ctx().workspace is None:
        return "Error: workspace not initialized"
    try:
        edits = json.loads(edits_json)
    except json.JSONDecodeError as e:
        return f"Error: invalid JSON — {e}"
    if not isinstance(edits, list) or not edits:
        return "Error: edits_json must be a non-empty JSON array"

    state = assertions._orch_ctx().workspace.load_state()
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

    renamed: list[str] = []
    set_cells = {"v": 0, "cleared": 0, "skipped_unknown_col": 0}
    errors: list[str] = []

    def _apply(s: Any) -> Any:
        for item in edits:
            if not isinstance(item, dict) or "entity" not in item:
                errors.append("each edit must be an object with 'entity' key")
                continue
            raw_name = str(item["entity"]).strip()
            new_name = str(item.get("rename", "")).strip() or None
            set_vals = item.get("set")
            source = item.get("source", "")
            excerpt = item.get("source_excerpt", "")
            if not isinstance(source, str) or not isinstance(excerpt, str):
                errors.append(f"set {raw_name!r}: source and source_excerpt must be strings")
                continue
            source = source.strip()
            if source:
                from urllib.parse import urlsplit
                try:
                    parsed = urlsplit(source)
                    valid_source = parsed.scheme in {"http", "https", "local"} and bool(parsed.netloc)
                except ValueError:
                    valid_source = False
                if not valid_source:
                    errors.append(f"set {raw_name!r}: source must be an original http/https or local URL; use read_evidence.source_urls for skill/agent observations")
                    continue

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
                        s.evidence_graph.invalidate_index()
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
                    val = assertions._cell_value(raw_val)
                    if not val:
                        if clear_cell_evidence(
                            s,
                            table_id=tid,
                            entity=canonical,
                            attribute=col,
                        ):
                            set_cells["cleared"] += 1
                        continue
                    if assertions._assert_cell_value(
                        s,
                        table_id=tid,
                        entity=canonical,
                        attribute=col,
                        value=val,
                        source=source or "agent://orchestrator/edit",
                        evidence_prefix="edit",
                        alignment_note="edited by orchestrator",
                        overwrite=True,
                        raw_value=raw_val,
                        source_excerpt=excerpt,
                    ):
                        set_cells["v"] += 1
                    else:
                        reason = (
                            "provide original source and source_excerpt for every non-empty set; "
                            "use read_evidence.source_urls for skill/agent observations; "
                            "check source scope and column constraints"
                        )
                        errors.append(f"set {canonical!r}.{col}: {reason}")
        return s

    state = assertions._orch_ctx().workspace.atomic_update_state(_apply)
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
