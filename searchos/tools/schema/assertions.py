"""Schema 工具共用的运行上下文、单元格值归一与证据写入。"""

from __future__ import annotations

import hashlib
import time
from typing import Any

from searchos.socm.coverage import commit_evidence


def _orch_ctx():
    """Lazy handle on the orchestrator runtime context (bound workspace)."""
    from searchos.agents.runtime import _ctx
    return _ctx


def _cell_value(raw_value: Any) -> str:
    if isinstance(raw_value, list):
        return "; ".join(str(item).strip() for item in raw_value if str(item).strip())
    if raw_value is None:
        return ""
    return str(raw_value).strip()


def _assert_cell_value(
    state: Any,
    *,
    table_id: str,
    entity: str,
    attribute: str,
    value: str,
    source: str,
    evidence_prefix: str,
    alignment_note: str,
    overwrite: bool = False,
    raw_value: Any = None,
    source_excerpt: str = "",
) -> bool:
    """Commit synthetic Evidence and project it into the Coverage Cell.

    ``overwrite`` supersedes the cell's prior evidence before applying the new
    assertion. Normal add assertions remain low-tier evidence and therefore do
    not displace a stronger direct-page value.
    """
    from searchos.socm import EvidenceNode
    from searchos.socm.evidence.provenance import is_original_source

    if overwrite and (not is_original_source(source) or not source_excerpt.strip()):
        return False
    if (state.source_scope or {}).get("mode") == "hybrid" and source.startswith("agent://"):
        return False

    cell_key = state.coverage_map.cell_key(table_id, entity, attribute)
    cell = state.coverage_map.cells.get(cell_key)
    if cell is None or not value:
        return False

    seed = f"{evidence_prefix}_{table_id}_{entity}_{attribute}_{value}"
    if not source.startswith("agent://"):
        seed += f"_{source}"
    evidence_id = f"f_{evidence_prefix}_{hashlib.md5(seed.encode()).hexdigest()[:10]}"

    node = EvidenceNode(
        id=evidence_id,
        finding=f"{entity} {attribute}: {value}",
        value=value, source=source, source_excerpt=source_excerpt, confidence=0.7,
        entity=entity, attribute=attribute, alignment="full",
        alignment_note=alignment_note,
        source_authority="aggregator" if source.startswith("agent://") else "unclear",
        table_id=table_id, created_at=time.time(),
    )
    values = {node.id: raw_value} if raw_value is not None else None
    return bool(commit_evidence(
        state, [node], overwrite=overwrite, validation_values=values,
    ).nodes)
