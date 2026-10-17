"""在调用方的原子更新内核验候选行并提交证据与单元格投影。"""

from __future__ import annotations

from typing import Any

from searchos.harness.middleware.extraction.utils.grounding import (
    _NULL_VALUES,
    _anchored_excerpt,
    _ungrounded_number,
)
from searchos.harness.middleware.extraction.utils.unit_normalize import normalize_value
from searchos.socm import TableSchema
from searchos.socm.evidence.values import is_missing_value


def ingest_rows(bundles, table_id, state, *, commit_stats=None):
    """提交保留单元格归属的证据。"""
    return _ingest_rows(bundles, table_id, state, independent=False, commit_stats=commit_stats)


def ingest_facts(bundles, table_id, state, *, commit_stats=None):
    """保留原始观察，提交可跨表投影的独立事实。"""
    return _ingest_rows(bundles, table_id, state, independent=True, commit_stats=commit_stats)


def _ingest_rows(
    bundles: list[tuple],
    tid: str,
    s: Any,
    *,
    independent: bool,
    commit_stats: dict[str, Any] | None = None,
) -> tuple[list[Any], list[dict[str, str]]]:
    """在原子更新中校验行、锚定来源，并提交本批证据。

    bundle 为 (row, page_text, source_url[, mode])。FILL 只能匹配有效行，
    DISCOVER 可创建新行；两者均不能恢复已排除行。返回新增节点和拒绝原因。
    """
    import hashlib
    import uuid

    from searchos.socm import EvidenceNode
    from searchos.socm.coverage import (
        commit_evidence,
        commit_table_facts,
        evidence_source_allowed,
        validate_row,
    )
    from searchos.socm.evidence import SourceObservation
    from searchos.socm.evidence.provenance import select_source_urls
    from searchos.util.span_match import find_span

    cmap = s.coverage_map
    schema = cmap.tables.get(tid)
    if schema is None:
        return [], []
    null_values = _NULL_VALUES
    conf_map = {"high": 0.9, "medium": 0.6, "low": 0.3}
    new_nodes: list[Any] = []
    validation_values: dict[str, Any] = {}
    rejected: list[dict[str, str]] = []
    observations: dict[str, SourceObservation] = {}

    for bundle in bundles:
        row, page_text, source_url = bundle[:3]
        local_source_metadata = bundle[3] if len(bundle) > 4 else None
        mode = bundle[4] if len(bundle) > 4 else bundle[3] if len(bundle) > 3 else "merged"
        original = bundle[5] if len(bundle) > 5 else page_text
        page_id = bundle[6] if len(bundle) > 6 else ""
        source_urls = bundle[7] if len(bundle) > 7 else []
        observed = (
            SourceObservation.capture(
                source_url, original, local_source_metadata, source_urls=source_urls,
            )
            if independent
            else None
        )
        if independent and (
            not source_url.startswith(("http://", "https://", "local://", "skill://", "agent://"))
            or not evidence_source_allowed(
                s,
                EvidenceNode(id="", source=source_url, local_source_metadata=local_source_metadata),
            )
        ):
            rejected.append({"row": "", "column": "", "reason": "source_out_of_scope"})
            continue
        key_vals: dict[str, str] = {}
        ok = True
        for k in schema.primary_key:
            v = str(row.get(k, "")).strip()
            if not v or v.lower() in null_values:
                ok = False
                break
            key_vals[k] = v
        if not ok:
            continue
        raw_entity = TableSchema.make_entity_key(key_vals, schema.primary_key)
        if not raw_entity:
            continue
        # Hard admission rules: any checked column violating drops the row
        violations = validate_row(schema, row)
        if violations:
            rejected.extend({"row": raw_entity, **violation} for violation in violations)
            continue
        # Canonicalize: reuse an existing row if this is a surface variant,
        # else create the row (materializes its MISSING cells).
        entity, row_status = cmap.resolve_row(raw_entity, table_id=tid)
        if row_status == "excluded":
            rejected.append({"row": raw_entity, "column": "", "reason": "excluded_entity"})
            continue
        if entity is None:
            if mode == "fill":
                rejected.append(
                    {
                        "row": raw_entity,
                        "column": "",
                        "reason": "fill_mode_new_row",
                    }
                )
                continue
            if not cmap.add_entity(raw_entity, table_id=tid):
                rejected.append({"row": raw_entity, "column": "", "reason": "unresolved_entity"})
                continue
            entity = cmap.resolve_entity(raw_entity, table_id=tid)

        alignment = str(row.get("_alignment", "full")).strip().lower()
        if alignment not in ("full", "partial", "loose"):
            alignment = "full"
        confidence = conf_map.get(
            str(row.get("_confidence", "high")).strip().lower(),
            0.9,
        )
        source_authority = str(row.get("_source_authority", "unclear")).strip().lower()
        alignment_note = str(row.get("_alignment_note", "")).strip()
        row_excerpt = str(row.get("_source_excerpt", "")).strip()
        page_id = page_id or (
            hashlib.md5(source_url.encode("utf-8")).hexdigest()[:12] if source_url else ""
        )

        for attr in schema.data_columns:
            raw_value = row.get(attr)
            if is_missing_value(raw_value):
                continue
            val = str(raw_value).strip()
            # Factuality gate: the judge's value is required to be verbatim
            # (unit conversion happens below, in code), so its significant
            # numbers must literally occur on the page. Cell-level reject —
            # the row's other cells may still be grounded.
            gate_reason = _ungrounded_number(page_text, val)
            if gate_reason:
                rejected.append(
                    {
                        "row": raw_entity,
                        "column": attr,
                        "reason": gate_reason,
                    }
                )
                continue
            fid = f"f_{uuid.uuid4().hex[:8]}"
            excerpt, span, text_hash = _anchored_excerpt(
                page_text,
                row_excerpt,
                val,
                entity,
                attr,
            )
            # Deterministic unit fix: the judge often copies the verbatim
            # source number into a unit-pinned column without converting
            # (e.g. "$131 billion" -> "131" in a 亿美元 column). The excerpt
            # retains the original wording, so rescale in code.
            cd = (getattr(schema, "column_desc", None) or {}).get(attr)
            col_text = f"{attr} {getattr(cd, 'desc', '')}" if cd else attr
            new_val, unit_note = normalize_value(val, excerpt, col_text)
            cell_note = alignment_note
            if new_val != val:
                val = new_val
                cell_note = (
                    f"{alignment_note}; {unit_note}".strip("; ") if alignment_note else unit_note
                )
            # A cell whose excerpt never anchored to the page has no
            # verifiable provenance — it must not out-vote a grounded
            # value at conflict arbitration, whatever the judge claimed.
            cell_conf = confidence if span is not None else min(confidence, 0.4)
            if observed is not None:
                original_span, _ = find_span(
                    original,
                    excerpt,
                    browser_lines=source_url.startswith(("http://", "https://", "skill://")),
                )
                if span is None or original_span is None:
                    rejected.append(
                        {"row": raw_entity, "column": attr, "reason": "unanchored_source"}
                    )
                    continue
                span = original_span
                excerpt = original[span[0] : span[1]]
                text_hash = "sha1:" + hashlib.sha1(excerpt.encode()).hexdigest()
                observations[observed.id] = observed
            node = EvidenceNode(
                id=fid,
                finding=f"{entity} {attr}: {val}",
                value=val,
                source=source_url,
                source_urls=select_source_urls(
                    source_url, original, excerpt,
                    (row.get("_source_urls", {}).get(attr)
                     if isinstance(row.get("_source_urls"), dict)
                     else row.get("_source_urls")), available=source_urls, state=s,
                ),
                source_excerpt=excerpt,
                local_source_metadata=local_source_metadata,
                confidence=cell_conf,
                entity=entity,
                attribute=attr,
                alignment=alignment,
                alignment_note=cell_note or f"row-level extraction from {source_url}",
                source_authority=source_authority,
                page_id=page_id,
                span=span,
                text_hash=text_hash,
                table_id=tid,
                observation_id=observed.id if observed is not None else "",
            )
            new_nodes.append(node)
            validation_values[fid] = (
                val if new_val != str(row.get(attr, "")).strip() else row.get(attr)
            )

    commit = commit_table_facts if independent else commit_evidence
    result = commit(s, new_nodes, validation_values=validation_values)
    for node in result.nodes:
        if node.observation_id in observations and not any(
            o.id == node.observation_id for o in s.evidence_graph.observations
        ):
            s.evidence_graph.observations.append(observations[node.observation_id])
    rejected.extend(result.rejected)
    if commit_stats is not None:
        commit_stats.update(
            cells_filled=result.cells_filled,
            evidence_links_added=result.associations_added,
            accepted_ids=list(dict.fromkeys(node.id for node in result.nodes)),
        )
    return result.added_nodes, rejected
