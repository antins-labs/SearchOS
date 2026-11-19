"""表格候选的原文支持核验、摘录定位与原子提交。"""

from __future__ import annotations

import json
import re
from typing import Any

from searchos.harness.middleware.extraction.core.tables.units import normalize_value
from searchos.socm import TableSchema
from searchos.socm.evidence.missing_values import (
    _NULL_VALUES,
    is_missing_value,
    normalize_pk_field,
)
from searchos.socm.evidence.provenance import source_refs


def _provenance_fields(page_text: str, snippet: str) -> tuple[tuple[int, int] | None, str]:
    """Return (anchored span of snippet in page_text, sha1 text_hash).
    Tolerant matching — _extract_context collapses whitespace and judge
    excerpts arrive reflowed, so a raw find() never anchored in practice."""
    import hashlib

    from searchos.socm.evidence.provenance import find_span

    if not snippet:
        return None, ""
    text_hash = f"sha1:{hashlib.sha1(snippet.encode('utf-8')).hexdigest()}"
    if not page_text:
        return None, text_hash
    span, _tier = find_span(page_text, snippet)
    return span, text_hash


def _anchored_excerpt(
    page_text: str,
    llm_excerpt: str,
    value: str,
    entity: str,
    attribute: str = "",
) -> tuple[str, tuple[int, int] | None, str]:
    """Excerpt to persist: the LLM-provided one if it anchors, else the
    harness-extracted context window when THAT anchors (LLM copies reflow
    or paraphrase too far to recover)."""
    excerpt = llm_excerpt or _extract_context(page_text, value, entity, attribute)
    span, text_hash = _provenance_fields(page_text, excerpt)
    if span is None and llm_excerpt:
        ctx = _extract_context(page_text, value, entity, attribute)
        if ctx:
            ctx_span, ctx_hash = _provenance_fields(page_text, ctx)
            if ctx_span is not None:
                return ctx, ctx_span, ctx_hash
    return excerpt, span, text_hash


def _fold_digits(s: str) -> str:
    """NFKC-fold and strip thousand separators so page and value numbers
    compare on digits alone ("673,622,371" == "673622371", full-width too)."""
    import unicodedata

    s = unicodedata.normalize("NFKC", s or "")
    return s.replace(",", "").replace("，", "")


def _ungrounded_number(page_text: str, value: str) -> str | None:
    """Reason string when a value's significant numbers are nowhere on the page.

    The zh_016 failure mode — one templated price ("全价票100元/人") stamped
    onto dozens of rows whose cited page is a name-list with no prices —
    satisfies every prompt-side rule but cannot satisfy this one. Only tokens
    of >=3 digits are checked: short tokens (day-of-month, list indexes,
    "3.5" split by the decimal point) false-positive; the observed
    fabrications are prices / counts / amounts. Values without such tokens
    pass (textual cells are governed by the excerpt rules instead)."""
    # 地址中的日期和 ID 由完整 URL 检查负责，不要求正文重述路径中的数字。
    for ref in source_refs(value):
        value = value.replace(ref, "")
    tokens = [t for t in re.findall(r"\d+", _fold_digits(value)) if len(t) >= 3]
    if not tokens:
        return None
    page = _fold_digits(page_text)
    missing = [t for t in tokens if t not in page]
    if missing:
        return "number_not_on_page:" + ",".join(missing[:3])
    return None


def _ungrounded_url(
    page_text: str, value: str, source_url: str, *, source_urls=(),
) -> str | None:
    """只接受观测中完整出现的地址；域名、路径前缀不能证明目标 URL。

    观测自身地址和工具执行层声明的来源链接也可支持地址值。此检查只验证
    地址存在，不证明目标页已被阅读或支持陈述，也不改变证据的 source。
    """
    allowed = {*source_refs(page_text), source_url, *source_urls}
    missing = [ref for ref in source_refs(value) if ref not in allowed]
    if missing:
        return "url_not_on_page:" + ",".join(missing[:3])
    return None


