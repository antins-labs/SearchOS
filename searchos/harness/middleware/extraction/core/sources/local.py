"""本地来源身份、版本、定位核验和观测构造。"""

from __future__ import annotations

import json
import re
from typing import Any

from searchos.harness.middleware.extraction.core.models import (
    EvidenceObservation,
    EvidenceSourceKind,
)
from searchos.harness.middleware.models import TaskContext


def extract_source_url(content: str) -> str:
    header = content.split("\n\n", 1)[0]
    match = re.search(r"^Source:\s*(local://\S+)", header, re.MULTILINE)
    return match.group(1) if match else ""


def canonical_local_source(source_url, metadata, source_scope):
    from searchos.local.index.source_registry import SourceRecord
    from searchos.local.reader.references import build_ref_id, parse_ref_id, resolve_reference

    scope = source_scope
    if not scope:
        return source_url, metadata
    ref = parse_ref_id(source_url)
    raw_record = next(
        (r for r in scope.get("documents", []) if r["document_id"] == ref.document_id), None
    )
    if raw_record is None:
        raise ValueError("Local observation is outside the current source scope")
    record = SourceRecord.model_validate(raw_record)
    resolved = resolve_reference(
        ref,
        record.references,
        library_id=record.library_id,
        source_revision=record.source_revision,
    )
    canonical = build_ref_id(
        library_id=record.library_id,
        document_id=record.document_id,
        source_revision=record.source_revision,
        locators=list(resolved.locators),
    )
    return canonical, {
        **(metadata or {}),
        "tool_ref_id": source_url,
        "file_name": record.relative_path,
        "library_id": record.library_id,
        "document_id": record.document_id,
        "locators": [loc.model_dump() for loc in resolved.locators],
    }


def extract_local_source_metadata(
    content: str,
    source_url: str,
) -> dict[str, Any] | None:
    # Tool-owned headers precede the first blank line. Source text cannot
    # inject trusted metadata by containing a similar-looking line.
    header = content.split("\n\n", 1)[0]
    for line in header.splitlines():
        if not line.startswith("Metadata: "):
            continue
        try:
            payload = json.loads(line.removeprefix("Metadata: "))
        except json.JSONDecodeError:
            return None
        if isinstance(payload, dict) and payload.get("ref_id", source_url) == source_url:
            metadata = {**payload, "ref_id": source_url}
            window = re.search(r"^Characters: \[(\d+), (\d+)\)", header, re.MULTILINE)
            if window and "text_range" not in metadata:
                metadata["text_range"] = {
                    "start": int(window.group(1)),
                    "end": int(window.group(2)),
                }
            return metadata
    return None


def structured_local_source_metadata(
    result: Any,
    source_url: str,
) -> dict[str, Any] | None:
    artifact = getattr(result, "artifact", None)
    if not isinstance(artifact, dict):
        return None
    payload = artifact.get("local_source_metadata")
    if isinstance(payload, dict) and payload.get("ref_id") == source_url:
        return payload
    return None


def build_observation(
    result: Any, content: str, context: TaskContext, source_scope: dict
) -> EvidenceObservation | None:
    if len(content) < 50 or "[LOCAL_SOURCE]" not in content:
        return None
    source_url = extract_source_url(content)
    if not source_url:
        return None
    metadata = structured_local_source_metadata(
        result, source_url
    ) or extract_local_source_metadata(content, source_url)
    source_url, metadata = canonical_local_source(source_url, metadata, source_scope)
    return EvidenceObservation(
        content=content,
        source_url=source_url,
        source_kind=EvidenceSourceKind.LOCAL_DOCUMENT,
        target_table=context.target_table,
        task_id=context.task_id,
        task_text=context.task_text,
        local_source_metadata=metadata,
    )
