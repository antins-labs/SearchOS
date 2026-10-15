"""默认组合：创建业务对象、列出 middleware、调用同一个图入口。"""

from __future__ import annotations

from searchos.config.run_config import current_run_config
from searchos.config.middleware import selection
from searchos.config.settings import settings
from searchos.harness.middleware.context.dynamic_trim_middleware import DynamicTrimMiddleware
from searchos.harness.middleware.context.search_episode_middleware import SearchEpisodeMiddleware
from searchos.harness.middleware.context.socm_middleware import SOCMContextMiddleware
from searchos.harness.middleware.context.tool_history_middleware import ToolHistoryMiddleware
from searchos.harness.middleware.context.tool_results_middleware import (
    ToolResultLimitMiddleware,
)
from searchos.harness.middleware.extraction import (
    ExtractionConfig,
    ExtractionCoordinator,
    FinalSummaryEvidenceMiddleware,
    LocalEvidenceMiddleware,
    WebEvidenceMiddleware,
)
from searchos.harness.middleware.models import SourceContext, TaskContext
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
from searchos.harness.middleware.sensor.progress_middleware import (
    ProgressGuardMiddleware,
    ReadingProgressMiddleware,
    ToolProgressMiddleware,
)
from searchos.harness.middleware.sensor.route_middleware import RetryRouteMiddleware

ORCHESTRATOR_DRAIN_TOOLS = frozenset(
    {
        "check_agents",
        "add_entities",
        "edit_entities",
        "remove_entities",
        "inspect_table",
        "python",
        "stop_task",
    }
)
WRITER_DRAIN_TOOLS = frozenset(
    {
        "read_outline",
        "update_outline",
        "write_section",
        "edit_section",
        "annotate_section",
        "read_coverage",
        "read_evidence",
        "resolve_cell_provenance",
        "list_frontier",
        "read_task_report",
    }
)
SEARCH_RESULT_LIMITS = dict.fromkeys(
    {
        "web_search",
        "tavily_search",
        "serper_search",
        "browser_navigate",
        "search",
        "local_catalog",
    },
    6000,
) | {"explore_web": 48000}


def _graph(model, tools, system_prompt, middleware, *, pipeline, **graph_options):
    from searchos.agents.runtime import create_search_agent_graph
    from searchos.harness.middleware.context.compaction_context_middleware import CompactionContextMiddleware
    from searchos.harness.middleware.context.utils.messages import model_input_limit

    selected = selection(pipeline, settings)
    if pipeline in settings.middleware_pipelines:
        instances = {type(item).__name__: item for item in middleware}
        if "CompactionContextMiddleware" in selected and model_input_limit(model):
            instances["CompactionContextMiddleware"] = CompactionContextMiddleware(model)
        middleware = [instances[name] for name in selected if name in instances]

    return create_search_agent_graph(
        model=model,
        tools=tools,
        system_prompt=system_prompt,
        middleware=middleware,
        **graph_options,
    )


def _worker_defaults(
    workspace,
    task,
    budget,
    control,
    *,
    pipeline,
    history,
    view="task",
    drain_tools=frozenset(),
    agent_graphs=None,
):
    middleware = [
        BudgetMiddleware(
            budget, control=control, workspace=workspace, task=task, drain_tools=drain_tools
        ),
        RetryRouteMiddleware(workspace, agent_id=task.agent_id),
        QueryRepetitionMiddleware(control, workspace=workspace, task=task),
        ReadingReminderMiddleware(control),
        EmptyResultMiddleware(control, workspace=workspace, task=task),
        ToolResultLimitMiddleware(SEARCH_RESULT_LIMITS),
    ]
    if not isinstance(history, DynamicTrimMiddleware):
        middleware.insert(0, history)
    selected = selection(pipeline, settings)
    if "SOCMContextMiddleware" in selected:
        middleware.append(
            SOCMContextMiddleware(
                workspace,
                task=task,
                view=view,
                control=control,
                agent_graphs=agent_graphs,
                heartbeat_turns=settings.socm_heartbeat_turns,
            )
        )
    if "ToolHistoryMiddleware" in selected:
        middleware.append(ToolHistoryMiddleware())
    middleware.append(
        history
        if isinstance(history, DynamicTrimMiddleware)
        else DynamicTrimMiddleware(max_tokens_fraction=settings.dynamic_trim_fraction)
    )
    return middleware