def _extract_context(
    page_text: str,
    value: str,
    entity: str,
    attribute: str = "",
    window: int = 120,
) -> str:
    """Return a short text window around the fact for offline verification.

    The window centers on the value occurrence NEAREST an entity mention, not
    the first one on the page: short generic values ("5A", "朝阳区",
    "9:00-18:00") recur across a page, and the first hit is routinely another
    entity's statement."""
    if not page_text:
        return ""
    haystack = page_text

    def _positions(needle: str) -> list[int]:
        if not needle or len(needle) < 2:
            return []
        pos = [m.start() for m in re.finditer(re.escape(needle), haystack)]
        if pos:
            return pos
        lowered = haystack.lower()
        return [m.start() for m in re.finditer(re.escape(needle.lower()), lowered)]

    def _window_at(idx: int, length: int) -> str:
        start = max(0, idx - window)
        end = min(len(haystack), idx + length + window)
        return " ".join(haystack[start:end].split())

    # Scraped pages carry a "Title: … URL Source: … Markdown Content:"
    # preamble; anything worth quoting is restated in the body, and viewers
    # strip the preamble — so prefer body occurrences when any exist.
    m = re.search(r"Markdown Content:\s*", haystack)
    body_start = m.end() if m else 0

    def _prefer_body(pos: list[int]) -> list[int]:
        body = [p for p in pos if p >= body_start]
        return body or pos

    val_pos = _prefer_body(_positions(value))
    ent_pos = _prefer_body(_positions(entity))
    if val_pos and ent_pos:
        idx = min(val_pos, key=lambda v: min(abs(v - e) for e in ent_pos))
        return _window_at(idx, len(value))
    if val_pos:
        return _window_at(val_pos[0], len(value))
    if ent_pos:
        return _window_at(ent_pos[0], len(entity))
    return ""


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

    from searchos.socm import EvidenceNode, EvidenceStatus
    from searchos.socm.coverage import (
        commit_evidence,
        commit_table_facts,
        evidence_source_allowed,
        validate_row,
    )
    from searchos.socm.coverage.projection import cell_source_error
    from searchos.socm.evidence import SourceObservation
    from searchos.socm.evidence.provenance import find_span, select_source_urls

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
    candidate_observations: set[str] = set()

    for bundle in bundles:
        row, page_text, source_url = bundle[:3]
        local_source_metadata = bundle[3] if len(bundle) > 4 else None
        mode = bundle[4] if len(bundle) > 4 else bundle[3] if len(bundle) > 3 else "merged"
        original = bundle[5] if len(bundle) > 5 else page_text
        page_id = bundle[6] if len(bundle) > 6 else ""
        source_urls = bundle[7] if len(bundle) > 7 else []
        referring_page = bundle[8] if len(bundle) > 8 else None
        observed = (
            SourceObservation.capture(
                source_url, original, local_source_metadata, source_urls=source_urls,
                referring_page=referring_page,
            )
            if independent or referring_page
            else None
        )
        supported_source = source_url.startswith(("http://", "https://", "local://", "skill://", "agent://"))
        if (independent and not supported_source) or not evidence_source_allowed(
            s, EvidenceNode(id="", source=source_url, local_source_metadata=local_source_metadata)
        ):
            rejected.append({"row": "", "column": "", "reason": "source_out_of_scope"})
            continue
        key_vals: dict[str, str] = {
            k: normalize_pk_field(row.get(k)) for k in schema.primary_key
        }
        # Composite PK: not-all-null. Missing fields normalize to "/".
        if not key_vals or all(v == "/" for v in key_vals.values()):
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
        if entity == raw_entity and cmap.primary_key_values(entity, table_id=tid) != key_vals:
            rejected.append({"row": raw_entity, "column": "", "reason": "primary_key_fields_mismatch"})
            continue
        if row_status == "excluded":
            rejected.append({"row": raw_entity, "column": "", "reason": "excluded_entity"})
            continue
        # An active resolve is the same row. Discover must reuse it (no second
        # entity) and may still commit newly supported attributes.
        new_entity = entity is None and not (mode == "discover" and row_status == "active")
        if new_entity:
            if mode == "fill":
                rejected.append(
                    {
                        "row": raw_entity,
                        "column": "",
                        "reason": "fill_mode_new_row",
                    }
                )
                continue
            entity = raw_entity

        alignments = row.get("_alignment", "full")
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

        row_start = len(new_nodes)
        for identity_only in (False, True):
            columns = [attr for attr in schema.data_columns if not is_missing_value(row.get(attr))]
            if identity_only:
                if not new_entity or len(new_nodes) > row_start:
                    break
                # 属性尚未通过时，用原文独立核验身份，保留可继续补充的行。
                columns = schema.primary_key
                if not row_excerpt and len(columns) == 1:
                    row_excerpt = key_vals[columns[0]]
                # Identity anchoring only requires non-placeholder PK values in the excerpt.
                anchored_vals = [v for v in key_vals.values() if v.lower() not in null_values]
                if (find_span(original, row_excerpt, browser_lines=True)[0] is None
                        or not all(
                            find_span(row_excerpt, value)[0] is not None for value in anchored_vals
                        )):
                    rejected.append({"row": raw_entity, "column": "", "reason": "unanchored_row_identity"})
                    break
            for attr in columns:
                alignment = "full" if identity_only else str(
                    alignments.get(attr, "partial") if isinstance(alignments, dict) else alignments
                ).strip().lower()
                if alignment not in ("full", "partial", "loose"):
                    alignment = "partial"
                raw_value = row.get(attr)
                val = str(raw_value).strip()
                # 数字与地址继续按原文校验，失败只排除当前属性。
                url_value = raw_value if isinstance(raw_value, str) else json.dumps(raw_value)
                gate_reason = _ungrounded_url(
                    original, url_value, source_url, source_urls=source_urls,
                ) or _ungrounded_number(page_text, val)
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
                cd = (getattr(schema, "column_desc", None) or {}).get(attr)
                col_text = f"{attr} {getattr(cd, 'desc', '')}" if cd else attr
                new_val, unit_note = (val, "") if identity_only else normalize_value(val, excerpt, col_text)
                cell_note = alignment_note
                if new_val != val:
                    val = new_val
                    cell_note = (
                        f"{alignment_note}; {unit_note}".strip("; ") if alignment_note else unit_note
                    )
                cell_conf = confidence if span is not None else min(confidence, 0.4)
                if observed is not None:
                    original_span, _ = find_span(
                        original,
                        excerpt,
                        browser_lines=source_url.startswith(("http://", "https://", "skill://")),
                    )
                    # Span is optional highlight metadata: prefer original-page
                    # coordinates when available, but do not drop the cell solely
                    # because anchoring failed.
                    if original_span is not None:
                        span = original_span
                        excerpt = original[span[0] : span[1]]
                        text_hash = "sha1:" + hashlib.sha1(excerpt.encode()).hexdigest()
                        cell_conf = confidence
                    else:
                        cell_conf = min(cell_conf, 0.4)
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
                        referring_url=referring_page[0] if referring_page else "",
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
                # Keep number/url/excerpt gates; span absence alone is not a hard reject.
                source_error = cell_source_error(s, node)
                if source_error or alignment != "full":
                    node.status = EvidenceStatus.CANDIDATE
                    durable, _ = s.evidence_graph.get_or_add(node)
                    candidate_observations.add(durable.observation_id)
                    rejected.append({
                        "row": raw_entity, "column": attr, "candidate_id": durable.id,
                        "reason": source_error or "source_incompletely_matches_target",
                    })
                    continue
                new_nodes.append(node)
                validation_values[fid] = (
                    val if new_val != str(row.get(attr, "")).strip() else row.get(attr)
                )
            if identity_only and len(new_nodes) - row_start != len(columns):
                del new_nodes[row_start:]
        if new_entity and len(new_nodes) > row_start:
            cmap.add_entity(raw_entity, table_id=tid, key_values=key_vals)

    commit = commit_table_facts if independent else commit_evidence
    result = commit(s, new_nodes, validation_values=validation_values)
    for observation_id in candidate_observations.union(n.observation_id for n in result.nodes):
        if observation_id in observations and not any(
            o.id == observation_id for o in s.evidence_graph.observations
        ):
            s.evidence_graph.observations.append(observations[observation_id])
    rejected.extend(result.rejected)
    if commit_stats is not None:
        commit_stats.update(
            cells_filled=result.cells_filled,
            evidence_links_added=result.associations_added,
            accepted_ids=list(dict.fromkeys(node.id for node in result.nodes)),
        )
    return result.added_nodes, rejected
