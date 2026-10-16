"""SearchSession: Main Agent (Orchestrator) as the sole decision maker.

The Orchestrator explores, plans, dispatches Sub Agents, evaluates, and synthesizes.
No external auto_plan or DAGExecutor — the Orchestrator owns the full loop.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from contextlib import aclosing
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
        if not any(q.kind == "search" for q in state.frontier.questions):
            reasons.append(
                "no search task was ever dispatched this session "
                "(explore alone cannot complete a search task)"
            )
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
    return (
        "[AUTOMATED HARNESS — turn ended without a tool call]\n"
        "Your previous message contained no executable tool call; action "
        "descriptions written as plain text are NOT executed.\n"
        f"The session is not complete: {reason}.\n"
        "Continue by calling a real tool — check_agents to collect running "
        "agents, enqueue_tasks to dispatch remaining work. If you are certain "
        "no further progress is possible, state why explicitly and end with "
        "a final summary."
    )


def _is_safe_steer_boundary(event: dict) -> bool:
    """Whether a live follow-up can be injected after this astream event.

    Context updates may follow an AI tool request before its ToolMessages
    arrive. Check every outstanding call, not just the last message.
    """
    pending: set[str] = set()
    for message in event.get("messages") or []:
        for call in getattr(message, "tool_calls", None) or []:
            pending.add(call["id"])
        if getattr(message, "type", None) == "tool":
            pending.discard(message.tool_call_id)
    return not pending


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
        from searchos.tools.simple_browser.backend.base import BrowserService
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
    """Orchestrator-based search harness.

    Flow (unified — Orchestrator is the sole decision maker):
        1. Create workspace + state
        2. Build Orchestrator Agent with orchestrator tools (create_schema,
           spawn/check/continue_agent, plus SOCM read + skill management)
        3. Orchestrator autonomously: choose exploration / schema / retrieval →
           poll → continue/spawn as needed
        4. Harness drains Agent work; Orchestrator finalizes the answer
           without tools, with Synthesis reserved for failure fallback
    """

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
        research_mode: str | None = None,
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
        self._research_mode = research_mode

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
        self._conversation_logger = None
        try:
            with activate_run_config(self._run_config):
                return await self._run_impl(*args, **kwargs)
        finally:
            if self._conversation_logger is not None:
                self._conversation_logger.flush()

    async def _run_impl(
        self,
        query: str,
        *,
        session_id: str | None = None,
        initial_state: SearchState | None = None,
        context_preamble: str | None = None,
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

        ``context_preamble`` (optional): prior-turn conversational background
        injected ahead of the query in the orchestrator's first user message,
        enabling multi-turn follow-ups. ``query`` itself stays unchanged for
        logging/metadata.

        ``steer_queue`` (optional): a queue the caller pushes live user
        follow-ups onto while the run is in flight. Immediate input replaces
        unfinished model generation or wakes check_agents; after_tool input
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

        # --- Token tracking (per-run, ContextVar-backed) ---
        from searchos.util.token_tracker import start_tracking
        token_usage = start_tracking()
        from searchos.tools.simple_browser.usage import (
            start_tracking as start_browser_tracking,
        )
        browser_usage = start_browser_tracking()

        # --- Workspace ---
        workspace = WorkspaceManager(self._workspace_root, session_id)
        workspace.create()

        # --- Reset cross-agent browser state for this fresh session ---
        from searchos.tools.simple_browser.state import reset_browser, set_source_controls
        reset_browser()
        source_controls = set_source_controls(trusted_domains, excluded_domains)

        # --- State ---
        state = initial_state or SearchState(intent=query)
        if state.source_scope is None:
            state.source_scope = {"mode": "web", "documents": []}
        if state.source_scope.get("mode") == "local":
            raise ValueError("Local mode uses the direct Local Search Agent")
        state.research_mode = self._research_mode or (
            "findings" if state.source_scope.get("mode") == "hybrid" else "table"
        )
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
        from searchos.tools.skill_catalog import _skill_access_policy_var
        _skill_access_policy_var.set({
            "access_only": None if access_only is None else frozenset(access_only),
            "access_deny": frozenset(access_deny or ()),
            "strategy_deny": frozenset(strategy_deny or ()),
            "orchestrator_deny": frozenset(orchestrator_deny or ()),
        })
        self.ensure_skill_registry()

        # --- Trajectory logger ---
        self._active_workspace = workspace  # exposed so the live TUI can poll state
        from searchos.harness.telemetry.episodic import TrajectoryLogger
        traj_logger = TrajectoryLogger(workspace.trajectory_path)
        # In-process live-TUI hook: every trajectory event (orchestrator +
        # sub-agents, all sharing this one logger) is forwarded as it's written.
        if on_event is not None:
            traj_logger.add_listener(on_event)

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
        from searchos.agents.orchestrator import get_orchestrator_tools
        from searchos.agents.runtime import set_orchestrator_context
        from searchos.tools.search_state import set_workspace
        from searchos.tools.simple_browser.state import _provider, set_browser_provider

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


        from datetime import datetime as _dt

        from searchos.agents.orchestrator.catalog import _is_agent_enabled, generate_agent_catalog_text
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
                "stop_task",
                "check_agents",
                "inspect_table",
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
            from searchos.skills.catalog.router import render_playbook
            from searchos.skills.core.models import SkillCategory
            orch_candidates = self._skill_registry.list_by_category(SkillCategory.ORCHESTRATOR)
            if orchestrator_deny:
                orch_candidates = [
                    s for s in orch_candidates if s.meta.name not in orchestrator_deny
                ]
            orchestrator_playbook = render_playbook(orch_candidates)

            # 子 agent 按当前检索需求发现技能；权限仍由上面的 policy 约束。
            skill_catalog = (
                "Search agents start each task by discovering Access and Strategy skills with "
                "list_skills(query=their current retrieval need), then read load_skill "
                "before use. Give them the task, source hints and acceptance criteria. "
                "The skills field is optional; omit it unless you already know a suitable "
                "skill from this run. Do not guess skill names."
            )
        else:
            orchestrator_playbook = ""
            skill_catalog = ""

        system_prompt = build_orchestrator_prompt(
            agent_catalog=generate_agent_catalog_text(),
            skill_catalog=skill_catalog,
            max_dispatches=settings.orch_max_dispatches,
            max_searches_per_agent=settings.max_searches_per_sub_agent,
            max_skills_per_agent=settings.max_skills_per_sub_agent,
            max_search_agents_per_session=settings.max_search_agents_per_session,
            # Date-only: minute precision forks the prompt-cache prefix
            # across sessions started in different minutes.
            current_time=_dt.now().strftime("%Y-%m-%d"),
            orch_toolset=render_toolset(orchestrator_tools, header="## Available Tools"),
            enable_explore=_is_agent_enabled("explore_agent"),
            explore_on_start=self._run_config.explore_on_start and not targeted_repair_mode,
            orchestrator_playbook=orchestrator_playbook,
            follow_up=follow_up or bool(context_preamble),
            research_mode=state.research_mode,
            source_mode=(state.source_scope or {}).get("mode", ""),
            local_sources=(
                "Current library: " + str(state.source_scope.get("library_id", ""))
                + (
                    "; scope: readable library snapshot.\n"
                    if state.source_scope.get("selection") == "library"
                    else "; scope: selected documents.\n"
                )
                + f"Readable documents: {len(state.source_scope.get('documents', []))}.\n"
                if (state.source_scope or {}).get("library_id") else ""
            ) + "\n".join(
                f"- {record['relative_path']} (document_id={record['document_id']})"
                for record in (state.source_scope or {}).get("documents", [])
            ),
            source_limitations="\n".join(state.source_scope.get("unavailable_sources", {}).values()),
        )
        if fixed_schema:
            system_prompt += (
                "\n\n## Fixed Prebuilt Schema Mode (experimental override)\n"
                "The SOCM already contains the complete, immutable schema for this run. "
                "This block overrides any earlier instruction to create or redesign a schema. "
                "The create_schema and add_columns tools are intentionally unavailable. Do not add tables or columns or "
                "reinterpret the table boundaries. You may discover rows, call add_entities / "
                "edit_entities, dispatch agents from the current Agent Catalog, "
                "and fill the existing cells. "
                "Follow the configured initial-action policy for Explore, using the existing "
                "table IDs and relations; Explore must not redesign the schema. "
                "Every retrieval task in a multi-table "
                "run must name target_table."
            )
        if targeted_repair_mode:
            system_prompt += (
                "\n\n## Targeted Repair Mode (overrides the normal workflow)\n"
                "The selected cells in the user message are an immutable allowlist. "
                "Plan the work yourself and call `enqueue_tasks` with the appropriate "
                "retrieval agents from the current Agent Catalog. "
                "Every task MUST provide the exact "
                "`target_table` and explicit "
                "`target_cells`, and their cells must be a subset of the allowlist; "
                "the tool rejects any wider scope. Group and stage tasks as you judge "
                "best for the available pool. Do not create or edit schemas or entities. "
                "Use `check_agents`, adapt later waves from returned evidence, inspect "
                "only the selected cells, then report their changes."
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
        from searchos.harness.middleware.sensor.core.models import BudgetState, ControlState

        # Orchestrator never calls `search` — bound by iterations + sensors.
        orch_budget = BudgetState(
            max_queries=0,
            max_iterations=settings.orch_max_iterations,
            max_time_s=(settings.default_max_time_s
                        if self._max_time_s is None else self._max_time_s),
        )
        def stop_dispatch():
            from searchos.agents.runtime import _ctx

            _ctx.mark_budget_exhausted()

        from searchos.agents.runtime import _ctx

        orch_control = ControlState()
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
        from searchos.harness.middleware.context.steering_middleware import SteeringMiddleware

        steering = next((m for m in graph.middleware if isinstance(m, SteeringMiddleware)), None)

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

        # --- Run Orchestrator ---
        logger.info(
            "Starting Orchestrator: %s (session=%s)",
            query[:60],
            workspace.session_id,
        )
        final_state = None
        execution_error = ""
        finalization_reason = ""
        prev_msg_count = 0

        pending_tool_calls: dict[str, dict[str, Any]] = {}
        phase_tracker = _PhaseTracker(token_usage)
        answer_stream = AnswerStreamEmitter(
            traj_logger._append_raw,
            stream_prefix=f"web-{workspace.session_id}",
        )
        committed_final_answer = ""
        cancelled = False  # set when the user interrupts (Ctrl-C → task.cancel)
        try:
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
            user_content = query
            if context_preamble:
                user_content = (
                    f"{context_preamble}\n\n---\n当前问题：{query}"
                )
            if targeted_repair_mode:
                targets = ", ".join(targeted_repair_cells or [])
                user_content = (
                    "[TARGETED CELL REPAIR]\n"
                    f"Repair only these coverage cells: {targets}.\n"
                    "You own the repair plan and dispatch. Split these cells into focused "
                    "retrieval tasks with enqueue_tasks using the current Agent Catalog; "
                    "set target_table and "
                    "target_cells on every task (`target_cells` may use Entity.Attribute "
                    "or the full table/Entity.Attribute key). Do not create or change schemas, add "
                    "entities, or expand beyond this allowlist. Keep dispatching and "
                    "checking agents until the selected cells are repaired or the "
                    "available evidence is exhausted, then summarize what changed."
                )
            input_payload: dict[str, Any] = {
                "messages": [{"role": "user", "content": user_content}],
            }
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
                        new_msgs = msgs[prev_msg_count:]
                        prev_msg_count = len(msgs)

                        for msg in new_msgs:
                            # Record to conversation logger
                            for conv_msg in langchain_msg_to_conversation_msgs(msg):
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

                        # Once research is stopped, leave the graph at a complete
                        # tool/message boundary. Synthesis runs after task drain.
                        if (not self._skip_synthesis
                                and (orch_control.forced or orch_budget.fully_exhausted)
                                and _is_safe_steer_boundary(event)):
                            finalization_reason = orch_control.reason or "harness_stopped"
                            break

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
                        {"role": "user", "content": _premature_end_nudge(reason)},
                    ],
                }

        except asyncio.CancelledError:
            # User interrupted (Ctrl-C). Skip the slow drain below — cancel
            # sub-agents fast and re-raise so no result/synthesis is produced.
            cancelled = True
            logger.info("Orchestrator run cancelled by user")
            raise
        except Exception as exc:
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
            # entries even when no final check_agents tool call took place.
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
                    _check_call_count_var,
                    _session_search_count_var,
                )
                search_count_box = _session_search_count_var.get()
                final_search_state.budget.consumed_queries = (
                    search_count_box[0] if search_count_box else 0
                )
                count_box = _check_call_count_var.get()
                if count_box is not None:
                    final_search_state.budget.current_iteration = count_box[0]
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
                    elif finalization_reason or orch_control.stopped:
                        committed_final_answer = await _finalize_stopped_research(
                            workspace=workspace, state=final_search_state, query=query,
                            orchestrator_model=self._model,
                            fallback_model=self._synthesis_model,
                            stop_reason=finalization_reason or "harness_stopped",
                            answer_stream=answer_stream, trajectory_logger=traj_logger,
                            conversation_logger=conv_logger,
                            follow_ups=steering.delivered if steering else (),
                            steering=steering,
                        )
                    else:
                        committed_final_answer = _write_findings_answer(
                            workspace, final_search_state, query, final_state,
                            execution_error=execution_error,
                            stop_reason=finalization_reason,
                        )
                        answer_stream.push(committed_final_answer)
                        answer_stream.finish()
                    traj_logger._append_raw({
                        "type": "harness", "kind": "post_session_phase",
                        "phase": "finalization",
                        "status": "done",
                    })
                except Exception:
                    logger.error(
                        "Harness finalization crashed; writing minimal marker",
                        exc_info=True,
                    )
                    try:
                        workspace.write_output(
                            "report.md",
                            f"# {query}\n\n_Finalization crashed. See logs._\n",
                        )
                    except Exception:
                        pass

        final_search_state = workspace.load_state()

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

        result = SearchResult(
            query=query,
            session_id=workspace.session_id,
            workspace_path=str(workspace.path),
            search_state=final_search_state,
            eval_verdict="UNASSESSED" if final_search_state.research_mode == "findings" else "COMPLETE",
            coverage_score=final_search_state.coverage_map.coverage_score,
            evidence_count=final_search_state.evidence_graph.node_count,
            total_queries=traj_logger.tool_counts.get("search", 0),
            total_steps=traj_logger.step_count,
            elapsed_s=elapsed,
            final_messages=final_messages,
            execution_error=execution_error,
        )

        # Log task_complete event (with total + per-phase token usage)
        token_dict = token_usage.to_dict()
        # Main-loop roles only; middleware one-shot calls are excluded
        # (their numbers stay visible in by_role).
        token_dict["cache_hit_rate"] = round(token_usage.cache_hit_rate, 4)
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
            "total_queries": result.total_queries,
            "total_steps": result.total_steps,
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
        result.model_distribution = self._model_distribution

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
                    "tool_counts": result.tool_counts,
                    "token_usage": result.token_usage,
                    "token_phases": result.token_phases,
                    "model_distribution": result.model_distribution,
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
        if settings.enable_access_skill_generation:
            async def _generate_trace_skills() -> None:
                from pathlib import Path
                from searchos.skills import generate_from_trace

                try:
                    lib = self._skill_library_path or "searchos/skills/library"
                    results = await generate_from_trace(
                        workspace.trajectory_path, library_path=Path(lib),
                        model=self._skill_evolver_model,
                        max_requests=settings.access_skill_max_per_run,
                    )
                    installed = sum(1 for r in results if r.status == "installed")
                    logger.info("Trace skill generation finished: %d installed/updated, %d requests",
                                installed, len(results))
                except Exception:
                    logger.warning("Trace skill generation failed", exc_info=True)

            access_task = asyncio.create_task(
                _generate_trace_skills(), name=f"skill-gen-{workspace.session_id}",
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


async def _finalize_stopped_research(*, workspace, state, query, orchestrator_model,
                                     fallback_model=None, stop_reason,
                                     answer_stream=None, trajectory_logger=None,
                                     conversation_logger=None, follow_ups=(), steering=None) -> str:
    """子任务回收后由 Orchestrator 生成终止轮，Synthesis 仅作降级。"""
    from langchain_core.messages import AIMessage

    from searchos.harness.report.synthesis import finalize_research

    if steering is not None and conversation_logger is not None:
        from searchos.harness.telemetry.conversation import langchain_msg_to_conversation_msgs

        # The research stream is closed. Record late input here while the
        # tool-free finalization graph owns the same inbox.
        def record_follow_up(message):
            for entry in langchain_msg_to_conversation_msgs(message):
                conversation_logger.log(entry)

        steering.on_delivery = record_follow_up

    draft = ""
    execution_error = ""
    orchestrator_error = ""
    finalizer = "orchestrator"
    try:
        draft = await finalize_research(
            state=state, query=query, model=orchestrator_model,
            stop_reason=stop_reason,
            follow_ups=follow_ups,
            steering=steering,
            max_chars=settings.research_finalize_max_chars,
            timeout_s=settings.research_finalize_timeout_s,
        )
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        orchestrator_error = type(exc).__name__
        logger.warning(
            "Orchestrator final turn failed (%s); trying synthesis fallback",
            orchestrator_error,
        )
        if fallback_model is not None:
            finalizer = "synthesis"
            try:
                draft = await finalize_research(
                    state=state, query=query, model=fallback_model,
                    stop_reason=stop_reason,
                    follow_ups=follow_ups,
                    steering=steering,
                    max_chars=settings.research_finalize_max_chars,
                    timeout_s=settings.research_finalize_timeout_s,
                )
            except asyncio.CancelledError:
                raise
            except Exception as fallback_exc:
                execution_error = type(fallback_exc).__name__
                logger.warning(
                    "Synthesis fallback failed: %s", execution_error,
                )
        else:
            execution_error = orchestrator_error
    state = workspace.load_state()
    answer = _write_findings_answer(
        workspace, state, query, {"messages": [AIMessage(content=draft)]},
        execution_error=execution_error, stop_reason=stop_reason,
    )
    if conversation_logger is not None:
        from searchos.harness.telemetry.trajectory import ConversationMessage

        conversation_logger.log(ConversationMessage(
            role="assistant",
            content=answer,
            metadata={
                "phase": "final_answer",
                "finalizer": finalizer,
                "stop_reason": stop_reason,
            },
        ))
    if trajectory_logger is not None:
        trajectory_logger._append_raw({
            "type": "harness",
            "kind": "research_finalized",
            "stop_reason": stop_reason,
            "finalizer": finalizer,
            "orchestrator_error": orchestrator_error,
            "execution_error": execution_error,
        })
    if answer_stream is not None:
        answer_stream.push(answer)
        answer_stream.finish()
    return answer


def _write_findings_answer(workspace, state, query, final_state, *, execution_error="",
                           stop_reason="") -> str:
    """保存正文，将事实引用解析到原文并记录缺失；不作语义核验。"""
    import json

    from searchos.local.library import _LOCAL_LINK_RE
    from searchos.socm.coverage import answer_evidence

    nodes = answer_evidence(state)
    from searchos.harness.report.grounding import final_answer_text
    answer = final_answer_text(final_state)
    from searchos.socm.provenance import evidence_source_urls
    canonical = {url: url for node in nodes for url in evidence_source_urls(node) if url.startswith("local://")}
    from searchos.local.reader.references import parse_ref_id
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
    from searchos.socm.provenance import resolve_answer_citations
    answer, citation_issues = resolve_answer_citations(answer, nodes)
    answer = _LOCAL_LINK_RE.sub(lambda m: canonical.get(m.group(0), "invalid-local-reference"), answer)
    from searchos.socm.research_plan import membership_review
    workspace.write_output("report.md", answer)
    workspace.write_output("result.json", json.dumps({
        "query": query, "answer": answer, "mode": mode,
        "execution_error": execution_error,
        "stop_reason": stop_reason,
        "citation_issues": citation_issues,
        "research_plan": state.research_plan.model_dump() if state.research_plan else None,
        "membership_review": membership_review(state),
        "evidence_count": len(nodes),
        "coverage": state.coverage_map.coverage_score,
        "frontier_progress": _frontier_progress(state),
    }, ensure_ascii=False, indent=2))
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

    from searchos.socm.provenance import resolve_answer_citations
    from searchos.socm.research_plan import membership_review
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
        self.total_queries = total_queries
        self.total_steps = total_steps
        self.elapsed_s = elapsed_s
        self.final_messages = final_messages or []
        self.execution_error = execution_error
        self.access_task: asyncio.Task[None] | None = None
        self.token_usage: dict[str, Any] = {}
        self.token_phases: dict[str, Any] = {}
        self.browser_usage: dict[str, int] = {}
        self.tool_counts: dict[str, int] = {}
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
