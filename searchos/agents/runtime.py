"""Agent runtime: the single ReAct loop factory + session-scoped context.

Two halves, kept together because every spawn touches both:

1. **ReAct factory** (``create_search_agent_graph``) — explicit LangChain
   middleware assembly on the LangGraph ReAct loop. Business mechanisms run
   only when the caller loads them.

2. **Runtime context** (``_ctx`` / ``set_orchestrator_context``) — the ContextVars
   that bind one session run to its workspace, models, task pool, and scheduler.
   Callers get a small runtime interface instead of scattered module globals.

Paper §Agent: "Model 比静态图更善于决定'下一步做什么'——Harness 的职责是约束和验证，不是编排"。
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from contextvars import ContextVar
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool
from langgraph.checkpoint.memory import MemorySaver

from searchos.harness.steering import SteerQueue
from searchos.socm.storage.workspace import WorkspaceManager

logger = logging.getLogger(__name__)


# ===========================================================================
# Part 1 — ReAct loop factory
# ===========================================================================


def create_search_agent_graph(
    model: BaseChatModel,
    tools: Sequence[BaseTool],
    *,
    system_prompt: str = "",
    middleware: Sequence[Any] = (),
    subagents: list[Any] | None = None,
    skills: list[str] | None = None,
    backend: Any = None,
    checkpointer: Any = None,
    state_schema: type | None = None,
    name: str = "search_agent",
    control: Any = None,
    drain_tools: frozenset[str] = frozenset(),
    finish_without_tools: bool = True,
    policy: Any = None,
    workspace: Any = None,
    trajectory_logger: Any = None,
    conversation_logger: Any = None,
    agent_id: str | None = None,
    emit_tool_started: bool = True,
    image_fallback: bool | None = None,
) -> Any:
    """Create an explicitly assembled search agent graph.

    Callers supply concrete middleware instances in execution order.

    Args:
        model: LLM (BaseChatModel).
        tools: LangChain tools.
        system_prompt: Backbone system prompt.
        middleware: AgentMiddleware instances, outermost first.
        subagents: Explicit optional SubAgent specs; no default agent is inserted.
        skills: Paths to skill .md files for SkillsMiddleware.
        backend: Code execution / filesystem sandbox backend.
        checkpointer: LangGraph checkpointer (defaults to in-memory).
        state_schema: Custom state schema.
        name: Agent name for logging.
        control: Shared control state; inferred from middleware when omitted.
        drain_tools: Tools allowed while finishing after a stop signal.
        finish_without_tools: Convert tool requests into a final reply after stop.
        policy: Optional role policy for model and tool invocation.
        workspace: Workspace used to record state changes.
        trajectory_logger: Session trajectory recorder, independent of middleware.
        conversation_logger: Session recorder for injected context messages.
        agent_id: Identity for recorded events; defaults to name.
        emit_tool_started: Record tool start events as well as completed calls.
        image_fallback: Retry unsupported image inputs as text. None follows
            the run configuration's automatic image-reading setting.

    Returns:
        Runnable graph with state inspection and automatic cleanup of loaded resources.
    """
    from langchain.agents import create_agent

    from searchos.harness.middleware.context.compaction_context_middleware import (
        CompactionContextMiddleware,
    )
    from searchos.harness.middleware.sensor.budget_middleware import BudgetMiddleware

    compaction_position = next(
        (i for i, item in enumerate(middleware) if isinstance(item, CompactionContextMiddleware)),
        len(middleware),
    )
    if any(isinstance(item, BudgetMiddleware) for item in middleware[compaction_position + 1 :]):
        raise ValueError(
            "Place BudgetMiddleware before CompactionContextMiddleware "
            "to checkpoint usage before deleting history"
        )

    if checkpointer is None:
        checkpointer = MemorySaver()
    prompt = system_prompt or "You are a search agent."
    optional_middleware: list[Any] = []
    if skills or subagents:
        from deepagents.backends import StateBackend

        if backend is None:

            def backend(runtime):
                return StateBackend(runtime)

        if skills:
            from deepagents.middleware.skills import SkillsMiddleware

            optional_middleware.append(SkillsMiddleware(backend=backend, sources=skills))
        if subagents:
            from deepagents.middleware.subagents import SubAgentMiddleware

            specs = [dict(spec) for spec in subagents]
            for spec in specs:
                if "runnable" not in spec:
                    spec.setdefault("model", model)
                    spec.setdefault("tools", list(tools))
            optional_middleware.append(
                SubAgentMiddleware(backend=backend, subagents=specs, state_schema=state_schema)
            )

    from searchos.agents.execution import (
        ControlExecutor,
        _BeforeModel,
        _ExecutionHooks,
        _ManagedGraph,
        _RecordingHooks,
        bind_controls,
        loaded_resources,
    )

    control = bind_controls(middleware, control)
    if image_fallback is None:
        from searchos.config.run_config import current_run_config

        config = current_run_config()
        image_fallback = config.enable_web_image_read and config.web_image_read_mode == "auto"
    executor = ControlExecutor(
        control,
        drain_tools=drain_tools,
        finish_without_tools=finish_without_tools,
    )
    resources = loaded_resources(middleware)
    recorder = None
    if trajectory_logger is not None or conversation_logger is not None:
        from searchos.harness.telemetry.recording import AgentRecorder

        recorder = AgentRecorder(
            trajectory_logger,
            agent_id=agent_id or name,
            workspace=workspace,
            emit_started=emit_tool_started,
            conversation_logger=conversation_logger,
        )
    effective_middleware: list[Any] = (
        ([_BeforeModel(resources)] if resources else [])
        + optional_middleware
        + list(middleware)
        + [
            _ExecutionHooks(
                executor, policy=policy, image_fallback=image_fallback, recorder=recorder
            ),
        ]
    )
    if trajectory_logger is not None:
        effective_middleware.insert(0, _RecordingHooks(recorder))

    graph = create_agent(
        model=model,
        tools=list(tools),
        system_prompt=prompt,
        middleware=effective_middleware,
        checkpointer=checkpointer,
        state_schema=state_schema,
        name=name,
    ).with_config({"recursion_limit": 9999})

    logger.info(
        "Created search agent graph '%s' with %d tools, %d middleware, %s skills",
        name,
        len(tools),
        len(middleware),
        len(skills) if skills else 0,
    )
    graph.middleware = list(middleware)
    graph.control = control
    graph.policy = policy
    if resources:
        from searchos.config.settings import settings

        return _ManagedGraph(graph, resources, settings.extraction_finalize_timeout_s)
    return graph


# ===========================================================================
# Part 2 — Session-scoped runtime context
# ===========================================================================

_workspace_var: ContextVar[WorkspaceManager | None] = ContextVar("so_orch_workspace", default=None)
_model_var: ContextVar[BaseChatModel | None] = ContextVar("so_orch_model", default=None)
_judge_model_var: ContextVar[BaseChatModel | None] = ContextVar("so_orch_judge", default=None)
_extraction_model_var: ContextVar[BaseChatModel | None] = ContextVar(
    "so_orch_extraction", default=None
)
_sub_agent_model_var: ContextVar[BaseChatModel | None] = ContextVar(
    "so_orch_sub_agent", default=None
)
_synthesis_model_var: ContextVar[BaseChatModel | None] = ContextVar(
    "so_orch_synthesis", default=None
)
_skill_evolver_model_var: ContextVar[BaseChatModel | None] = ContextVar(
    "so_skill_evolver_model",
    default=None,
)
# "post_mortem" role model — distills FailureMemory records from failed
# sub-agent traces. When None, post-mortems silently skip.
_post_mortem_model_var: ContextVar[BaseChatModel | None] = ContextVar(
    "so_post_mortem_model",
    default=None,
)
# Per-session post-mortem fire counter. ``list[int]`` so the trigger hook
# can mutate in place across awaits.
_post_mortem_count_var: ContextVar[list[int] | None] = ContextVar(
    "so_post_mortem_count",
    default=None,
)
# Live post-mortem coroutine handles. Kept in a list (not task_pool) so they
# are isolated from the scheduler / check_agents "is the pool empty?" logic,
# but the harness drain phase can still await them so their
# atomic_update_state writes land before the workspace closes.
_post_mortem_tasks_var: ContextVar[list[Any] | None] = ContextVar(
    "so_post_mortem_tasks",
    default=None,
)
_skill_registry_var: ContextVar[Any] = ContextVar("so_orch_skills", default=None)
_trajectory_logger_var: ContextVar[Any] = ContextVar("so_orch_traj", default=None)
_conversation_logger_var: ContextVar[Any] = ContextVar("so_orch_conv", default=None)
_query_var: ContextVar[str] = ContextVar("so_orch_query", default="")
_steer_queue_var: ContextVar[SteerQueue | None] = ContextVar("so_orch_steer_queue", default=None)
_repair_target_allowlist_var: ContextVar[set[str] | None] = ContextVar(
    "so_orch_repair_target_allowlist",
    default=None,
)

_task_pool_var: ContextVar[dict[str, Any] | None] = ContextVar("so_orch_task_pool", default=None)
_completed_var: ContextVar[dict[str, Any] | None] = ContextVar("so_orch_completed", default=None)
_agent_graph_var: ContextVar[dict[str, dict[str, Any]] | None] = ContextVar(
    "so_orch_agent_graphs", default=None
)
_check_call_count_var: ContextVar[list[int] | None] = ContextVar(
    "so_orch_check_call_count", default=None
)
_session_search_count_var: ContextVar[list[int] | None] = ContextVar(
    "so_orch_session_search_count", default=None
)
_sub_agent_counter_var: ContextVar[dict[str, int] | None] = ContextVar(
    "so_orch_sub_agent_counter", default=None
)
_scheduler_var: ContextVar[Any] = ContextVar("so_orch_scheduler", default=None)
# Mutable box: set True once the ORCHESTRATOR's budget is exhausted, so the
# scheduler stops spawning new sub-agents while already-running ones drain.
_budget_exhausted_var: ContextVar[list[bool] | None] = ContextVar(
    "so_orch_budget_exhausted", default=None
)


def _scheduler():
    """Return the session-scoped Scheduler singleton.

    Normally pre-created by ``set_orchestrator_context`` in the session's
    parent context. The lazy branch below is a fallback for test paths —
    inside a tool task it would bind to that task's ContextVar copy only.
    """
    scheduler = _scheduler_var.get()
    if scheduler is None:
        from searchos.agents.orchestrator.scheduler import Scheduler

        scheduler = Scheduler()
        _scheduler_var.set(scheduler)
    return scheduler


class _Ctx:
    """Property accessor around orchestrator ContextVars."""

    @property
    def workspace(self) -> WorkspaceManager | None:
        return _workspace_var.get()

    @property
    def model(self) -> BaseChatModel | None:
        return _model_var.get()

    @property
    def judge_model(self) -> BaseChatModel | None:
        return _judge_model_var.get()

    @property
    def extraction_model(self) -> BaseChatModel | None:
        return _extraction_model_var.get()

    @property
    def sub_agent_model(self) -> BaseChatModel | None:
        return _sub_agent_model_var.get()

    @property
    def synthesis_model(self) -> BaseChatModel | None:
        return _synthesis_model_var.get()

    @property
    def skill_evolver_model(self) -> BaseChatModel | None:
        return _skill_evolver_model_var.get()

    @property
    def post_mortem_model(self) -> BaseChatModel | None:
        return _post_mortem_model_var.get()

    @property
    def post_mortem_tasks(self) -> list[Any] | None:
        return _post_mortem_tasks_var.get()

    @property
    def skill_registry(self) -> Any:
        return _skill_registry_var.get()

    @property
    def trajectory_logger(self) -> Any:
        return _trajectory_logger_var.get()

    @property
    def conversation_logger(self) -> Any:
        return _conversation_logger_var.get()

    @property
    def task_pool(self) -> dict[str, Any]:
        pool = _task_pool_var.get()
        if pool is None:
            raise RuntimeError(
                "Orchestrator task pool not initialized. Call set_orchestrator_context() first."
            )
        return pool

    @property
    def completed(self) -> dict[str, Any]:
        done = _completed_var.get()
        if done is None:
            raise RuntimeError("Orchestrator completed-pool not initialized.")
        return done

    @property
    def agent_graphs(self) -> dict[str, dict[str, Any]]:
        graphs = _agent_graph_var.get()
        if graphs is None:
            raise RuntimeError("Orchestrator agent-graph registry not initialized.")
        return graphs

    @property
    def query(self) -> str:
        return _query_var.get()

    @property
    def steer_queue(self) -> SteerQueue | None:
        return _steer_queue_var.get()

    @property
    def repair_target_allowlist(self) -> set[str] | None:
        scope = _repair_target_allowlist_var.get()
        return set(scope) if scope is not None else None

    @property
    def budget_exhausted(self) -> bool:
        box = _budget_exhausted_var.get()
        return bool(box[0]) if box else False

    def mark_budget_exhausted(self) -> None:
        box = _budget_exhausted_var.get()
        if box:
            box[0] = True


_ctx = _Ctx()


def set_orchestrator_context(
    workspace: WorkspaceManager,
    model: BaseChatModel,
    skill_registry: Any = None,
    trajectory_logger: Any = None,
    judge_model: BaseChatModel | None = None,
    extraction_model: BaseChatModel | None = None,
    sub_agent_model: BaseChatModel | None = None,
    skill_evolver_model: BaseChatModel | None = None,
    post_mortem_model: BaseChatModel | None = None,
    conversation_logger: Any = None,
    query: str = "",
    scheduler_task_allowlist: set[str] | None = None,
    repair_target_allowlist: set[str] | None = None,
    synthesis_model: BaseChatModel | None = None,
    steer_queue: SteerQueue | None = None,
) -> None:
    """Bind runtime context for orchestrator tools in the current task."""
    _workspace_var.set(workspace)
    _model_var.set(model)
    _judge_model_var.set(judge_model)
    _extraction_model_var.set(extraction_model)
    _sub_agent_model_var.set(sub_agent_model)
    _synthesis_model_var.set(synthesis_model)
    _skill_evolver_model_var.set(skill_evolver_model)
    _post_mortem_model_var.set(post_mortem_model)
    _skill_registry_var.set(skill_registry)
    _trajectory_logger_var.set(trajectory_logger)
    _conversation_logger_var.set(conversation_logger)
    _query_var.set(query)
    _steer_queue_var.set(steer_queue)
    _repair_target_allowlist_var.set(
        set(repair_target_allowlist) if repair_target_allowlist is not None else None
    )
    _task_pool_var.set({})
    _completed_var.set({})
    _agent_graph_var.set({})
    _check_call_count_var.set([0])
    _post_mortem_count_var.set([0])
    _post_mortem_tasks_var.set([])
    _session_search_count_var.set([0])
    _sub_agent_counter_var.set({})
    # Create the Scheduler EAGERLY in the session's parent context. Lazy
    # creation inside _scheduler() happens in a tool task's ContextVar COPY,
    # invisible to sibling tool calls — each check_agents would get a fresh
    # Scheduler (own tick lock, own WriterTriggerSensor stages), defeating
    # both the concurrency cap and the writer trigger memory.
    from searchos.agents.orchestrator.scheduler import Scheduler

    task_allowlist = scheduler_task_allowlist
    if repair_target_allowlist is not None and task_allowlist is None:
        task_allowlist = set()
    _scheduler_var.set(Scheduler(task_allowlist=task_allowlist))
    _budget_exhausted_var.set([False])
