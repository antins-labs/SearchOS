"""把实际接受的最终回复提交为摘要观测。"""

from __future__ import annotations

from typing import Any

from searchos.harness.middleware.extraction.base import ObservationMiddleware
from searchos.harness.middleware.extraction.core.models import (
    DeliveryMode,
    EvidenceObservation,
    EvidenceSourceKind,
)
from searchos.harness.middleware.utils.messages import unwrap_ai_message


class FinalSummaryEvidenceMiddleware(ObservationMiddleware):
    name = "FinalSummaryEvidenceMiddleware"

    async def aafter_agent(self, state: Any, runtime: Any) -> None:
        messages = state.get("messages", [])
        if not messages:
            return
        response = messages[-1]
        if getattr(response, "type", None) != "ai" or self._response_has_tool_calls(response):
            return
        observation = self._final_message_observation(response)
        if observation is not None:
            await self.coordinator.submit(observation, delivery=DeliveryMode.BUFFERED)

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
        return EvidenceObservation(
            content=text,
            source_url=f"agent://{self.context.agent_id or 'sub_agent'}/final_summary",
            source_kind=EvidenceSourceKind.AGENT_SUMMARY,
            target_table=self.context.target_table,
            task_id=self.context.task_id,
            task_text=self.context.task_text,
        )

    @staticmethod
    def _response_has_tool_calls(response: Any) -> bool:
        message = unwrap_ai_message(response)
        if getattr(message, "tool_calls", None):
            return True
        additional = getattr(message, "additional_kwargs", None) or {}
        return isinstance(additional, dict) and bool(additional.get("tool_calls"))
