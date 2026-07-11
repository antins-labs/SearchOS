"""LangChain Agent Middleware 到 Evidence Intake 的薄 Adapter。"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable
from typing import Any

from langchain.agents.middleware.types import AgentMiddleware

from searchos.harness.middleware._shared import extract_tool_name, unwrap_ai_message
from searchos.harness.middleware.extraction.context import render_skill_context
from searchos.harness.middleware.extraction.intake import (
    DeliveryMode,
    EvidenceIntake,
    EvidenceObservation,
    EvidenceSourceKind,
    WorkspaceEvidenceStore,
)
from searchos.harness.middleware.extraction.intake._engine import (
    _anchored_excerpt,
    _extract_context,
    _fold_digits,
    _provenance_fields,
    _ungrounded_number,
)
from searchos.socm.strategy import record_source_antipattern

logger = logging.getLogger(__name__)


class EvidenceExtractionMiddleware(AgentMiddleware):
    """把 Agent 生命周期事件适配为 Evidence Observation。"""

    name: str = "EvidenceExtractionMiddleware"
    _EXTRACTABLE_TOOLS = {"open", "find"}

    def __init__(
        self,
        judge_model: Any,
        workspace: Any,
        trajectory_logger: Any = None,
        batch_n: int = 5,
        alias_resolver_model: Any = None,
    ) -> None:
        self._workspace = workspace
        self._trajectory_logger = trajectory_logger
        self.intake = EvidenceIntake(
            judge_model=judge_model,
            alias_resolver_model=alias_resolver_model,
            store=WorkspaceEvidenceStore(workspace),
            trajectory_logger=trajectory_logger,
            batch_n=batch_n,
        )

    @property
    def committed_node_ids(self) -> frozenset[str]:
        return self.intake.committed_node_ids

    async def await_pending_flushes(self, timeout: float = 5.0) -> int:
        return await self.intake.await_idle(timeout=timeout)

    async def finalize(self, *, timeout: float = 30.0) -> Any:
        return await self.intake.finalize(timeout=timeout)

    async def awrap_tool_call(self, request: Any, handler: Callable) -> Any:
        result = await handler(request)
        tool_name = extract_tool_name(request, default="")
        is_skill = tool_name.startswith("skill_")
        if tool_name not in self._EXTRACTABLE_TOOLS and not is_skill:
            return result

        content = self._result_content(result)
        if len(content) < 50:
            return result
        state = self._workspace.load_state()
        if not state.coverage_map.table_schema.attributes:
            return result

        if is_skill:
            prepared = self._skill_observation(content, tool_name)
            if prepared is None:
                return result
            content, source_url = prepared
            source_kind = EvidenceSourceKind.SKILL
            delivery = DeliveryMode.SYNC
        else:
            from searchos.tools.simple_browser import FETCH_ERROR_SENTINEL

            source_url = self._extract_source_url(content)
            if FETCH_ERROR_SENTINEL in content[:200]:
                self._record_source_skip(source_url or "<unknown>", "fetch_error")
                self._log_skip(source_url, "fetch_error")
                return result
            if tool_name == "find" and source_url:
                source_url = source_url.split("/find?")[0]
            if not EvidenceIntake._is_extractable_page(content):
                self._record_source_skip(source_url, "unextractable_page")
                self._log_skip(source_url, "unextractable_page")
                return result
            source_kind = EvidenceSourceKind.PAGE
            delivery = DeliveryMode.BUFFERED

        receipt = await self.intake.submit(
            EvidenceObservation(
                content=content,
                source_url=source_url,
                source_kind=source_kind,
                target_table=self._current_table(),
            ),
            delivery=delivery,
        )
        if receipt.duplicate:
            self._log_skip(source_url, "duplicate_content")

        if is_skill:
            from searchos.config.settings import settings

            rendered = render_skill_context(
                content,
                source_url=source_url,
                committed_count=len(receipt.committed_nodes),
                max_chars=settings.extraction_agent_context_max_chars,
                preview_records=settings.extraction_agent_context_preview_records,
                feedback=receipt.feedback,
            )
            if hasattr(result, "content"):
                try:
                    result.content = rendered
                except (AttributeError, TypeError):
                    pass
        if receipt.feedback and not is_skill:
            result = self._inject_feedback(result, receipt.feedback)
        return result

    async def awrap_model_call(self, request: Any, handler: Callable) -> Any:
        response = await handler(request)
        if self._response_has_tool_calls(response):
            return response

        await self.intake.await_idle(timeout=30.0)
        observation = self._final_message_observation(response)
        if observation is not None:
            await self.intake.submit(observation, delivery=DeliveryMode.BUFFERED)
        await self.intake.flush(reason="sub_agent_final_turn")
        return response

    def _final_message_observation(self, response: Any) -> EvidenceObservation | None:
        message = unwrap_ai_message(response)
        text = getattr(message, "content", None)
        if isinstance(text, list):
            text = "\n".join(
                part.get("text", "") if isinstance(part, dict) else str(part) for part in text
            )
        text = (text or "").strip()
        if len(text) < 50:
            return None
        try:
            from searchos.tools.search_state import _current_agent_var

            agent_id = _current_agent_var.get() or ""
        except Exception:
            agent_id = ""
        if self._trajectory_logger:
            self._trajectory_logger._append_raw(
                {
                    "type": "harness",
                    "kind": "final_message_buffered",
                    "agent": agent_id,
                    "chars": len(text),
                }
            )
        return EvidenceObservation(
            content=text,
            source_url=f"agent://{agent_id or 'sub_agent'}/final_summary",
            source_kind=EvidenceSourceKind.AGENT_SUMMARY,
            target_table=self._current_table(),
        )

    @staticmethod
    def _response_has_tool_calls(response: Any) -> bool:
        message = unwrap_ai_message(response)
        if getattr(message, "tool_calls", None):
            return True
        additional = getattr(message, "additional_kwargs", None) or {}
        return isinstance(additional, dict) and bool(additional.get("tool_calls"))

    @staticmethod
    def _current_table() -> str:
        try:
            from searchos.tools.search_state import _current_table_var

            return _current_table_var.get() or ""
        except Exception:
            return ""

    @staticmethod
    def _result_content(result: Any) -> str:
        return str(result.content) if hasattr(result, "content") else str(result)

    def _skill_observation(self, content: str, tool_name: str) -> tuple[str, str] | None:
        try:
            data = json.loads(content)
        except Exception:
            return content, self._extract_source_url(content)
        if isinstance(data, dict):
            if data.get("error") or data.get("success") is False:
                return None
            for key in ("source_url", "url", "page_url"):
                value = data.get(key)
                if isinstance(value, str) and value.startswith("http"):
                    return content, value
        source = self._extract_source_url(content)
        return content, source or f"skill://{tool_name.removeprefix('skill_')}"

    @staticmethod
    def _inject_feedback(result: Any, feedback: str) -> Any:
        if hasattr(result, "content"):
            try:
                result.content = str(result.content) + "\n\n" + feedback
                return result
            except (AttributeError, TypeError):
                pass
        return str(result) + "\n\n" + feedback

    def _record_source_skip(self, source_url: str, reason: str) -> None:
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
    def _extract_source_url(content: str) -> str:
        match = re.search(r"<Page \d+>[^\n]*?\((https?://\S+)", content)
        if match:
            url = match.group(1)
            while url.endswith(")") and url.count(")") > url.count("("):
                url = url[:-1]
            return url
        match = re.search(r"URL:\s*(https?://\S+)", content)
        if match:
            return match.group(1)
        match = re.search(r"https?://\S+", content)
        return match.group(0) if match else ""


__all__ = [
    "EvidenceExtractionMiddleware",
    "_anchored_excerpt",
    "_extract_context",
    "_fold_digits",
    "_provenance_fields",
    "_ungrounded_number",
]
