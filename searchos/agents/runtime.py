"""Agent runtime: the single ReAct loop factory + session-scoped context.

Two halves, kept together because every spawn touches both:

1. **ReAct factory** (``create_search_agent_graph``) — the one deepagents loop
   the whole Harness revolves around. ``_neutralize_deepagents_builtins`` strips
   deepagents' built-in task / filesystem / todo / summarization surfaces so the
   model only sees SearchOS's purpose-built tools.

2. **Runtime context** (``_ctx`` / ``set_orchestrator_context``) — the ContextVars
   that bind one session run to its workspace, models, task pool, and scheduler.
   Callers get a small runtime interface instead of scattered module globals.

Paper §Agent: "Model 比静态图更善于决定'下一步做什么'——Harness 的职责是约束和验证，不是编排"。
"""

from __future__ import annotations

import logging
from contextvars import ContextVar
from typing import Any, Sequence

from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool
from langgraph.checkpoint.memory import MemorySaver

from searchos.socm.workspace import WorkspaceManager

logger = logging.getLogger(__name__)


# ===========================================================================
# Part 1 — ReAct loop factory
# ===========================================================================

def _neutralize_deepagents_builtins() -> None:
    """Strip deepagents' built-in Deep-Agent preamble and `task`-tool framework.

    Our orchestrator already has its own dispatch for worker spawning; the
    built-in `task` tool let sub-agents spawn their own `general-purpose`
    sub-sub-agents, which (a) blocked the outer ReAct loop for 2-3 minutes
    each invocation and (b) broke scope isolation by running with the full
    tool suite outside our middleware stack. Neutralizing four surfaces:

    1. ``BASE_AGENT_PROMPT`` — the "You are a Deep Agent..." preamble that
       deepagents appends after every caller-supplied system_prompt.
    2. ``SubAgentMiddleware.(a)wrap_model_call`` — normally injects
       ``TASK_SYSTEM_PROMPT`` + the list of available subagents.
    3. The ``task`` tool itself — stripped per-agent via
       ``_ToolExclusionMiddleware`` inside ``create_search_agent_graph``.
    4. ``FilesystemMiddleware`` system prompt — injects a prompt listing
       ``read_file``, ``write_file``, etc. even though we strip those tools.
       The prompt-only leak causes the LLM to hallucinate tool calls that
       don't exist, resulting in 400 errors. We blank the template so the
       middleware still runs (it handles message eviction), but no filesystem
       tool descriptions reach the model.
    """
    import deepagents.graph as _dgraph
    import deepagents.middleware.subagents as _dsub
    import deepagents.middleware.async_subagents as _dasub
    import deepagents.middleware.filesystem as _dfs
    import deepagents.middleware.summarization as _dsum
    from langchain.agents.middleware import todo as _dtodo

    _dgraph.BASE_AGENT_PROMPT = ""

    def _noop_wrap(self, request, handler):
        return handler(request)

    async def _noop_awrap(self, request, handler):
        return await handler(request)

    # SubAgentMiddleware: TASK_SYSTEM_PROMPT (`task` tool) — excluded.
    _dsub.SubAgentMiddleware.wrap_model_call = _noop_wrap
    _dsub.SubAgentMiddleware.awrap_model_call = _noop_awrap

    # AsyncSubAgentMiddleware: ASYNC_TASK_SYSTEM_PROMPT — same story.
    _dasub.AsyncSubAgentMiddleware.wrap_model_call = _noop_wrap
    _dasub.AsyncSubAgentMiddleware.awrap_model_call = _noop_awrap

    # FilesystemMiddleware: ls/read/write/edit/glob/grep/execute — excluded.
    _dfs._FILESYSTEM_SYSTEM_PROMPT_TEMPLATE = ""
    _dfs.EXECUTION_SYSTEM_PROMPT = ""

    # TodoListMiddleware: `write_todos` — excluded.
    _dtodo.WRITE_TODOS_SYSTEM_PROMPT = ""
    _dtodo.TodoListMiddleware.wrap_model_call = _noop_wrap
    _dtodo.TodoListMiddleware.awrap_model_call = _noop_awrap

    # SummarizationToolMiddleware: `compact_conversation` — excluded.
    _dsum.SUMMARIZATION_SYSTEM_PROMPT = ""
    _dsum.SummarizationToolMiddleware.wrap_model_call = _noop_wrap
    _dsum.SummarizationToolMiddleware.awrap_model_call = _noop_awrap


