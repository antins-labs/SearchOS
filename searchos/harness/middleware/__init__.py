"""通过原生 AgentMiddleware 实例列表组合运行机制。"""

from searchos.harness.middleware.context.compaction_context_middleware import (
    CompactionContextMiddleware,
)
from searchos.harness.middleware.context.dynamic_trim_middleware import DynamicTrimMiddleware
from searchos.harness.middleware.context.search_episode_middleware import SearchEpisodeMiddleware
from searchos.harness.middleware.context.socm_middleware import SOCMContextMiddleware
from searchos.harness.middleware.context.tool_history_middleware import ToolHistoryMiddleware
from searchos.harness.middleware.context.tool_results_middleware import (
    ToolResultLimitMiddleware,
)
from searchos.harness.middleware.extraction import (
    ExtractionCoordinator,
    FinalSummaryEvidenceMiddleware,
    LocalEvidenceMiddleware,
    WebEvidenceMiddleware,
)
from searchos.harness.middleware.models import SourceContext, TaskContext
from searchos.harness.middleware.pipelines import (
    explore_pipeline,
    local_search_pipeline,
    orchestrator_pipeline,
    web_search_pipeline,
    writer_pipeline,
)
from searchos.harness.middleware.sensor.budget_middleware import BudgetMiddleware
from searchos.harness.middleware.sensor.core.models import BudgetState, ControlState
from searchos.harness.middleware.sensor.detection_middleware import (
    CoverageStallMiddleware,
    DispatchRoundMiddleware,
    EmptyResultMiddleware,
    QueryRepetitionMiddleware,
    ReadingReminderMiddleware,
    StateStallMiddleware,
)
from searchos.harness.middleware.sensor.failure_recording_middleware import (
    FailureRecordingMiddleware,
)
from searchos.harness.middleware.sensor.progress_middleware import (
    ProgressGuardMiddleware,
    ReadingProgressMiddleware,
    ToolProgressMiddleware,
)
from searchos.harness.middleware.sensor.route_middleware import RetryRouteMiddleware

__all__ = [
    "CompactionContextMiddleware",
    "BudgetMiddleware",
    "BudgetState",
    "ControlState",
    "DynamicTrimMiddleware",
    "EmptyResultMiddleware",
    "FailureRecordingMiddleware",
    "QueryRepetitionMiddleware",
    "ReadingReminderMiddleware",
    "StateStallMiddleware",
    "ExtractionCoordinator",
    "FinalSummaryEvidenceMiddleware",
    "LocalEvidenceMiddleware",
    "SOCMContextMiddleware",
    "SearchEpisodeMiddleware",
    "TaskContext",
    "SourceContext",
    "WebEvidenceMiddleware",
]

__all__ += [
    "CoverageStallMiddleware",
    "DispatchRoundMiddleware",
    "ProgressGuardMiddleware",
    "ReadingProgressMiddleware",
    "RetryRouteMiddleware",
    "ToolHistoryMiddleware",
    "ToolProgressMiddleware",
    "ToolResultLimitMiddleware",
    "explore_pipeline",
    "local_search_pipeline",
    "orchestrator_pipeline",
    "web_search_pipeline",
    "writer_pipeline",
]
