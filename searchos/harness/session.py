"""Route simple searches and research through a shared evidence runtime."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from contextlib import aclosing
from pathlib import Path
from typing import Any

from langchain_core.language_models import BaseChatModel

from searchos.config.run_config import EffectiveRunConfig, activate_run_config
from searchos.config.settings import settings
from searchos.harness.answer_stream import AnswerStreamEmitter
from searchos.harness.steering import SteerQueue
from searchos.skills.catalog.registry import SkillRegistry
from searchos.socm import SearchState, WorkspaceManager

logger = logging.getLogger(__name__)

# Module-level registry for background skill-evolution tasks.
_PENDING_EVOLUTIONS: set[asyncio.Task[None]] = set()


def _evidence_backed_coverage(state: SearchState) -> float:
    """Auxiliary progress: cells with any evidence / total cells."""
    cells = state.coverage_map.cells
    if not cells:
        return 0.0
    backed = sum(1 for c in cells.values() if c.supporting_evidence_ids)
    return backed / len(cells)


def _frontier_progress(state: SearchState) -> float:
    """Auxiliary progress: resolved frontier tasks / total frontier tasks."""
    total = len(state.frontier.questions)
    if not total:
        return 0.0
    return state.frontier.resolved_count / total


def follow_up_inspect_message(state: SearchState):
    """Remind a follow-up turn to read tables only when needed values are missing."""
    tables = getattr(getattr(state, "coverage_map", None), "tables", None) or {}
    if not tables:
        return None
    from langchain_core.messages import HumanMessage

    names = ", ".join(list(tables)[:2])
    return HumanMessage(
        content=(
            f"Follow-up over existing tables ({names}): if this question needs specific "
            "rows or fields not clearly present in the latest SOCM update or recent tool "
            "results, call read_table (with_values=true; attribute/value_counts/cursor as "
            "needed) before answering. Use read_evidence for citations or contested values. "
            "If SOCM/tool results already contain the needed values, answer directly. "
            "Dispatch search only for missing source facts."
        ),
        additional_kwargs={"sf_synthetic": True, "sf_kind": "follow_up_inspect"},
    )


def _premature_end_reason(workspace: WorkspaceManager, control: Any) -> str | None:
    """Decide whether the orchestrator's no-tool-call exit left work behind.

    The ReAct loop ends whenever the model emits a message without tool
    calls — including degenerate ones where the intended action is written
    as plain text. Returns a resume reason when structural evidence says
    the session isn't done, or None when the end is legitimate (harness
    initiated the stop, or nothing actionable remains).
    """
    if control.stopped:
        return None
    reasons: list[str] = []
    try:
        from searchos.agents.runtime import _ctx
        running = sorted(aid for aid, t in _ctx.task_pool.items() if not t.done())
    except Exception:
        running = []
    if running:
        reasons.append(
            f"{len(running)} sub-agent(s) still running ({', '.join(running)})"
        )
    try:
        state = workspace.load_state()
    except Exception:
        state = None
    if state is not None:
        from searchos.socm import FrontierTaskStatus
        open_count = sum(
            1 for q in state.frontier.questions
            if q.status in (FrontierTaskStatus.PENDING, FrontierTaskStatus.BLOCKED)
        )
        if open_count:
            reasons.append(f"{open_count} frontier task(s) still open")
        empty = state.coverage_map.empty_tables
        if empty:
            reasons.append(
                "table(s) declared but still have 0 rows: "
                + ", ".join(f"`{t}`" for t in empty)
            )
    if not reasons:
        return None
    return "; ".join(reasons)


def _premature_end_nudge(reason: str) -> str:
    return f"""Pending research work: {reason}.
Collect running agents or continue actionable tasks. If progress is blocked, report the supported findings and the remaining limitation."""


async def wait_for_all_evolutions(timeout: float | None = None) -> None:
    """Drain all outstanding background skill-evolution tasks.

    Call this before shutting down the event loop to avoid `Task was destroyed
    but it is pending!` warnings and to ensure skill-library writes complete.
    """
    if not _PENDING_EVOLUTIONS:
        return
    pending = list(_PENDING_EVOLUTIONS)
    logger.info("Waiting for %d background skill-evolution task(s)...", len(pending))
    try:
        if timeout is None:
            await asyncio.gather(*pending, return_exceptions=True)
        else:
            await asyncio.wait_for(
                asyncio.gather(*pending, return_exceptions=True),
                timeout=timeout,
            )
    except asyncio.TimeoutError:
        logger.warning("Evolution drain timed out after %.1fs; %d task(s) still running",
                       timeout, len(_PENDING_EVOLUTIONS))


async def close_browser_service() -> None:
    """Tear down the process-wide BrowserService (closes Chromium when crawl4ai
    backend is active). Safe to call multiple times; callers should invoke this
    once before process exit so Playwright doesn't leak background tasks.
    """
    try:
        from searchos.tools.simple_browser.fetchers.base import BrowserService
    except Exception:
        return
    inst = BrowserService._instance  # type: ignore[attr-defined]
    if inst is None:
        return
    try:
        await inst.close()
    except Exception:  # noqa: BLE001 — shutdown must not crash callers
        logger.debug("BrowserService close raised", exc_info=True)
    finally:
        BrowserService.reset()


class SearchSession:
    """Share sources, evidence, and finalization across direct search and research."""

    def __init__(
        self,
        *,
        max_time_s: int | None = None,
        skill_registry: SkillRegistry | None = None,
        workspace_root: str = settings.workspace_root,
        skill_library_path: str = "",
        skill_exclude: list[str] | None = None,
        model_overrides: dict[str, BaseChatModel] | None = None,
        skip_synthesis: bool | None = None,
        run_config: EffectiveRunConfig | None = None,
    ) -> None:
        """按 settings 中的角色选择模型，允许通过 model_overrides 覆盖。

        max_time_s 为单次会话覆盖；None 在每轮开始读取 settings，0 表示不限时。
        """
        from searchos.config.models import get_model_for

        overrides = model_overrides or {}

        def _resolve(role: str) -> BaseChatModel:
            return overrides.get(role) or get_model_for(role)

        self._model = _resolve("orchestrator")
        self._judge_model = _resolve("judge")
        self._extraction_model = _resolve("extraction")
        self._synthesis_model = _resolve("synthesis")
        self._skill_evolver_model = _resolve("skill_evolver")
        self._post_mortem_model = _resolve("post_mortem")
        # Keep the sub-agent model bound to the session's token tracker.
        self._sub_agent_model = _resolve("sub_agent")

        role_models = {
            "orchestrator": self._model,
            "judge": self._judge_model,
            "extraction": self._extraction_model,
            "synthesis": self._synthesis_model,
            "skill_evolver": self._skill_evolver_model,
            "post_mortem": self._post_mortem_model,
            "sub_agent": self._sub_agent_model,
        }
        self._model_distribution: dict[str, dict[str, str]] = {}
        for role, profile_name in settings.roles.items():
            model = role_models.get(role)
            profile = settings.profiles.get(profile_name)
            model_name = (
                getattr(model, "model_name", None) if model is not None else None
            ) or (
                getattr(model, "model", None) if model is not None else None
            ) or (profile.model if profile else "")
            self._model_distribution[role] = {
                "profile": profile_name,
                "model": str(model_name),
                "provider": (
                    profile.provider
                    if profile else model.__class__.__name__ if model is not None else "unknown"
                ),
            }

        self._max_time_s = max_time_s
        self._skill_registry = skill_registry
        self._workspace_root = workspace_root
        self._skill_library_path = skill_library_path or settings.skill_library_path
        self._skill_exclude = list(skill_exclude or [])
        self._skip_synthesis = skip_synthesis if skip_synthesis is not None else settings.skip_synthesis
        self._run_config = run_config or EffectiveRunConfig.from_settings()

    def ensure_skill_registry(self) -> SkillRegistry:
        """Build + load the skill registry if not already done (idempotent;
        ``load_directory`` is mtime-cached). Exposed so the interactive TUI can
        enumerate the access-skill catalog before the first run."""
        from pathlib import Path
        if self._skill_registry is None:
            self._skill_registry = SkillRegistry(excluded=self._skill_exclude)
        elif self._skill_exclude:
            self._skill_registry.set_excluded(self._skill_exclude)
        lib_path = Path(self._skill_library_path)
        if lib_path.exists():
            self._skill_registry.load_directory(lib_path)
        return self._skill_registry

    async def run(self, *args: Any, **kwargs: Any) -> SearchResult:
        """Execute with the immutable configuration captured at construction."""
        from searchos.network import network_context
        self._conversation_logger = None
        try:
            with activate_run_config(self._run_config), network_context():
                return await self._run_impl(*args, **kwargs)
        finally:
            if self._conversation_logger is not None:
                self._conversation_logger.flush()

    def _build_research_graph(
        self, *, state, workspace, query, fixed_schema, targeted_repair_mode,
        orchestrator_deny, follow_up, conversation_history, traj_logger, conv_logger,
        orch_budget, orch_control, steer_queue,
    ):
        """Build the research graph on demand, leaving simple searches without an orchestrator."""
        from datetime import datetime as _dt

        from searchos.agents.orchestrator import get_orchestrator_tools
        from searchos.agents.orchestrator.catalog import (
            _is_agent_enabled,
            generate_agent_catalog_text,
        )
        from searchos.agents.orchestrator.prompt import build_orchestrator_prompt
        orchestrator_tools = get_orchestrator_tools(source_mode=(state.source_scope or {}).get("mode", ""))
        if fixed_schema:
            orchestrator_tools = [
                tool for tool in orchestrator_tools
                if getattr(tool, "name", "") not in {"create_schema", "add_columns"}
            ]
        if targeted_repair_mode:
            repair_tool_allowlist = {
                "enqueue_tasks",
                "check_agents",
                "stop_task",
                "read_table",
            }
            orchestrator_tools = [
                tool for tool in orchestrator_tools
                if getattr(tool, "name", "") in repair_tool_allowlist
            ]
        from searchos.agents.toolset_render import render_toolset

        # Inject ALL orchestrator-layer skills into the playbook directly — no
        # router LLM call. Skipped entirely when enable_skills=False so the
        # orchestrator cannot see or use skills.
        if settings.enable_skills and "web" not in state.source_scope.get("unavailable_sources", {}):
            from searchos.skills.catalog.discovery import render_playbook
            from searchos.skills.core.models import SkillCategory
            orch_candidates = self._skill_registry.list_by_category(SkillCategory.ORCHESTRATOR)
            if orchestrator_deny:
                orch_candidates = [
                    s for s in orch_candidates if s.meta.name not in orchestrator_deny
                ]
            orchestrator_playbook = render_playbook(orch_candidates)

            # 子 agent 按当前检索需求发现技能；权限仍由上面的 policy 约束。
            skill_catalog = """Search agents discover Access and Strategy skills for their current retrieval need, then load the selected skill before use. Give them the task, source hints and acceptance criteria; include known skill recommendations when useful."""
        else:
            orchestrator_playbook = ""
            skill_catalog = ""

        scope = state.source_scope or {}
        documents = scope.get("documents", [])
        local_sources = "\n".join(
            f"""- {record['relative_path']} (document_id={record['document_id']})"""
            for record in documents
        )
        if scope.get("library_id"):
            selection = "readable library snapshot" if scope.get("selection") == "library" else "selected documents"
            local_sources = f"""Current library: {scope['library_id']}; scope: {selection}.
