"""本地原文窗口抽取与来源定位校验。"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any

from searchos.harness.middleware.extraction.base import ObservationMiddleware
from searchos.harness.middleware.extraction.core.coordinator import ExtractionCoordinator
from searchos.harness.middleware.extraction.core.models import (
    EvidenceObservation,
    EvidenceSourceKind,
)
from searchos.harness.middleware.models import SourceContext, TaskContext
from searchos.harness.middleware.utils.messages import extract_tool_name


class LocalEvidenceMiddleware(ObservationMiddleware):
    name = "LocalEvidenceMiddleware"

    def __init__(
        self,
        coordinator: ExtractionCoordinator,
        *,
        context: TaskContext | None = None,
        source: SourceContext | None = None,
    ) -> None:
        super().__init__(coordinator, context=context)
        self.source = source or SourceContext()
        self.source_scope = self.source.scope

    async def awrap_tool_call(self, request: Any, handler: Callable) -> Any:
        result = await handler(request)
        if extract_tool_name(request, default="") != "local_open":
            return result
        content = self._result_content(result)
        if len(content) < 50 or "[LOCAL_SOURCE]" not in content:
            return result
        source_url = self._extract_source_url(content)
        if not source_url:
            return result
        metadata = self._structured_local_source_metadata(
            result,
            source_url,
        ) or self._extract_local_source_metadata(content, source_url)
        source_url, metadata = self._canonical_local_source(source_url, metadata)
        return await self._submit(
            EvidenceObservation(
                content=content,
                source_url=source_url,
                source_kind=EvidenceSourceKind.LOCAL_DOCUMENT,
                target_table=self.context.target_table,
                task_id=self.context.task_id,
                task_text=self.context.task_text,
                local_source_metadata=metadata,
            ),
            result,
        )

    @staticmethod
    def _extract_source_url(content: str) -> str:
        header = content.split("\n\n", 1)[0]
        match = re.search(r"^Source:\s*(local://\S+)", header, re.MULTILINE)
        return match.group(1) if match else ""

    def _canonical_local_source(self, source_url, metadata):
        from searchos.local.index.source_registry import SourceRecord
        from searchos.local.reader.references import build_ref_id, parse_ref_id, resolve_reference

        scope = self.source_scope
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

    @staticmethod
    def _extract_local_source_metadata(
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
            if isinstance(payload, dict) and payload.get("ref_id") == source_url:
                return payload
        return None

    @staticmethod
    def _structured_local_source_metadata(
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
