"""来源 Adapter 共用的上下文与提交反馈。"""

from __future__ import annotations

from typing import Any

from langchain.agents.middleware.types import AgentMiddleware

from searchos.harness.middleware.extraction.core.coordinator import ExtractionCoordinator
from searchos.harness.middleware.extraction.core.models import DeliveryMode, EvidenceObservation
from searchos.harness.middleware.models import TaskContext


class ObservationMiddleware(AgentMiddleware):
    def __init__(
        self,
        coordinator: ExtractionCoordinator,
        *,
        context: TaskContext | None = None,
    ) -> None:
        self.coordinator = coordinator
        self.context = (
            context if context is not None else getattr(coordinator, "task", TaskContext())
        )

    @property
    def run_resources(self) -> tuple[ExtractionCoordinator, ...]:
        return (self.coordinator,)

    async def _submit(self, observation: EvidenceObservation, result: Any) -> Any:
        receipt = await self.coordinator.submit(observation, delivery=DeliveryMode.BUFFERED)
        if receipt.feedback:
            return self._inject_feedback(result, receipt.feedback)
        return result

    @staticmethod
    def _result_content(result: Any) -> str:
        return str(result.content) if hasattr(result, "content") else str(result)

    @staticmethod
    def _inject_feedback(result: Any, feedback: str) -> Any:
        if hasattr(result, "content"):
            try:
                if isinstance(result.content, list):
                    result.content = [
                        *result.content,
                        {"type": "text", "text": feedback},
                    ]
                else:
                    result.content = str(result.content) + "\n\n" + feedback
                return result
            except (AttributeError, TypeError):
                pass
        return str(result) + "\n\n" + feedback