Readable documents: {len(documents)}.
{local_sources}"""
        system_prompt = build_orchestrator_prompt(
            initial_planning_effort=self._run_config.initial_planning_effort,
            agent_catalog=generate_agent_catalog_text(),
            skill_catalog=skill_catalog,
            max_dispatches=settings.orch_max_dispatches,
            max_searches_per_agent=settings.max_searches_per_sub_agent,
            max_execs_per_agent=settings.max_execs_per_sub_agent,
            max_search_agents_per_session=settings.max_search_agents_per_session,
            # Date-only: minute precision forks the prompt-cache prefix
            # across sessions started in different minutes.
            current_time=_dt.now().strftime("%Y-%m-%d"),
            orch_toolset=render_toolset(orchestrator_tools, header="## Available Tools"),
            enable_explore=_is_agent_enabled("explore_agent"),
            explore_on_start=self._run_config.explore_on_start and not targeted_repair_mode,
            orchestrator_playbook=orchestrator_playbook,
            follow_up=follow_up or bool(conversation_history),
            fixed_schema=fixed_schema,
            targeted_repair=targeted_repair_mode,
            source_mode=(state.source_scope or {}).get("mode", ""),
            local_sources=local_sources,
            source_limitations="\n".join(state.source_scope.get("unavailable_sources", {}).values()),
        )
        conv_logger.register_sub_agent(
            agent_name="orchestrator",
            parent="",
            task=query,
            system_prompt=system_prompt,
            agent_type="orchestrator",
        )

        from deepagents.backends import FilesystemBackend

        from searchos.harness.middleware.pipelines import orchestrator_pipeline

        def stop_dispatch():
            from searchos.agents.runtime import _ctx

            _ctx.mark_budget_exhausted()

        from searchos.agents.runtime import _ctx

        orch_backend = FilesystemBackend(
            root_dir=str(workspace.path / "orchestrator_logs"),
            virtual_mode=False,
        )

        graph = orchestrator_pipeline(
            model=self._model,
            tools=orchestrator_tools,
            system_prompt=system_prompt,
            workspace=workspace, budget=orch_budget, control=orch_control,
            agent_graphs=_ctx.agent_graphs, task_pool=_ctx.task_pool,
            on_exhausted=stop_dispatch, trajectory_logger=traj_logger,
            conversation_logger=conv_logger,
            backend=orch_backend,
            name="orchestrator",
            steer_queue=steer_queue,
        )
        from searchos.harness.steering import find_follow_up_turns

        return graph, find_follow_up_turns(graph.middleware)

    async def _run_impl(
        self,
        query: str,
        *,
        session_id: str | None = None,
        initial_state: SearchState | None = None,
        conversation_history: list[dict[str, str]] | None = None,
        on_event: "Callable[[dict], None] | None" = None,
        steer_queue: SteerQueue | None = None,
        access_only: "set[str] | None" = None,
        access_deny: "set[str] | None" = None,
        strategy_deny: "set[str] | None" = None,
        orchestrator_deny: "set[str] | None" = None,
        trusted_domains: "list[str] | None" = None,
        excluded_domains: "list[str] | None" = None,
        follow_up: bool = False,
        fixed_schema: bool = False,
        targeted_repair_task_ids: "set[str] | None" = None,
        targeted_repair_cells: "list[str] | None" = None,
    ) -> SearchResult:
        """Execute a complete search session via Orchestrator pattern.

        ``conversation_history`` (optional): prior user and assistant messages.
        The current query is appended unchanged as a separate user message.

        ``steer_queue`` (optional): a queue the caller pushes live user
        follow-ups onto while the run is in flight. Immediate input replaces
        unfinished model generation or wakes report delivery; after_tool input
        waits for the current tool batch. Middleware commits each message once
        within the same graph. Neither mode cancels running sub-agents.

        ``access_only`` (optional) limits discovery and execution to these access
        skills. ``access_deny`` removes names before discovery and execution.
        Both let the interactive TUI's ``/skill`` command set the allowed scope.

        ``strategy_deny`` (optional): strategy-skill names hidden from the
        sub-agent catalog. ``orchestrator_deny`` (optional): orchestrator-skill
        names dropped from the orchestrator playbook. Both default to all-on;
        the ``/skill`` picker passes the names the user has unchecked.

        ``trusted_domains`` rank matching search results first while
        ``excluded_domains`` remove matching results and block direct opens.
        Both controls are task-local and inherited by spawned sub-agents.

        ``fixed_schema`` locks a schema already present in ``initial_state``.
        The orchestrator can discover/add rows and fill cells, but cannot call
        ``create_schema`` to replace or extend the experimental table design.
        """
        start_time = time.time()
        targeted_repair_mode = (
            targeted_repair_cells is not None
            or targeted_repair_task_ids is not None
        )

        # --- Workspace ---
        workspace = WorkspaceManager(self._workspace_root, session_id)
        workspace.create()
        self._active_workspace = workspace
        from searchos.harness.telemetry.trajectory import TrajectoryLogger
        traj_logger = TrajectoryLogger(workspace.trajectory_path)
        if on_event is not None:
            traj_logger.add_listener(on_event)
        traj_logger.log_phase("loading_skills")

        # --- Token tracking (per-run, ContextVar-backed) ---
        from searchos.harness.telemetry.usage import start_tracking
        token_usage = start_tracking(
            usage_path=workspace.path / settings.output_dir / "llm_usage.jsonl",
        )
        from searchos.tools.simple_browser.fetchers.cache import (
            start_tracking as start_browser_tracking,
        )
        browser_usage = start_browser_tracking()

        # --- Reset cross-agent browser state for this fresh session ---
        from searchos.tools.simple_browser.session import reset_browser, set_source_controls
        reset_browser()
        source_controls = set_source_controls(trusted_domains, excluded_domains)

        # --- State ---
        state = initial_state or SearchState(intent=query)
        if state.source_scope is None:
            state.source_scope = {"mode": "web", "documents": []}
        if state.source_scope.get("mode") == "local" and (trusted_domains or excluded_domains):
            raise ValueError("Local mode does not accept Web domain controls")
        if not state.intent:
            state.intent = query

        workspace.save_state(state)
        from searchos.tools.search_state import _source_scope_var
        _source_scope_var.set(state.source_scope)

        # --- Skill registry ---
        from searchos.skills.names import canonical_skill_names
        access_only = canonical_skill_names(access_only) if access_only is not None else None
        access_deny = canonical_skill_names(access_deny or ())
        strategy_deny = canonical_skill_names(strategy_deny or ())
        orchestrator_deny = canonical_skill_names(orchestrator_deny or ())
        from searchos.tools.skills.catalog import _skill_access_policy_var
        _skill_access_policy_var.set({
            "access_only": None if access_only is None else frozenset(access_only),
            "access_deny": frozenset(access_deny or ()),
            "strategy_deny": frozenset(strategy_deny or ()),
            "orchestrator_deny": frozenset(orchestrator_deny or ()),
        })
        await asyncio.to_thread(self.ensure_skill_registry)
        traj_logger.log_phase("loading_skills", "done")

        # --- Conversation logger (full LLM messages) ---
        from searchos.harness.telemetry.conversation import (
            ConversationLogger,
            langchain_msg_to_conversation_msgs,
        )
        conv_logger = ConversationLogger(workspace.conversation_path)
        self._conversation_logger = conv_logger
        # Follow-up turns reuse the same session workspace; load prior turns
        # from disk so this turn's messages append instead of overwriting.
        conv_logger.hydrate()

        # --- Log task_start event ---
        from datetime import datetime, timezone
        trace_offset = workspace.trajectory_path.stat().st_size if workspace.trajectory_path.exists() else 0
        traj_logger._append_raw({
            "type": "task_start",
            "source_mode": (state.source_scope or {}).get("mode", "web"),
            "session_id": workspace.session_id,
            "query": query,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        traj_logger._append_raw({
            "type": "run_config",
            "skills": {
                "access_mode": "only" if access_only is not None else "router",
                "access_only": sorted(access_only or ()),
                "access_deny": sorted(access_deny or ()),
                "strategy_deny": sorted(strategy_deny or ()),
                "orchestrator_deny": sorted(orchestrator_deny or ()),
            },
            "trusted_domains": list(source_controls.trusted_domains),
            "excluded_domains": list(source_controls.excluded_domains),
            "explore": {
                "batch_enabled": settings.enable_explore_batch,
                "max_waves": self._run_config.explore_max_waves,
            },
            "effective_run_config": self._run_config.snapshot(),
            "models": self._model_distribution,
            "fixed_schema": fixed_schema,
        })

        # --- Set up orchestrator tools context ---
        from searchos.agents.runtime import set_orchestrator_context
        from searchos.tools.search_state import set_workspace
        from searchos.tools.simple_browser.session import _provider, set_browser_provider

        set_workspace(workspace)
        set_orchestrator_context(
            workspace=workspace,
            model=self._model,
            skill_registry=self._skill_registry,
            trajectory_logger=traj_logger,
            conversation_logger=conv_logger,
            judge_model=self._judge_model,
            extraction_model=self._extraction_model,
            sub_agent_model=self._sub_agent_model,
            synthesis_model=self._synthesis_model,
            skill_evolver_model=self._skill_evolver_model,
            post_mortem_model=self._post_mortem_model,
            query=query,
            steer_queue=steer_queue,
            scheduler_task_allowlist=targeted_repair_task_ids,
            repair_target_allowlist=(
                set(targeted_repair_cells or ()) if targeted_repair_mode else None
            ),
        )
        if _provider is not None:
            set_browser_provider(_provider)


        from searchos.harness.middleware.sensor.core.run_state import BudgetState, ControlState

        # Orchestrator never calls `search` — bound by iterations + sensors.
        orch_budget = BudgetState(
            max_queries=0,
            max_iterations=settings.orch_max_iterations,
            max_time_s=(settings.default_max_time_s
                        if self._max_time_s is None else self._max_time_s),
        )
        # Router, simple worker and research share this session deadline.
        orch_budget._start_ts = start_time
        orch_control = ControlState()
        steering = None
        graph = None

        # --- Run Orchestrator ---
        logger.info(
            "Starting Orchestrator: %s (session=%s)",
            query[:60],
            workspace.session_id,
        )
        final_state = None
        execution_error = ""
        finalization_reason = ""
        seen_message_ids = set()

        pending_tool_calls: dict[str, dict[str, Any]] = {}
        phase_tracker = _PhaseTracker(token_usage)
        answer_stream = AnswerStreamEmitter(
            traj_logger._append_raw,
            stream_prefix=f"web-{workspace.session_id}",
        )
        committed_final_answer = ""
        cancelled = False  # set when the user interrupts (Ctrl-C → task.cancel)
        simple_outcome = None
        route = None
        initial_query_logged = False
        try:
            import json

            from langchain_core.messages import AIMessage

            from searchos.harness.routing import select_route
            from searchos.harness.simple_search import run_simple_search

            def remaining_time():
                return max(0.0, orch_budget.max_time_s - (time.time() - start_time)) if orch_budget.max_time_s else None

            traj_logger.log_phase("routing")
            route = await select_route(
                model=self._model, query=query, state=state,
                execution_path=self._run_config.execution_path,
                follow_up=follow_up or bool(conversation_history), fixed_schema=fixed_schema,
                targeted_repair=targeted_repair_mode, table_export=self._skip_synthesis,
                remaining_time_s=remaining_time(), trajectory_logger=traj_logger,
            )
            traj_logger.log_phase("routing", "done")
            routing_record = {"execution_path": self._run_config.execution_path, **route.model_dump()}
            workspace.write_output("routing.json", json.dumps(routing_record, ensure_ascii=False, indent=2))
            if self._run_config.execution_path != "unified" and not (follow_up or conversation_history or targeted_repair_mode):
                state.research_plan = route.plan()
                workspace.save_state(state)
            if route.path == "simple":
                from searchos.harness.telemetry.conversation import ConversationMessage

                conv_logger.register_sub_agent(
                    agent_name="orchestrator", parent="", task=query,
                    agent_type="search_session",
                )
                conv_logger.log(ConversationMessage(role="user", content=query))
                initial_query_logged = True

                def record_simple_steer(message):
                    for entry in langchain_msg_to_conversation_msgs(message):
                        conv_logger.log(entry)

                remaining = remaining_time()
                simple_time = min(120.0, remaining) if remaining is not None else 120.0
                simple_outcome = await run_simple_search(
                    workspace=workspace, query=query,
                    evidence_obligations=route.evidence_obligations,
                    remaining_time_s=simple_time, steer_queue=steer_queue,
                    trajectory_logger=traj_logger,
                    on_steer_delivery=record_simple_steer,
                )
                final_state = {"messages": [AIMessage(content=simple_outcome.answer)]}
                routing_record["final_path"] = "simple"
                workspace.write_output("routing.json", json.dumps(routing_record, ensure_ascii=False, indent=2))

            if simple_outcome is None:
                state = workspace.load_state()
                graph, steering = self._build_research_graph(
                    state=state, workspace=workspace, query=query, fixed_schema=fixed_schema,
                    targeted_repair_mode=targeted_repair_mode, orchestrator_deny=orchestrator_deny,
                    follow_up=follow_up, conversation_history=conversation_history,
                    traj_logger=traj_logger, conv_logger=conv_logger,
                    orch_budget=orch_budget, orch_control=orch_control, steer_queue=steer_queue,
                )
                if targeted_repair_mode:
                    from searchos.agents.runtime import _scheduler

                    dispatch_result = None
                    if targeted_repair_task_ids:
                        dispatch_result = await _scheduler().drain_ready_tasks()
                    traj_logger._append_raw({
                        "type": "harness",
                        "kind": "targeted_repair_delegated",
                        "task_ids": sorted(targeted_repair_task_ids or ()),
                        "target_cells": list(targeted_repair_cells or []),
                        "dispatch": dispatch_result,
                    })


                model_name = getattr(self._model, "model_name", None) or getattr(self._model, "model", "") or ""
                # SOCMContextMiddleware supplies live state during each model turn.
                astream_config = {
                    "configurable": {"thread_id": workspace.session_id},
                    "run_name": f"orchestrator:{workspace.session_id}",
                    "tags": [
                        f"session:{workspace.session_id}",
                    ],
                    "metadata": {
                        "session_id": workspace.session_id,
                        "query": query,
                        "model": str(model_name),
                    },
                }
                from langchain_core.messages import HumanMessage

                history_messages = [
                    {**message, "id": f"history-{index}"}
                    for index, message in enumerate(conversation_history or [])
                ]
                input_payload: dict[str, Any] = {"messages": [
                    *history_messages,
                    {"role": "user", "content": query, "id": "routed-query"},
                ]}
                # 历史已经持久保存；本轮日志和界面从当前用户消息开始追加。
                seen_message_ids.update(message["id"] for message in history_messages)
                if targeted_repair_mode:
                    from searchos.socm.refs import cell_ref
                    targets = json.dumps([cell_ref(key) for key in targeted_repair_cells or []], ensure_ascii=False)
                    repair_context = f"""Repair only these coverage cells: {targets}.
