"""本地原文窗口抽取与来源定位校验。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from searchos.harness.middleware.extraction.base import ObservationMiddleware
from searchos.harness.middleware.extraction.core.coordinator import ExtractionCoordinator
from searchos.harness.middleware.extraction.core.sources.local import build_observation
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
        observation = build_observation(
            result, self._result_content(result), self.context, self.source_scope
        )
        if observation is not None:
            return await self._submit(observation, result)
        return result