_neutralize_deepagents_builtins()


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
) -> Any:
    """Create a deepagents-powered search agent graph.

    This is the single loop the entire Harness revolves around. The Harness
    middleware (Context → Sensor → Extraction) is composed as the outermost
    middleware via ``build_layered_stack``.

    Args:
        model: LLM (BaseChatModel).
        tools: LangChain tools.
        system_prompt: Backbone system prompt.
        middleware: AgentMiddleware instances, in layer order.
        subagents: SubAgent specs (a disabled ``general-purpose`` stub is
            auto-inserted to suppress deepagents' default).
        skills: Paths to skill .md files for SkillsMiddleware.
        backend: Code execution / filesystem sandbox backend.
        checkpointer: LangGraph checkpointer (defaults to in-memory).
        state_schema: Custom state schema.
        name: Agent name for logging.

    Returns:
        Compiled LangGraph StateGraph.
    """
    from deepagents import create_deep_agent
    from deepagents.middleware._tool_exclusion import _ToolExclusionMiddleware

    if checkpointer is None:
        checkpointer = MemorySaver()

    prompt = system_prompt or "You are a search agent."

    # Stub `general-purpose` subagent: presence (by name) prevents deepagents
    # from auto-injecting its default one. `tools=[]` makes the stub a no-op
    # even if invoked — which can't happen since `task` is stripped below.
    effective_subagents: list[Any] = list(subagents) if subagents else []
    if not any(s.get("name") == "general-purpose" for s in effective_subagents):
        effective_subagents.insert(0, {
            "name": "general-purpose",
            "description": "(disabled in SearchOS — use the orchestrator's dispatch instead)",
            "system_prompt": "",
            "tools": [],
        })

    # Strip every tool deepagents auto-injects via its default middleware
    # stack — SearchOS already has purpose-built replacements and doesn't
    # want the LLM wandering into deepagents' virtual filesystem, shell
    # execute, or scratchpad todo list. We keep the middleware installed
    # (deepagents wires state/backend through it); we just filter the tools
    # off the model-facing list.
    _DEEPAGENTS_INJECTED_TOOLS = frozenset({
        "task",                  # SubAgentMiddleware
        "write_todos",           # TodoListMiddleware
        "compact_conversation",  # SummarizationMiddleware
        "ls", "read_file", "write_file", "edit_file",
        "glob", "grep", "execute",   # FilesystemMiddleware
    })
    effective_middleware: list[Any] = list(middleware) + [
        _ToolExclusionMiddleware(excluded=_DEEPAGENTS_INJECTED_TOOLS),
    ]

    graph = create_deep_agent(
        model=model,
        tools=list(tools),
        system_prompt=prompt,
        middleware=effective_middleware,
        subagents=effective_subagents,
        skills=skills,
        backend=backend,
        checkpointer=checkpointer,
        context_schema=state_schema,
        name=name,
    )

    logger.info(
        "Created search agent graph '%s' with %d tools, %d middleware, %s skills",
        name, len(tools), len(middleware), len(skills) if skills else 0,
    )
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
_alias_resolver_model_var: ContextVar[BaseChatModel | None] = ContextVar(
    "so_orch_alias_resolver", default=None
)
_sub_agent_model_var: ContextVar[BaseChatModel | None] = ContextVar(
    "so_orch_sub_agent", default=None
)
_skill_runtime_model_var: ContextVar[BaseChatModel | None] = ContextVar(
    "so_orch_skill_runtime", default=None
)
_skill_evolver_model_var: ContextVar[BaseChatModel | None] = ContextVar(
    "so_skill_evolver_model", default=None,
)
# "post_mortem" role model — distills FailureMemory records from failed
# sub-agent traces. When None, post-mortems silently skip.
_post_mortem_model_var: ContextVar[BaseChatModel | None] = ContextVar(
    "so_post_mortem_model", default=None,
)
# Per-session post-mortem fire counter. ``list[int]`` so the trigger hook
# can mutate in place across awaits.
_post_mortem_count_var: ContextVar[list[int] | None] = ContextVar(
    "so_post_mortem_count", default=None,
)
# Live post-mortem coroutine handles. Kept in a list (not task_pool) so they
# are isolated from the scheduler / check_agents "is the pool empty?" logic,
# but the harness drain phase can still await them so their
# atomic_update_state writes land before the workspace closes.
_post_mortem_tasks_var: ContextVar[list[Any] | None] = ContextVar(
    "so_post_mortem_tasks", default=None,
)
_skill_registry_var: ContextVar[Any] = ContextVar("so_orch_skills", default=None)
_trajectory_logger_var: ContextVar[Any] = ContextVar("so_orch_traj", default=None)
_conversation_logger_var: ContextVar[Any] = ContextVar("so_orch_conv", default=None)
_query_var: ContextVar[str] = ContextVar("so_orch_query", default="")