You own the repair plan and dispatch. Split these cells into focused retrieval tasks with enqueue_tasks using the current Agent Catalog; set target_table and target_cells on every task as CellRef objects {{table_id, key: [PK values], attribute}}. Do not create or change schemas, add entities, or expand beyond this allowlist. Keep dispatching and reviewing incoming reports until the selected cells are repaired or the available evidence is exhausted, then summarize what changed."""
                    input_payload["messages"].append(HumanMessage(
                        content=repair_context,
                        additional_kwargs={"sf_synthetic": True, "sf_kind": "targeted_repair"},
                    ))
                elif follow_up or conversation_history:
                    inspect = follow_up_inspect_message(state)
                    if inspect is not None:
                        input_payload["messages"].append(inspect)
                resume_attempts = 0
                # Same thread_id on every astream call → each resume continues
                # the checkpointed conversation instead of starting over.
                while True:
                    # Close the previous stream and flush its checkpoint before
                    # re-entering; otherwise the next call can lose ToolMessages.
                    async with aclosing(graph.astream(
                        input_payload,
                        config=astream_config,
                        stream_mode=["values"],
                    )) as stream:
                        async for stream_kind, stream_event in stream:
                            event = stream_event
                            if not isinstance(event, dict):
                                continue
                            final_state = event
                            if "messages" not in event:
                                continue
                            msgs = event["messages"]
                            # 压缩会缩短消息列表；按身份记录，保留压缩后的新回复。
                            new_msgs = []
                            for msg in msgs:
                                message_id = getattr(msg, "id", None) or id(msg)
                                if message_id not in seen_message_ids:
                                    seen_message_ids.add(message_id)
                                    new_msgs.append(msg)

                            for msg in new_msgs:
                                # Record to conversation logger
                                if not (initial_query_logged and getattr(msg, "id", None) == "routed-query"):
                                    for conv_msg in langchain_msg_to_conversation_msgs(msg):
                                        # 只有最终交付记录可以成为该轮回答。
                                        if conv_msg.role == "assistant":
                                            conv_msg.metadata["phase"] = "progress"
                                        conv_logger.log(conv_msg)

                                # Record Orchestrator tool events to trajectory
                                _log_orchestrator_tool_events(
                                    msg, traj_logger, pending_tool_calls,
                                )

                                # Track token phase transitions
                                phase_tracker.observe(msg)

                                # Stream the orchestrator's own reasoning/content to the
                                # live UI (Claude-Code-style per-turn output).
                                if on_event is not None and getattr(msg, "type", None) == "ai":
                                    _c = getattr(msg, "content", "") or ""
                                    if isinstance(_c, list):
                                        _c = " ".join(
                                            b.get("text", "") for b in _c
                                            if isinstance(b, dict) and b.get("type") == "text"
                                        )
                                    _ex = getattr(msg, "additional_kwargs", None) or {}
                                    _r = _ex.get("reasoning_content", "") if isinstance(_ex, dict) else ""
                                    if (_c or "").strip() or (_r or "").strip():
                                        try:
                                            on_event({"type": "assistant", "agent": "orchestrator",
                                                      "content": _c or "", "reasoning": _r or ""})
                                        except Exception:
                                            pass
                                    # Surface the tool call the instant it's emitted —
                                    # don't wait for the result (which merges in a later
                                    # astream batch, one step behind). The live UI shows
                                    # the call now and back-fills the result by id.
                                    for _tc in (getattr(msg, "tool_calls", None) or []):
                                        _name = (_tc.get("name", "") if isinstance(_tc, dict)
                                                 else getattr(_tc, "name", ""))
                                        if not _name:
                                            continue
                                        _tcid = (_tc.get("id", "") if isinstance(_tc, dict)
                                                 else getattr(_tc, "id", ""))
                                        _targs = (_tc.get("args", {}) if isinstance(_tc, dict)
                                                  else getattr(_tc, "args", {}))
                                        try:
                                            on_event({
                                                "type": "orchestrator_tool_call",
                                                "tool": _name, "tool_call_id": _tcid,
                                                "args": _full_args(_targs),
                                            })
                                        except Exception:
                                            pass

                    reason = _premature_end_reason(workspace, orch_control)
                    if orch_control.stopped:
                        finalization_reason = orch_control.reason or "harness_stopped"
                    if (
                        reason is None
                        or resume_attempts >= settings.orch_premature_end_max_resumes
                    ):
                        if reason is not None:
                            finalization_reason = "premature_end_resumes_exhausted"
                            logger.warning(
                                "Orchestrator ended without a tool call and work "
                                "remains (%s), but resume budget is spent — "
                                "accepting the end.", reason,
                            )
                        break
                    resume_attempts += 1
                    logger.warning(
                        "Orchestrator ended without a tool call but work remains "
                        "(%s); resuming %d/%d",
                        reason, resume_attempts,
                        settings.orch_premature_end_max_resumes,
                    )
                    traj_logger._append_raw({
                        "type": "harness",
                        "kind": "premature_end_resume",
                        "reason": reason,
                        "attempt": resume_attempts,
                    })
                    input_payload = {
                        "messages": [
                            HumanMessage(
                                content=_premature_end_nudge(reason),
                                additional_kwargs={"sf_synthetic": True, "sf_kind": "pending_work"},
                            ),
                        ],
                    }

        except asyncio.CancelledError:
            # User interrupted (Ctrl-C). Skip the slow drain below — cancel
            # sub-agents fast and re-raise so no result/synthesis is produced.
            cancelled = True
            logger.info("Orchestrator run cancelled by user")
            raise
        except Exception as exc:
            if graph is None and simple_outcome is None:
                # Invalid graph/configuration remains a caller-visible setup error.
                raise
            execution_error = type(exc).__name__
            logger.error("Orchestrator execution failed", exc_info=True)
            traj_logger._append_raw({"type": "harness", "kind": "execution_failed",
                                     "error_type": execution_error})
        finally:
            answer_stream.finish()
            try:
                from searchos.agents.runtime import _ctx as _orch_ctx
                pending_pool = _orch_ctx.task_pool
            except Exception:
                pending_pool = {}
            undone = [t for t in pending_pool.values() if not t.done()]
            if undone and cancelled:
                # Interrupt path: cancel sub-agents immediately, short grace.
                logger.info("Cancelling %d sub-agent task(s) on interrupt", len(undone))
                for t in undone:
                    t.cancel()
                try:
                    await asyncio.wait_for(
                        asyncio.gather(*undone, return_exceptions=True),
                        timeout=5.0,
                    )
                except asyncio.TimeoutError:
                    pass
            elif undone:
                logger.info(
                    "Draining %d pending sub-agent task(s) before synthesis...",
                    len(undone),
                )
                try:
                    await asyncio.wait_for(
                        asyncio.gather(*undone, return_exceptions=True),
                        timeout=60.0,
                    )
                except asyncio.TimeoutError:
                    still_running = [t for t in undone if not t.done()]
                    logger.warning(
                        "Drain timed out after 60s; cancelling %d remaining "
                        "task(s). Their extractions will be lost.",
                        len(still_running),
                    )
                    for t in still_running:
                        t.cancel()
                    try:
                        await asyncio.wait_for(
                            asyncio.gather(*still_running, return_exceptions=True),
                            timeout=5.0,
                        )
                    except asyncio.TimeoutError:
                        pass
                except Exception:
                    logger.warning("Drain raised", exc_info=True)

            # Collectors have committed their reports and state; remove reaped
            # entries during final cleanup.
            for agent_id, task in list(pending_pool.items()):
                if task.done():
                    pending_pool.pop(agent_id, None)

            # Drain pending post-mortem coroutines so their
            # atomic_update_state writes land before the workspace
            # closes. fire-and-forget by design, but if the LAST
            # sub-agent return is also a trigger, the coroutine has
            # only milliseconds to finish before the process moves on
            # — without this wait the failure memory is silently lost.
            try:
                from searchos.agents.runtime import (
                    _post_mortem_tasks_var,
                )
                pm_tasks = list(_post_mortem_tasks_var.get() or [])
                pm_undone = [t for t in pm_tasks if not t.done()]
                if pm_undone and not cancelled:
                    logger.info(
                        "Draining %d pending post-mortem task(s)...",
                        len(pm_undone),
                    )
                    traj_logger._append_raw({
                        "type": "harness", "kind": "post_session_phase",
                        "phase": "post_mortem_drain",
                        "status": "start",
                        "pending_tasks": len(pm_undone),
                    })
                    try:
                        await asyncio.wait_for(
                            asyncio.gather(*pm_undone, return_exceptions=True),
                            timeout=70.0,
                        )
                    except asyncio.TimeoutError:
                        for t in pm_undone:
                            if not t.done():
                                t.cancel()
                    traj_logger._append_raw({
                        "type": "harness", "kind": "post_session_phase",
                        "phase": "post_mortem_drain",
                        "status": "done",
                    })
            except Exception:
                logger.debug("post-mortem drain raised", exc_info=True)

            elapsed = time.time() - start_time
            try:
                final_search_state = workspace.load_state()
                final_search_state.budget.elapsed_s = elapsed
                from searchos.agents.runtime import (
                    _session_search_count_var,
                )
                search_count_box = _session_search_count_var.get()
                final_search_state.budget.consumed_queries = (
                    search_count_box[0] if search_count_box else 0
                )
                final_search_state.budget.current_iteration = orch_budget.current_iteration
                final_search_state.budget.max_queries = orch_budget.max_queries
                final_search_state.budget.max_time_s = orch_budget.max_time_s
                final_search_state.budget.max_iterations = (
                    orch_budget.max_iterations
                )
                workspace.save_state(final_search_state)
            except Exception:
                logger.error("Failed to reload state for synthesis", exc_info=True)
                final_search_state = None

            if final_search_state is not None and not cancelled:
                try:
                    traj_logger._append_raw({
                        "type": "harness", "kind": "post_session_phase",
                        "phase": "finalization",
                        "status": "start",
                    })
                    if self._skip_synthesis:
                        _export_eval_table(
                            workspace=workspace,
                            state=final_search_state,
                            query=query,
                        )
                    else:
                        committed_final_answer = await _commit_final_answer(
                            workspace=workspace, state=final_search_state,
                            query=query, final_state=final_state, model=self._model,
                            execution_error=execution_error,
                            stop_reason=finalization_reason,
                            answer_stream=answer_stream, trajectory_logger=traj_logger,
                            conversation_logger=conv_logger,
                            follow_ups=steering.delivered if steering else (),
                            steering=steering,
                        )
                    traj_logger._append_raw({
                        "type": "harness", "kind": "post_session_phase",
                        "phase": "finalization",
                        "status": "done",
                    })
                except Exception as finalization_exc:
                    execution_error = execution_error or type(finalization_exc).__name__
                    logger.error(
                        "Harness finalization failed; preserving delivered answer",
                        exc_info=True,
                    )
                    try:
                        import json

                        workspace.write_output(
                            "finalization_error.json",
                            json.dumps({"query": query, "error_type": execution_error},
                                       ensure_ascii=False),
                        )
                    except Exception:
                        pass

        final_search_state = workspace.load_state()
        elapsed = time.time() - start_time
        final_search_state.budget.elapsed_s = elapsed
        workspace.save_state(final_search_state)

        # Extract messages
        final_messages: list[dict[str, Any]] = []
        if final_state and "messages" in final_state:
            for msg in final_state["messages"]:
                if hasattr(msg, "type") and hasattr(msg, "content"):
                    final_messages.append({
                        "role": msg.type,
                        "content": msg.content,
                    })
        if committed_final_answer and not any(
            message.get("role") in {"ai", "assistant"}
            and message.get("content") == committed_final_answer
            for message in final_messages
        ):
            final_messages.append({"role": "ai", "content": committed_final_answer})

        from searchos.harness.telemetry.recording import evidence_status_counts

        evidence_statuses = evidence_status_counts(final_search_state)
        result = SearchResult(
            query=query,
            session_id=workspace.session_id,
            workspace_path=str(workspace.path),
            search_state=final_search_state,
            eval_verdict="COMPLETE" if final_search_state.coverage_map.tables else "UNASSESSED",
            coverage_score=final_search_state.coverage_map.coverage_score,
            evidence_count=final_search_state.evidence_graph.node_count,
            total_queries=traj_logger.tool_counts.get("search", 0),
            total_steps=traj_logger.step_count,
            elapsed_s=elapsed,
            final_messages=final_messages,
            execution_error=execution_error,
        )
        result.evidence_active_count = evidence_statuses["active"]
        result.evidence_candidate_count = evidence_statuses["candidate"]
        result.extraction_pending_total = int(getattr(workspace, "extraction_pending_total", 0) or 0)
        result.extraction_rejection_counts = dict(
            getattr(workspace, "extraction_rejection_counts", {}) or {}
        )

        # Log task_complete event (with total + per-phase token usage)
        token_dict = token_usage.to_dict()
        # Main-loop roles only; middleware one-shot calls are excluded
        # (their numbers stay visible in by_role).
        cache_hit_rate = token_usage.cache_hit_rate
        token_dict["cache_hit_rate"] = (
            round(cache_hit_rate, 4) if cache_hit_rate is not None else None
        )
        token_dict["by_role"] = token_usage.by_role
        token_phases = phase_tracker.finalize()
        traj_logger._append_raw({
            "type": "task_complete",
            "execution_error": execution_error,
            "session_id": workspace.session_id,
            "coverage": result.coverage_score,
            "evidence_backed_coverage": _evidence_backed_coverage(final_search_state),
            "frontier_progress": _frontier_progress(final_search_state),
            "evidence_count": result.evidence_count,
            "evidence_active_count": getattr(result, "evidence_active_count", 0),
            "evidence_candidate_count": getattr(result, "evidence_candidate_count", 0),
            "extraction_pending_total": getattr(result, "extraction_pending_total", 0),
            "extraction_rejection_counts": getattr(result, "extraction_rejection_counts", {}),
            "total_queries": result.total_queries,
            "total_steps": result.total_steps,
            "skill_execution_count": traj_logger.skill_execution_count,
            "elapsed_s": result.elapsed_s,
            "tool_counts": traj_logger.tool_counts,
            "model_distribution": self._model_distribution,
            "frontier_resolved": final_search_state.frontier.resolved_count,
            "frontier_total": len(final_search_state.frontier.questions),
            "token_usage": token_dict,
            "token_phases": token_phases,
            "browser_usage": browser_usage.to_dict(),
        })
        result.token_usage = token_dict
        result.token_phases = token_phases
        result.browser_usage = browser_usage.to_dict()
        result.tool_counts = traj_logger.tool_counts
        result.skill_execution_count = traj_logger.skill_execution_count
        result.model_distribution = self._model_distribution

        skill_generation = None
        if settings.enable_access_skill_generation:
            from searchos.skills.post_run import TraceSkillGeneration

            try:
                skill_generation = TraceSkillGeneration(workspace.path, query, trace_offset=trace_offset)
                result.skill_generation_id = skill_generation.id
            except Exception:
                logger.warning("Failed to initialize trace skill generation", exc_info=True)

        try:
            workspace.save_turn_snapshot(
                query,
                final_search_state,
                {
                    "coverage_score": result.coverage_score,
                    "evidence_count": result.evidence_count,
                    "elapsed_s": result.elapsed_s,
                    "total_queries": result.total_queries,
                    "total_steps": result.total_steps,
                    "skill_execution_count": result.skill_execution_count,
                    "tool_counts": result.tool_counts,
                    "token_usage": result.token_usage,
                    "token_phases": result.token_phases,
                    "model_distribution": result.model_distribution,
                    "skill_generation_id": result.skill_generation_id,
                },
            )
        except Exception:
            # Snapshot persistence enriches history but must never turn an
            # otherwise successful search into a failed run.
            logger.warning("Failed to persist turn snapshot", exc_info=True)

        logger.info(
            "Search complete: coverage=%.0f%%, evidence=%d, time=%.1fs, tokens=%d (%d calls)",
            result.coverage_score * 100,
            result.evidence_count,
            result.elapsed_s,
            token_dict["total_tokens"],
            token_dict["llm_calls"],
        )

        # 兼容原配置名；统一 trace intent 决定三类技能的新增或更新。
        if skill_generation is not None:
            access_task = asyncio.create_task(
                skill_generation.run(
                    library_path=Path(self._skill_library_path or "searchos/skills/library"),
                    model=self._skill_evolver_model,
                    max_requests=settings.access_skill_max_per_run,
                ), name=f"skill-gen-{workspace.session_id}",
            )
            _PENDING_EVOLUTIONS.add(access_task)
            access_task.add_done_callback(_PENDING_EVOLUTIONS.discard)
            result.access_task = access_task

        return result

# ---------------------------------------------------------------------------
# Token phase tracking
# ---------------------------------------------------------------------------

_DISPATCH_PHASE_TOOLS = frozenset({"enqueue_tasks"})
_SYNTHESIZE_PHASE_TOOLS = frozenset({"synthesize_answer"})


class _PhaseTracker:
    """Track token consumption across Orchestrator phases via snapshots."""

    __slots__ = ("_usage", "_phase", "_snapshots")

    def __init__(self, usage: Any) -> None:
        self._usage = usage
        self._phase = "explore"
        self._snapshots: dict[str, dict[str, int]] = {
            "explore": usage.to_dict(),  # start snapshot
        }

    def observe(self, msg: Any) -> None:
        """Detect phase transitions from AIMessage tool calls."""
        tool_calls = getattr(msg, "tool_calls", None)
        if not tool_calls:
            return
        for tc in tool_calls:
            name = tc.get("name", "") if isinstance(tc, dict) else getattr(tc, "name", "")
            if self._phase == "explore" and name in _DISPATCH_PHASE_TOOLS:
                self._snapshots["sub_agents"] = self._usage.to_dict()
                self._phase = "sub_agents"
            elif self._phase == "sub_agents" and name in _SYNTHESIZE_PHASE_TOOLS:
                self._snapshots["synthesize"] = self._usage.to_dict()
                self._phase = "synthesize"

    def finalize(self) -> dict[str, dict[str, int]]:
        """Compute per-phase token deltas."""
        end = self._usage.to_dict()
        phases: dict[str, dict[str, int]] = {}

        snap_explore = self._snapshots["explore"]
        snap_sub = self._snapshots.get("sub_agents", end)
        snap_synth = self._snapshots.get("synthesize", end)

        phases["setup"] = dict(snap_explore)
        phases["explore"] = {k: snap_sub[k] - snap_explore[k] for k in snap_explore}
        phases["sub_agents"] = {k: snap_synth[k] - snap_sub[k] for k in snap_sub}
        phases["synthesize"] = {k: end[k] - snap_synth[k] for k in snap_synth}

        return phases


_RESULT_MAX_LEN = 500


def _log_orchestrator_tool_events(
    msg: Any,
    traj_logger: Any,
    pending: dict[str, dict[str, Any]],
) -> None:
    """Merge tool_call + tool_result into a single trajectory event.

    AIMessage.tool_calls → stash into *pending* (keyed by tool_call_id).
    ToolMessage → pop matching pending entry, emit ONE merged event.
    """
    if traj_logger is None:
        return

    # AIMessage with tool_calls → stash
    tool_calls = getattr(msg, "tool_calls", None)
    if tool_calls:
        for tc in tool_calls:
            tc_id = tc.get("id", "") if isinstance(tc, dict) else getattr(tc, "id", "")
            name = tc.get("name", "") if isinstance(tc, dict) else getattr(tc, "name", "")
            args = tc.get("args", {}) if isinstance(tc, dict) else getattr(tc, "args", {})
            pending[tc_id] = {"tool": name, "args": _full_args(args)}
        return

    # ToolMessage → merge with pending and emit
    msg_type = getattr(msg, "type", "")
    if msg_type == "tool":
        tc_id = getattr(msg, "tool_call_id", "") or ""
        tool_name = getattr(msg, "name", "") or ""

        content = str(getattr(msg, "content", ""))
        entry = pending.pop(tc_id, None)
        if entry:
            entry["type"] = "orchestrator_tool"
            entry["tool_call_id"] = tc_id
            entry["result"] = content
            entry["result_preview"] = content[:_RESULT_MAX_LEN]
            traj_logger._append_raw(entry)
        else:
            # No matching pending (shouldn't happen, but be safe)
            traj_logger._append_raw({
                "type": "orchestrator_tool",
                "tool": tool_name,
                "tool_call_id": tc_id,
                "args": {},
                "result": content,
                "result_preview": content[:_RESULT_MAX_LEN],
            })


def _full_args(args: Any) -> dict[str, Any]:
    """Keep complete tool args in the durable trajectory."""
    if not isinstance(args, dict):
        return {"raw": str(args)}
    return dict(args)


def _export_eval_table(
    *,
    workspace: WorkspaceManager,
    state: SearchState,
    query: str,
) -> None:
    """Deterministic eval-table export: skip LLM synthesis entirely."""
    import json as _json

    from searchos.harness.report.eval_table_export import build_eval_table

    eval_table = build_eval_table(state)
    workspace.write_output("eval_table.md", eval_table or "")
    workspace.write_output("result.json", _json.dumps({
        "query": query,
        "answer": eval_table,
        "mode": "eval_table_direct",
        "evidence_count": state.evidence_graph.node_count,
        "coverage": state.coverage_map.coverage_score,
    }, ensure_ascii=False, indent=2))


class FinalCitationError(ValueError):
    """Retain a rejected draft and its citation gaps before publishing output."""

    def __init__(self, draft, issues, state):
        from searchos.socm.coverage import answer_evidence

        available = {node.id: node for node in answer_evidence(state)}
        all_nodes = {node.id: node for node in state.evidence_graph.nodes}
        self.draft = draft
        self.issues = list(issues)
        self.gaps = []
        for ref in issues:
            eid = ref.removeprefix("evidence:") if ref.startswith("evidence:") else ""
            node = all_nodes.get(eid)
            reason = (
                "unknown_evidence" if node is None else
                "unavailable_evidence" if eid not in available else
                "original_source_missing"
            )
            self.gaps.append({
                "reference": ref, "reason": reason,
                "finding": node.finding if node is not None else "",
            })
        super().__init__("Final citation validation failed: " + ", ".join(issues))


def _finalization_audit(workspace, audit):
    import json

    workspace.write_output(
        f"finalization/{audit['id']}/audit.json",
        json.dumps(audit, ensure_ascii=False, indent=2),
    )


def _archive_previous_delivery(workspace, audit_id):
    """Archive previous output only after the new answer passes citation validation."""
    if getattr(workspace, "path", None) is None:
        return
    output = workspace.path / settings.output_dir
    for filename in ("report.md", "result.json"):
        source = output / filename
        if source.exists():
            workspace.write_output(
                f"finalization/{audit_id}/previous/{filename}",
                source.read_text(encoding="utf-8"),
            )


def _record_finalization_follow_ups(steering, conversation_logger):
    if steering is None or conversation_logger is None:
        return
    from searchos.harness.telemetry.conversation import langchain_msg_to_conversation_msgs

    def record_follow_up(message):
        for entry in langchain_msg_to_conversation_msgs(message):
            conversation_logger.log(entry)

    steering.on_delivery = record_follow_up


def _incomplete_citation_answer(query, gaps):
    import re

    chinese = bool(re.search(r"[\u4e00-\u9fff]", query))
    answer = (
        "本次研究尚未形成可追溯的完整回答。以下内容仍缺少有效原文支持，需补充原文并核验后才能确认："
        if chinese else
        "This research is incomplete. The following material still needs an available original source and verification:"
    )
    findings = list(dict.fromkeys(gap["finding"] for gap in gaps if gap["finding"]))
    for finding in findings[:10]:
        # 缺口描述保留，内部地址不能重新成为正文引用。
        finding = re.sub(r"evidence:[\w-]+|(?:agent|skill|edit)://\S+", "[unavailable source]", finding)
        answer += "\n\n- " + finding
    if not findings:
        answer += (
            "\n\n正文引用无法关联到当前可回答范围内的有效原文。"
            if chinese else
            "\n\nThe draft cites references that cannot be linked to available source evidence."
        )
    if len(findings) > 10:
        answer += (
            f"\n\n另有 {len(findings) - 10} 项缺口，完整草稿及引用问题已保留在审计记录中。"
            if chinese else
            f"\n\nThere are {len(findings) - 10} additional gaps; the full draft and citation issues are saved in the audit."
        )
    return answer


async def _commit_final_answer(*, workspace, state, query, final_state, model,
                               execution_error="", stop_reason="", finalizer="orchestrator",
                               extra_generation_used=False, generation_events=(),
                               answer_stream=None, trajectory_logger=None,
                               conversation_logger=None, follow_ups=(), steering=None):
    """Validate and publish the current answer, with bounded citation repair."""
    from uuid import uuid4

    from langchain_core.messages import AIMessage

    from searchos.harness.report.synthesis import finalize_research
    from searchos.harness.telemetry.conversation import ConversationMessage

    audit = {
        "id": uuid4().hex, "status": "validating", "finalizer": finalizer,
        "extra_generation_used": int(extra_generation_used),
        "generation_events": list(generation_events), "citation_failures": [],
    }
    _record_finalization_follow_ups(steering, conversation_logger)
    gaps = []
    issues = []

    def record_rejection(exc):
        issues.extend(ref for ref in exc.issues if ref not in issues)
        gaps.extend(gap for gap in exc.gaps if gap not in gaps)
        attempt = len(audit["citation_failures"]) + 1
        workspace.write_output(f"finalization/{audit['id']}/draft-{attempt}.md", exc.draft)
        audit["citation_failures"].append({"attempt": attempt, "gaps": exc.gaps})
        _finalization_audit(workspace, audit)

    try:
        answer = _write_findings_answer(
            workspace, state, query, final_state, execution_error=execution_error,
            stop_reason=stop_reason, finalization=audit,
        )
    except FinalCitationError as exc:
        record_rejection(exc)
        if not audit["extra_generation_used"] and model is not None:
            audit["extra_generation_used"] = 1
            audit["generation_events"].append({"phase": "citation_repair", "status": "started"})
            _finalization_audit(workspace, audit)
            try:
                repaired = await finalize_research(
                    state=workspace.load_state(), query=query, model=model,
                    stop_reason=stop_reason or "citation_validation_failed",
                    follow_ups=steering.delivered if steering is not None else follow_ups,
                    steering=steering,
                    max_chars=settings.research_finalize_max_chars,
                    timeout_s=settings.research_finalize_timeout_s,
                    citation_repair={"draft": exc.draft, "gaps": exc.gaps},
                )
            except asyncio.CancelledError:
                audit["status"] = "cancelled"
                audit["generation_events"][-1]["status"] = "cancelled"
                try:
                    _finalization_audit(workspace, audit)
                except Exception:
                    logger.warning("Failed to save cancelled finalization audit", exc_info=True)
                raise
            except Exception as repair_exc:
                audit["generation_events"][-1].update(
                    status="failed", error_type=type(repair_exc).__name__,
                )
            else:
                audit["generation_events"][-1]["status"] = "completed"
                state = workspace.load_state()
                try:
                    answer = _write_findings_answer(
                        workspace, state, query, {"messages": [AIMessage(content=repaired)]},
                        execution_error=execution_error, stop_reason=stop_reason,
                        finalization=audit,
                    )
                except FinalCitationError as repaired_exc:
                    record_rejection(repaired_exc)
                else:
                    audit["status"] = "repaired"
        if audit["status"] != "repaired":
            audit["status"] = "incomplete"
            answer = _write_findings_answer(
                workspace, workspace.load_state(), query,
                {"messages": [AIMessage(content=_incomplete_citation_answer(query, gaps))]},
                execution_error=execution_error, stop_reason=stop_reason,
                finalization=audit, incomplete_issues=issues,
            )
    else:
        audit["status"] = "published"
    # 正式交付已完成。后置审计、通知故障不能撤销或改写该答案。
    notifications = [("audit", lambda: _finalization_audit(workspace, audit))]
    if conversation_logger is not None:
        notifications.append(("conversation", lambda: conversation_logger.log(ConversationMessage(
            role="assistant", content=answer,
            metadata={"phase": "final_answer", "finalizer": finalizer,
                      "stop_reason": stop_reason, "publication_status": audit["status"]},
        ))))
    if trajectory_logger is not None:
        notifications.append(("trajectory", lambda: trajectory_logger._append_raw({
            "type": "harness", "kind": "research_finalized", "stop_reason": stop_reason,
            "finalizer": finalizer, "execution_error": execution_error,
            "orchestrator_error": next((e.get("error_type", "") for e in generation_events
                                        if e.get("phase") == "orchestrator"), ""),
            "publication_status": audit["status"],
            "extra_generation_used": audit["extra_generation_used"],
            "citation_issues": issues,
        })))
    if answer_stream is not None:
        def publish_stream():
            answer_stream.push(answer)
            answer_stream.finish()

        notifications.append(("stream", publish_stream))
    for phase, notify in notifications:
        try:
            notify()
        except Exception:
            logger.warning("Committed answer %s notification failed", phase, exc_info=True)
    return answer


def _write_findings_answer(workspace, state, query, final_state, *, execution_error="",
                           stop_reason="", finalization=None, incomplete_issues=None) -> str:
    """Reject untraceable citations before publishing; semantic support is checked separately."""
    import json

    from searchos.local.refs import LOCAL_LINK_RE
    from searchos.socm.coverage import answer_evidence

    nodes = answer_evidence(state)
    from searchos.harness.report.grounding import final_answer_text
    answer = final_answer_text(final_state)
    from searchos.socm.evidence.provenance import evidence_source_urls
    canonical = {url: url for node in nodes for url in evidence_source_urls(node) if url.startswith("local://")}
    from searchos.local.refs import parse_ref_id
    document_refs: dict[str, set[str]] = {}
    for node in nodes:
        alias = (node.local_source_metadata or {}).get("tool_ref_id")
        if alias:
            canonical[alias] = node.source
        if node.source.startswith("local://"):
            try:
                ref = parse_ref_id(node.source)
                document_refs.setdefault(ref.document_id, set()).add(node.source)
            except ValueError:
                pass
    for doc_id, refs in document_refs.items():
        if len(refs) == 1:
            canonical[f"local://{doc_id}"] = next(iter(refs))
    mode = "research_finalized" if stop_reason else "hybrid_orchestrator"
    if not answer.strip():
        answer = "研究执行中断，尚未生成回答。" if execution_error else "本次研究尚未生成回答。"
        mode = "hybrid_partial"
    from searchos.socm.evidence.provenance import resolve_answer_citations
    resolved, citation_issues = resolve_answer_citations(answer, nodes)
    if citation_issues:
        raise FinalCitationError(answer, citation_issues, state)
    answer = resolved
    answer = LOCAL_LINK_RE.sub(lambda m: canonical.get(m.group(0), "invalid-local-reference"), answer)
    from searchos.socm.planning.research_plan import membership_review
    if incomplete_issues is not None:
        mode = "research_incomplete"
        citation_issues = incomplete_issues
    result = {
        "query": query, "answer": answer, "mode": mode,
        "execution_error": execution_error,
        "stop_reason": stop_reason,
        "citation_issues": citation_issues,
        "research_plan": state.research_plan.model_dump() if state.research_plan else None,
        "membership_review": membership_review(state),
        "evidence_count": len(nodes),
        "coverage": state.coverage_map.coverage_score,
        "frontier_progress": _frontier_progress(state),
    }
    if finalization is not None:
        result["finalization"] = {
            **finalization,
            "status": "incomplete" if incomplete_issues is not None else
                "repaired" if finalization["citation_failures"] else "published",
        }
    serialized = json.dumps(result, ensure_ascii=False, indent=2)
    if finalization is not None:
        _archive_previous_delivery(workspace, finalization["id"])
    workspace.write_output("report.md", answer)
    workspace.write_output("result.json", serialized)
    return answer


async def _harness_synthesize(
    *,
    workspace: WorkspaceManager,
    state: SearchState,
    query: str,
    answer_stream: AnswerStreamEmitter | None = None,
) -> None:
    """续写 writer 正文，拼接覆盖表和来源生成最终报告。"""
    logger.info(
        "_harness_synthesize called: session=%s, evidence=%d, coverage=%.0f%%",
        workspace.session_id, state.evidence_graph.node_count,
        state.coverage_map.coverage_score * 100,
    )
    import json as _json

    from searchos.socm.coverage import answer_evidence

    evidence = answer_evidence(state)

    # Nothing collected — write a minimal marker and exit.
    if not evidence:
        workspace.write_output(
            "report.md",
            f"# {query}\n\n_No report produced: 0 evidence nodes, draft empty._\n",
        )
        workspace.write_output("result.json", _json.dumps({
            "query": query,
            "answer": "",
            "mode": "empty_marker",
            "evidence_count": 0,
            "coverage": state.coverage_map.coverage_score,
            "evidence_backed_coverage": _evidence_backed_coverage(state),
            "frontier_progress": _frontier_progress(state),
        }, ensure_ascii=False, indent=2))
        logger.warning("Harness synthesis: wrote empty-marker report.md")
        return

    # 正文和降级路径共用确定性的引用编号、覆盖表和来源。
    from searchos.harness.report.synthesis import (
        _detect_language,
        build_coverage_table_with_citations,
        build_sources_list,
        build_url_citation_map,
    )

    evidence_by_id = {n.id: n for n in evidence}
    url_map = build_url_citation_map(evidence)
    coverage_table = build_coverage_table_with_citations(
        state, evidence_by_id, url_map,
    )
    sources_list = build_sources_list(url_map)
    language = "中文" if _detect_language(query) == "zh" else "English"

    # 优先续写 writer；失败时采用已有提纲正文，无正文则仅输出覆盖表和来源。
    sections = list(getattr(state.outline, "sections", []) or [])
    total_sec = len(sections)
    sec_with_content = sum(1 for s in sections if (s.content or "").strip())

    def _assemble(body: str) -> str:
        return "\n".join([
            f"# {query}",
            "",
            body if body.strip() else "_(empty body)_",
            "",
            "### 数据对比表" if language == "中文" else "### Coverage Table",
            coverage_table if coverage_table else "_(no structured data)_",
            "",
            "### 信息来源" if language == "中文" else "### Sources",
            sources_list if sources_list else "_(no sources)_",
        ])

    finalize_body = await _run_writer_finalize(
        query=query,
        coverage_table=coverage_table,
        sources_list=sources_list,
        language=language,
        coverage_score=state.coverage_map.coverage_score,
    )
    writer_metadata = {}
    if finalize_body:
        body, writer_agent_id = finalize_body
        body = body.strip()
        mode = "writer_finalize"
        writer_metadata["writer_agent_id"] = writer_agent_id
    else:
        # 只渲染引用仍有效的章节，原 outline 留作审计。
        eligible_ids = set(evidence_by_id)
        eligible_sections = [section for section in state.outline.sections
                             if all(eid in eligible_ids for eid in section.cited_evidence_ids)]
        body = state.outline.model_copy(update={"sections": eligible_sections}).rendered().strip()
        mode = "outline_writer" if body else "structured_only"

    from searchos.socm.evidence.provenance import resolve_answer_citations
    from searchos.socm.planning.research_plan import membership_review
    report, citation_issues = resolve_answer_citations(_assemble(body), evidence)
    workspace.write_output("report.md", report)
    workspace.write_output("result.json", _json.dumps({
        "query": query,
        "answer": report,
        "citation_issues": citation_issues,
        "research_plan": state.research_plan.model_dump() if state.research_plan else None,
        "membership_review": membership_review(state),
        "mode": mode,
        **writer_metadata,
        "evidence_count": len(evidence),
        "coverage": state.coverage_map.coverage_score,
        "evidence_backed_coverage": _evidence_backed_coverage(state),
        "frontier_progress": _frontier_progress(state),
        "outline_sections_total": total_sec,
        "outline_sections_with_content": sec_with_content,
        "url_citations": url_map,
    }, ensure_ascii=False, indent=2))
    if answer_stream is not None:
        # Publish after the writer body, citations, tables, and sources have
        # been assembled into the exact answer persisted for the user.
        answer_stream.push(report)
        answer_stream.finish()
    logger.info(
        "Harness synthesis (%s): %d/%d sections with content, "
        "%d evidence, %d unique sources",
        mode, sec_with_content, total_sec, len(evidence), len(url_map),
    )
    return

async def _run_writer_finalize(
    *,
    query: str,
    coverage_table: str,
    sources_list: str,
    language: str,
    coverage_score: float,
) -> tuple[str, str] | None:
    """续写 writer 线程，返回 (正文, Agent ID)，失败时返回 None。

    直接调用图以绕过调度层预算门禁，允许搜索预算耗尽后完成报告收尾。
    """
    from searchos.agents.runtime import _ctx
    from searchos.harness.report.synthesis import build_writer_finalize_message

    try:
        graphs = _ctx.agent_graphs
    except RuntimeError:
        logger.info("writer_finalize: no orchestrator context (agent_graphs)")
        return None

    # 选择最近启动的 writer。
    writer_entries = [
        (aid, info) for aid, info in graphs.items()
        if info.get("agent_type") == "writer_agent"
    ]
    if not writer_entries:
        logger.info("writer_finalize: no writer_agent in registry")
        return None
    writer_entries.sort(key=lambda p: p[1].get("started_at", 0.0), reverse=True)
    writer_agent_id, info = writer_entries[0]
    graph = info.get("graph")
    thread_id = info.get("thread_id")
    if graph is None or not thread_id:
        logger.info("writer_finalize: writer %s missing graph/thread_id", writer_agent_id)
        return None

    message = build_writer_finalize_message(
        query=query,
        coverage_table=coverage_table,
        sources_list=sources_list,
        language=language,
        coverage_score=coverage_score,
        stop_reason="harness_finalize",
    )

    # Rebind current-agent ContextVar so writer tools identify themselves.
    try:
        from searchos.tools.search_state import set_current_agent
        set_current_agent(thread_id)
    except Exception:
        pass

    try:
        latest_messages: list[Any] = []
        async for stream_kind, stream_event in graph.astream(
            {"messages": [{"role": "user", "content": message}]},
            config={"configurable": {"thread_id": thread_id}},
            stream_mode=["values"],
        ):
            event = stream_event
            if isinstance(event, dict) and "messages" in event:
                latest_messages = event["messages"]
    except Exception as e:
        logger.error(
            "writer_finalize: astream raised: %s(%s)",
            type(e).__name__, str(e).strip(), exc_info=True,
        )
        return None
    if not latest_messages:
        logger.warning("writer_finalize: no messages returned")
        return None

    # Walk backwards to find the last AI message with non-empty text content.
    body = ""
    for msg in reversed(latest_messages):
        msg_type = getattr(msg, "type", None) or getattr(msg, "role", None)
        if msg_type not in ("ai", "assistant"):
            continue
        content = getattr(msg, "content", None)
        if isinstance(content, str) and content.strip():
            body = content.strip()
            break
        if isinstance(content, list):
            parts = []
            for p in content:
                if isinstance(p, dict) and p.get("type") == "text":
                    parts.append(p.get("text", ""))
                elif isinstance(p, str):
                    parts.append(p)
            text = "\n".join(x for x in parts if x).strip()
            if text:
                body = text
                break

    if not body:
        logger.warning("writer_finalize: AI message content empty")
        return None

    return body, writer_agent_id


class SearchResult:
    """Structured output from a search session."""

    def __init__(
        self,
        query: str,
        session_id: str,
        workspace_path: str,
        search_state: SearchState,
        eval_verdict: str,
        coverage_score: float,
        evidence_count: int,
        total_queries: int,
        total_steps: int,
        elapsed_s: float,
        final_messages: list[dict[str, Any]] | None = None,
        execution_error: str = "",
    ) -> None:
        self.query = query
        self.session_id = session_id
        self.workspace_path = workspace_path
        self.search_state = search_state
        self.eval_verdict = eval_verdict
        self.coverage_score = coverage_score
        self.evidence_count = evidence_count
        self.evidence_active_count = 0
        self.evidence_candidate_count = 0
        self.extraction_pending_total = 0
        self.extraction_rejection_counts: dict[str, int] = {}
        self.total_queries = total_queries
        self.total_steps = total_steps
        self.elapsed_s = elapsed_s
        self.final_messages = final_messages or []
        self.execution_error = execution_error
        self.access_task: asyncio.Task[None] | None = None
        self.skill_generation_id: str | None = None
        self.token_usage: dict[str, Any] = {}
        self.token_phases: dict[str, Any] = {}
        self.browser_usage: dict[str, int] = {}
        self.tool_counts: dict[str, int] = {}
        self.skill_execution_count: int = 0
        self.model_distribution: dict[str, dict[str, str]] = {}

    def summary(self) -> str:
        tokens = self.token_usage.get("total_tokens", 0)
        calls = self.token_usage.get("llm_calls", 0)
        token_line = f"Tokens: {tokens:,} ({calls} LLM calls)\n" if tokens else ""
        return (
            f"Query: {self.query}\n"
            f"Verdict: {self.eval_verdict}\n"
            f"Coverage: {self.coverage_score:.0%}\n"
            f"Evidence: {self.evidence_count} nodes\n"
            f"Steps: {self.total_steps}\n"
            f"Time: {self.elapsed_s:.1f}s\n"
            f"{token_line}"
            f"Workspace: {self.workspace_path}"
        )

if __name__ == "__main__":
    from searchos.agents.orchestrator import get_orchestrator_tools
    from searchos.agents.toolset_render import render_toolset
    print(render_toolset(get_orchestrator_tools()))

    from searchos.agents.orchestrator.catalog import generate_agent_catalog_text
    print(generate_agent_catalog_text())