def _extraction(model, workspace, task, policy, trajectory_logger):
    if model is None:
        return None
    return ExtractionCoordinator(
        model,
        workspace=workspace,
        task=task,
        policy=policy,
        config=ExtractionConfig.from_settings(),
        trajectory_logger=trajectory_logger,
    )


def _search_progress(workspace, task, control, extraction):
    guard = (
        ProgressGuardMiddleware(
            extraction, control, task=task, limit=settings.search_agent_no_progress_tool_limit
        )
        if extraction is not None
        else ToolProgressMiddleware(
            control,
            workspace=workspace,
            task=task,
            limit=settings.search_agent_no_progress_tool_limit,
        )
    )
    middleware = [guard, ReadingProgressMiddleware(set())]
    if workspace is not None:
        middleware.append(StateStallMiddleware(workspace, control=control, task=task))
    return middleware


def web_search_pipeline(
    model,
    tools,
    *,
    workspace,
    task: TaskContext,
    system_prompt="",
    budget=None,
    control=None,
    extraction_model=None,
    extraction_policy="task_rows",
    final_summary=True,
    source: SourceContext | None = None,
    agent_graphs=None,
    trajectory_logger=None,
    conversation_logger=None,
    **graph_options,
):
    """网页检索默认组合；修改来源行为可直接手写 middleware 列表。"""
    budget, control = budget or BudgetState(), control or ControlState()
    extraction = _extraction(
        extraction_model, workspace, task, extraction_policy, trajectory_logger
    )
    history = (
        SearchEpisodeMiddleware(
            workspace,
            evidence_source=extraction,
            history_max_tokens=settings.layered_context_layer2_max_tokens,
        )
        if "SearchEpisodeMiddleware" in selection("web_search", settings)
        else DynamicTrimMiddleware(max_tokens_fraction=settings.dynamic_trim_fraction)
    )
    middleware = [
        *_search_progress(workspace, task, control, extraction),
        *_worker_defaults(
            workspace,
            task,
            budget,
            control,
            pipeline="web_search",
            history=history,
            agent_graphs=agent_graphs,
        ),
    ]
    if extraction is not None:
        middleware.append(
            WebEvidenceMiddleware(extraction, source=source, trajectory_logger=trajectory_logger)
        )
        if final_summary:
            middleware.append(FinalSummaryEvidenceMiddleware(extraction))
    return _graph(
        model,
        tools,
        system_prompt,
        middleware,
        pipeline="web_search",
        control=control,
        workspace=workspace,
        trajectory_logger=trajectory_logger,
        conversation_logger=conversation_logger,
        agent_id=task.agent_id,
        **graph_options,
    )


def local_search_pipeline(
    model,
    tools,
    *,
    workspace,
    task: TaskContext,
    system_prompt="",
    budget=None,
    control=None,
    extraction_model=None,
    extraction_policy="task_rows",
    final_summary=True,
    source: SourceContext | None = None,
    agent_graphs=None,
    trajectory_logger=None,
    conversation_logger=None,
    **graph_options,
):
    """本地检索默认组合，保留原文窗口供下一轮推理使用。"""
    budget, control = budget or BudgetState(), control or ControlState()
    extraction = _extraction(
        extraction_model, workspace, task, extraction_policy, trajectory_logger
    )
    middleware = [
        *_search_progress(workspace, task, control, extraction),
        *_worker_defaults(
            workspace,
            task,
            budget,
            control,
            pipeline="local_search",
            history=DynamicTrimMiddleware(max_tokens_fraction=settings.dynamic_trim_fraction),
            agent_graphs=agent_graphs,
        ),
    ]
    if extraction is not None:
        middleware.append(LocalEvidenceMiddleware(extraction, source=source))
        if final_summary:
            middleware.append(FinalSummaryEvidenceMiddleware(extraction))
    return _graph(
        model,
        tools,
        system_prompt,
        middleware,
        pipeline="local_search",
        control=control,
        workspace=workspace,
        trajectory_logger=trajectory_logger,
        conversation_logger=conversation_logger,
        agent_id=task.agent_id,
        **graph_options,
    )


