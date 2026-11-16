"""网页及 Access Skill 页面抽取。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from searchos.harness.middleware.extraction.base import ObservationMiddleware
from searchos.harness.middleware.extraction.core.coordinator import ExtractionCoordinator
from searchos.harness.middleware.extraction.core.sources.web import WebObservationSource
from searchos.harness.middleware.models import SourceContext, TaskContext
from searchos.harness.middleware.utils.messages import extract_tool_name


class WebEvidenceMiddleware(ObservationMiddleware):
    name = "WebEvidenceMiddleware"

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
        self._sources = WebObservationSource(trajectory_logger)

    async def awrap_tool_call(self, request: Any, handler: Callable) -> Any:
        result = await handler(request)
        if extract_tool_name(request, default="") == "exec":
            observations = self._sources.execution_observations(result, self.context)
            if observations:
                feedback = await self.coordinator.submit_exec(observations)
                if feedback:
                    result = self._inject_feedback(result, feedback)
            return result
        for observation in await self._sources.observations(request, result, self.context):
            result = await self._submit(observation, result)
        return result
