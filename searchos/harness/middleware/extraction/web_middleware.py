"""网页及 Access Skill 页面抽取。"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from typing import Any

from searchos.harness.middleware.extraction.base import ObservationMiddleware
from searchos.harness.middleware.extraction.core.coordinator import ExtractionCoordinator
from searchos.harness.middleware.extraction.core.models import (
    EvidenceObservation,
    EvidenceSourceKind,
)
from searchos.harness.middleware.extraction.core.preparation import is_extractable_page
from searchos.harness.middleware.models import SourceContext, TaskContext
from searchos.harness.middleware.utils.messages import extract_tool_name
from searchos.socm.planning.strategy import record_source_antipattern

logger = logging.getLogger(__name__)


class WebEvidenceMiddleware(ObservationMiddleware):
    name = "WebEvidenceMiddleware"
    _EXTRACTABLE_TOOLS = {"open", "find", "read_visual"}

    def __init__(
        self,
        coordinator: ExtractionCoordinator,
        *,
        context: TaskContext | None = None,
        source: SourceContext | None = None,
        trajectory_logger: Any = None,
    ) -> None:
        super().__init__(coordinator, context=context)
        self.source = source or SourceContext(workspace=getattr(coordinator, "workspace", None))
        self._workspace = self.source.workspace
        self._trajectory_logger = trajectory_logger

    async def awrap_tool_call(self, request: Any, handler: Callable) -> Any:
        result = await handler(request)
        tool_name = extract_tool_name(request, default="")
        if tool_name in {"local_open", "local_find", "local_catalog", "exec", "read_skill_file", "load_skill", "list_skills"}:
            return result
        artifact = getattr(result, "artifact", None)
        if isinstance(artifact, dict):
            source = artifact.get("page_source", {})
            if isinstance(source, dict) and (source.get("evidence_eligible") is False or source.get("kind") in {"diagnostic", "fixture", "execution_index"}):
                return result
            if artifact.get("input_mode") == "fixture" or artifact.get("fixture") is True:
                return result
            if isinstance(source, dict) and (source.get("input_mode") == "fixture" or source.get("fixture") is True):
                return result
        visible = self._result_content(result)
        header = visible.split("\n\n", 1)[0]
        is_page_view = visible.startswith("[Now viewing]") and bool(
            re.search(r"^URL:\s*(?:https?://|skill://)", header, re.MULTILINE)
        )
        if tool_name not in self._EXTRACTABLE_TOOLS and not is_page_view:
            return result

        extraction_result = result
        if tool_name == "read_visual" and isinstance(getattr(result, "content", None), list):
            from searchos.tools.simple_browser.image_reading import (
                replace_native_image_tool_results,
            )

            extraction_result = (await replace_native_image_tool_results([result]))[0]
        content = self._result_content(extraction_result)
        if len(content) < 50:
            return result
        page_source = self._structured_page_source(extraction_result)
        source_url = page_source.get("source_url") or self._extract_source_url(content)

        from searchos.tools.simple_browser import FETCH_ERROR_SENTINEL

        reason = ""
        if FETCH_ERROR_SENTINEL in content[:200]:
            reason = "fetch_error"
        elif not is_extractable_page(content):
            reason = "unextractable_page"
        if reason:
            self._record_source_skip(source_url or "<unknown>", reason)
            self._log_skip(source_url, reason)
            return result

        return await self._submit(
            EvidenceObservation(
                content=content,
                source_url=source_url,
                source_urls=tuple(page_source.get("source_urls", [])),
                page_id=page_source.get("page_id") or self._extract_page_id(content),
                source_kind=(EvidenceSourceKind.SKILL if page_source.get("kind") == "skill_result" else EvidenceSourceKind.PAGE),
                target_table=self.context.target_table,
                task_id=self.context.task_id,
                task_text=self.context.task_text,
            ),
            result,
        )

    def _record_source_skip(self, source_url: str, reason: str) -> None:
        if self._workspace is None:
            return
        try:
            record_source_antipattern(
                self._workspace,
                source_url,
                reason=reason,
                created_by="extraction",
            )
        except Exception:
            logger.debug("strategy source write failed", exc_info=True)

    def _log_skip(self, source_url: str, reason: str) -> None:
        if self._trajectory_logger:
            self._trajectory_logger._append_raw(
                {
                    "type": "harness",
                    "kind": "extraction_skipped",
                    "reason": reason,
                    "source": source_url[:200],
                }
            )

    @staticmethod
    def _structured_page_source(result: Any) -> dict:
        """只从工具 artifact 取来源身份，不接受正文中的伪造元数据。"""
        artifact = getattr(result, "artifact", None)
        payload = artifact.get("page_source") if isinstance(artifact, dict) else None
        if not isinstance(payload, dict):
            return {}
        url = payload.get("source_url")
        if not isinstance(url, str) or not url.startswith(("http://", "https://", "skill://")):
            return {}
        page_id = payload.get("page_id")
        return {"source_url": url, "page_id": page_id if isinstance(page_id, str) else "",
                "kind": payload.get("kind", ""), "source_urls": payload.get("source_urls", [])}

    @staticmethod
    def _extract_source_url(content: str) -> str:
        match = re.search(r"<Page \d+>[^\n]*?\((https?://\S+)", content)
        if match:
            url = match.group(1)
            while url.endswith(")") and url.count(")") > url.count("("):
                url = url[:-1]
            return url
        match = re.search(r"^URL:\s*((?:https?://|skill://)\S+)", content, re.MULTILINE)
        if match:
            return match.group(1)
        match = re.search(r"https?://\S+", content)
        return match.group(0) if match else ""

    @staticmethod
    def _extract_page_id(content: str) -> str:
        match = re.search(r"^Page ID:\s*([a-f0-9]{12})\s*$", content, re.MULTILINE)
        return match.group(1) if match else ""