def explore_pipeline(
    model,
    tools,
    *,
    workspace,
    task: TaskContext,
    system_prompt="",
    budget=None,
    control=None,
    agent_graphs=None,
    trajectory_logger=None,
    conversation_logger=None,
    **graph_options,
):
    budget, control = budget or BudgetState(), control or ControlState()
    middleware = _worker_defaults(
        workspace,
        task,
        budget,
        control,
        pipeline="explore",
        history=DynamicTrimMiddleware(max_tokens_fraction=settings.dynamic_trim_fraction),
        agent_graphs=agent_graphs,
    )
    from searchos.agents.explore.policy import ExplorePolicy

    policy = None
    if settings.enable_explore_batch:
        config = current_run_config()
        policy = ExplorePolicy(
            max_waves=config.explore_max_waves,
            control=control,
        )
    return _graph(
        model,
        tools,
        system_prompt,
        middleware,
        pipeline="explore",
        control=control,
        workspace=workspace,
        trajectory_logger=trajectory_logger,
        conversation_logger=conversation_logger,
        agent_id=task.agent_id,
        policy=policy,
        emit_tool_started=True,
        **graph_options,
    )


def writer_pipeline(
    model,
    tools,
    *,
    workspace,
    task: TaskContext,
    system_prompt="",
    budget=None,
    control=None,
    agent_graphs=None,
    trajectory_logger=None,
    conversation_logger=None,
    **graph_options,
):
    budget, control = budget or BudgetState(), control or ControlState()
    middleware = _worker_defaults(
        workspace,
        task,
        budget,
        control,
        pipeline="writer",
        history=DynamicTrimMiddleware(max_tokens_fraction=settings.dynamic_trim_fraction),
        view="writing",
        drain_tools=WRITER_DRAIN_TOOLS,
        agent_graphs=agent_graphs,
    )
    return _graph(
        model,
        tools,
        system_prompt,
        middleware,
        pipeline="writer",
        control=control,
        workspace=workspace,
        trajectory_logger=trajectory_logger,
        conversation_logger=conversation_logger,
        agent_id=task.agent_id,
        drain_tools=WRITER_DRAIN_TOOLS,
        finish_without_tools=False,
        **graph_options,
    )


def orchestrator_pipeline(
    model,
    tools,
    *,
    workspace,
    system_prompt="",
    budget=None,
    control=None,
    agent_graphs=None,
    task_pool=None,
    on_exhausted=None,
    trajectory_logger=None,
    conversation_logger=None,
    steer_queue=None,
    **graph_options,
):
    budget = budget or BudgetState(max_queries=0, max_iterations=settings.orch_max_iterations)
    control = control or ControlState()
    middleware = [
        BudgetMiddleware(
            budget,
            control=control,
            drain_tools=ORCHESTRATOR_DRAIN_TOOLS,
            on_exhausted=on_exhausted,
            warn_iterations=True,
            wrap_up="Drain running agents with check_agents, inspect the live table, then answer.",
        ),
        RetryRouteMiddleware(workspace, agent_id="orchestrator"),
        DispatchRoundMiddleware(control, max_rounds=settings.orch_max_dispatches),
        CoverageStallMiddleware(
            workspace,
            control=control,
            agent_graphs=agent_graphs if agent_graphs is not None else {},
            max_stalled_rounds=settings.orch_coverage_stall_rounds,
        ),
        ToolResultLimitMiddleware(SEARCH_RESULT_LIMITS),
    ]
    if steer_queue is not None:
        from searchos.harness.middleware.context.steering_middleware import SteeringMiddleware

        middleware.insert(0, SteeringMiddleware(steer_queue, trajectory_logger=trajectory_logger))
    selected = selection("orchestrator", settings)
    if "SOCMContextMiddleware" in selected:
        middleware.append(
            SOCMContextMiddleware(
                workspace,
                task=TaskContext(agent_id="orchestrator"),
                view="overview",
                control=control,
                heartbeat_turns=settings.socm_heartbeat_turns,
            )
        )
    from searchos.agents.orchestrator.policy import DispatchPolicy

    policy = None
    if settings.max_parallel_agents > 0:
        policy = DispatchPolicy(
            workspace,
            agents=task_pool if task_pool is not None else {},
            control=control,
            capacity=settings.max_parallel_agents,
            cooldown_s=settings.pool_nudge_cooldown_s,
            max_reminders=settings.pool_nudge_max_count,
        )
    if "ToolHistoryMiddleware" in selected:
        middleware.append(ToolHistoryMiddleware())
    middleware.append(DynamicTrimMiddleware(max_tokens=settings.orch_trim_max_tokens))
    return _graph(
        model,
        tools,
        system_prompt,
        middleware,
        pipeline="orchestrator",
        control=control,
        workspace=workspace,
        trajectory_logger=trajectory_logger,
        conversation_logger=conversation_logger,
        agent_id="orchestrator",
        policy=policy,
        drain_tools=ORCHESTRATOR_DRAIN_TOOLS,
        finish_without_tools=False,
        **graph_options,
    )