_task_pool_var: ContextVar[dict[str, Any] | None] = ContextVar("so_orch_task_pool", default=None)
_completed_var: ContextVar[dict[str, Any] | None] = ContextVar("so_orch_completed", default=None)
_agent_graph_var: ContextVar[dict[str, dict[str, Any]] | None] = ContextVar(
    "so_orch_agent_graphs", default=None
)
_granularity_hints_var: ContextVar[list[dict[str, Any]] | None] = ContextVar(
    "so_orch_granularity_hints", default=None
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


def _pop_granularity_hints() -> list[dict[str, Any]]:
    """Scheduler's drain-and-clear hook for pending granularity hints."""
    hints = _granularity_hints_var.get()
    if hints is None:
        return []
    out = list(hints)
    hints.clear()
    return out


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
    def alias_resolver_model(self) -> BaseChatModel | None:
        return _alias_resolver_model_var.get()

    @property
    def sub_agent_model(self) -> BaseChatModel | None:
        return _sub_agent_model_var.get()

    @property
    def skill_runtime_model(self) -> BaseChatModel | None:
        return _skill_runtime_model_var.get()

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
                "Orchestrator task pool not initialized. "
                "Call set_orchestrator_context() first."
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
    alias_resolver_model: BaseChatModel | None = None,
    sub_agent_model: BaseChatModel | None = None,
    skill_runtime_model: BaseChatModel | None = None,
    skill_evolver_model: BaseChatModel | None = None,
    post_mortem_model: BaseChatModel | None = None,
    conversation_logger: Any = None,
    query: str = "",
    scheduler_task_allowlist: set[str] | None = None,
) -> None:
    """Bind runtime context for orchestrator tools in the current task."""
    _workspace_var.set(workspace)
    _model_var.set(model)
    _judge_model_var.set(judge_model)
    _extraction_model_var.set(extraction_model)
    _alias_resolver_model_var.set(alias_resolver_model)
    _sub_agent_model_var.set(sub_agent_model)
    _skill_runtime_model_var.set(skill_runtime_model)
    _skill_evolver_model_var.set(skill_evolver_model)
    _post_mortem_model_var.set(post_mortem_model)
    _skill_registry_var.set(skill_registry)
    _trajectory_logger_var.set(trajectory_logger)
    _conversation_logger_var.set(conversation_logger)
    _query_var.set(query)
    _task_pool_var.set({})
    _completed_var.set({})
    _agent_graph_var.set({})
    _granularity_hints_var.set([])
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
    _scheduler_var.set(Scheduler(task_allowlist=scheduler_task_allowlist))
    _budget_exhausted_var.set([False])
