"""SearchSession: Main Agent (Orchestrator) as the sole decision maker.

The Orchestrator explores, plans, dispatches Sub Agents, evaluates, and synthesizes.
No external auto_plan or DAGExecutor — the Orchestrator owns the full loop.
"""

from __future__ import annotations

import asyncio
import logging
import queue as _queue
import time
from typing import Any

from langchain_core.language_models import BaseChatModel

from searchos.harness.blueprint import SearchBlueprint
from searchos.config.settings import settings
from searchos.skills.catalog.registry import SkillRegistry
from searchos.socm import SearchState
from searchos.socm import WorkspaceManager

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


def _premature_end_reason(workspace: WorkspaceManager, harness: Any) -> str | None:
    """Decide whether the orchestrator's no-tool-call exit left work behind.

    The ReAct loop ends whenever the model emits a message without tool
    calls — including degenerate ones where the intended action is written
    as plain text. Returns a resume reason when structural evidence says
    the session isn't done, or None when the end is legitimate (harness
    initiated the stop, or nothing actionable remains).
    """
    if getattr(harness, "harness_stop_fired", False):
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

    Unsafe iff the last message is an AI turn carrying tool calls whose
    ToolMessages haven't landed yet — injecting a HumanMessage there would
    leave dangling tool_calls and some providers reject the next request.
    """
    msgs = event.get("messages") or []
    if not msgs:
        return True
    last = msgs[-1]
    if getattr(last, "type", None) == "ai" and (getattr(last, "tool_calls", None) or []):
        return False
    return True


def _steer_nudge(text: str) -> str:
    return (
        "[用户追问 — 实时插入]\n"
        f"{text}\n\n"
        "请在当前进展的基础上响应该追问：可以调整计划、补充或重排任务，或直接作答。"
        "此前已分派的子代理仍在后台运行，无需重复分派相同的工作。"
    )


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
        3. Orchestrator autonomously: explore → schema → spawn sub-agents →
           poll → continue/spawn as needed
        4. Harness finalizes: synthesize report, collect results, mine skills
    """

    def __init__(
        self,
        *,
        blueprint: SearchBlueprint | None = None,
        skill_registry: SkillRegistry | None = None,
        workspace_root: str = settings.workspace_root,
        skill_library_path: str = "",
        skill_exclude: list[str] | None = None,
        model_overrides: dict[str, BaseChatModel] | None = None,
        skip_synthesis: bool | None = None,
    ) -> None:
        """Models are pulled from settings.profiles + settings.roles via
        ``model_factory.get_model_for(role)``. ``model_overrides`` lets
        tests inject a stub for a specific role without touching settings.
        """
        from searchos.config.models import get_model_for

        overrides = model_overrides or {}

        def _resolve(role: str) -> BaseChatModel:
            return overrides.get(role) or get_model_for(role)

        self._model = _resolve("orchestrator")
        self._judge_model = _resolve("judge")
        self._extraction_model = _resolve("extraction")
        self._alias_resolver_model = _resolve("alias_resolver")
        self._synthesis_model = _resolve("synthesis")
        self._skill_evolver_model = _resolve("skill_evolver")
        self._post_mortem_model = _resolve("post_mortem")
        # sub_agent / skill_runtime are pulled lazily inside the spawn /
        # access-skill paths; keep references so token-tracker callbacks
        # are bound consistently.
        self._sub_agent_model = _resolve("sub_agent")
        self._skill_runtime_model = _resolve("skill_runtime")

        role_models = {
            "orchestrator": self._model,
            "judge": self._judge_model,
            "extraction": self._extraction_model,
            "alias_resolver": self._alias_resolver_model,
            "synthesis": self._synthesis_model,
            "skill_evolver": self._skill_evolver_model,
            "post_mortem": self._post_mortem_model,
            "sub_agent": self._sub_agent_model,
            "skill_runtime": self._skill_runtime_model,
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

        self._blueprint = blueprint or SearchBlueprint()
        self._skill_registry = skill_registry
        self._workspace_root = workspace_root
        self._skill_library_path = skill_library_path or self._blueprint.skill_library_path
        self._skill_exclude = list(skill_exclude or [])
        self._skip_synthesis = skip_synthesis if skip_synthesis is not None else settings.skip_synthesis

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

    async def run(
        self,
        query: str,
        *,
        session_id: str | None = None,
        initial_state: SearchState | None = None,
        context_preamble: str | None = None,
        on_event: "Callable[[dict], None] | None" = None,
        steer_queue: "asyncio.Queue[str] | _queue.Queue[str] | None" = None,
        access_only: "set[str] | None" = None,
        access_deny: "set[str] | None" = None,
        strategy_deny: "set[str] | None" = None,
        orchestrator_deny: "set[str] | None" = None,
        trusted_domains: "list[str] | None" = None,
        excluded_domains: "list[str] | None" = None,
        follow_up: bool = False,
        targeted_repair_task_ids: "set[str] | None" = None,
        targeted_repair_cells: "list[str] | None" = None,
    ) -> SearchResult:
        """Execute a complete search session via Orchestrator pattern.

        ``context_preamble`` (optional): prior-turn conversational background
        injected ahead of the query in the orchestrator's first user message,
        enabling multi-turn follow-ups. ``query`` itself stays unchanged for
        logging/metadata.

        ``steer_queue`` (optional): a queue the caller pushes live user
        follow-ups onto while the run is in flight. At safe step boundaries the
        orchestrator loop drains it and re-enters its thread with the message
        injected, steering the run without killing in-flight sub-agents.

        ``access_only`` (optional): when set, the orchestrator's access-skill
        catalog is restricted to exactly these skill names, overriding the
        query-driven router. ``access_deny`` (optional): names removed from the
        catalog whatever the router selects. Both let the interactive TUI's
        ``/skill`` command pin / disable specific access skills.

        ``strategy_deny`` (optional): strategy-skill names hidden from the
        sub-agent catalog. ``orchestrator_deny`` (optional): orchestrator-skill
        names dropped from the orchestrator playbook. Both default to all-on;
        the ``/skill`` picker passes the names the user has unchecked.

        ``trusted_domains`` rank matching search results first while
        ``excluded_domains`` remove matching results and block direct opens.
        Both controls are task-local and inherited by spawned sub-agents.
        """
        start_time = time.time()
        targeted_repair_mode = (
            targeted_repair_cells is not None
            or targeted_repair_task_ids is not None
        )

        # --- Token tracking (per-run, ContextVar-backed) ---
        from searchos.util.token_tracker import start_tracking
        token_usage = start_tracking()

        # --- Workspace ---
        workspace = WorkspaceManager(self._workspace_root, session_id)
        workspace.create()

        # --- Reset cross-agent browser state for this fresh session ---
        from searchos.tools.simple_browser.state import reset_browser, set_source_controls
        reset_browser()
        source_controls = set_source_controls(trusted_domains, excluded_domains)

        # --- State ---
        state = initial_state or SearchState(intent=query)
        if not state.intent:
            state.intent = query

        workspace.save_state(state)

        # --- Skill registry ---
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
        # Follow-up turns reuse the same session workspace; load prior turns
        # from disk so this turn's messages append instead of overwriting.
        conv_logger.hydrate()

        # --- Log task_start event ---
        from datetime import datetime, timezone
        traj_logger._append_raw({
            "type": "task_start",
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
        })

        # --- Set up orchestrator tools context ---
        from searchos.agents.orchestrator import get_orchestrator_tools
        from searchos.agents.runtime import set_orchestrator_context
        from searchos.tools.simple_browser.state import set_browser_provider
        from searchos.tools.search_state import set_workspace
        from searchos.tools.simple_browser.state import _provider

        set_workspace(workspace)
        set_orchestrator_context(
            workspace=workspace,
            model=self._model,
            skill_registry=self._skill_registry,
            trajectory_logger=traj_logger,
            conversation_logger=conv_logger,
            judge_model=self._judge_model,
            extraction_model=self._extraction_model,
            alias_resolver_model=self._alias_resolver_model,
            sub_agent_model=self._sub_agent_model,
            skill_runtime_model=self._skill_runtime_model,
            skill_evolver_model=self._skill_evolver_model,
            post_mortem_model=self._post_mortem_model,
            query=query,
            scheduler_task_allowlist=targeted_repair_task_ids,
            repair_target_allowlist=(
                set(targeted_repair_cells or ()) if targeted_repair_mode else None
            ),
        )
        if _provider is not None:
            set_browser_provider(_provider)


        from searchos.agents.orchestrator.catalog import generate_agent_catalog_text
        from searchos.agents.orchestrator.prompt import build_orchestrator_prompt
        from searchos.agents.runtime import create_search_agent_graph

        from datetime import datetime as _dt
        orchestrator_tools = get_orchestrator_tools()
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
        if settings.enable_skills:
            from searchos.skills.core.models import SkillCategory
            from searchos.skills.catalog.router import render_playbook
            orch_candidates = self._skill_registry.list_by_category(SkillCategory.ORCHESTRATOR)
            if orchestrator_deny:
                orch_candidates = [
                    s for s in orch_candidates if s.meta.name not in orchestrator_deny
                ]
            orchestrator_playbook = render_playbook(orch_candidates)

            # Query-driven top-k pre-filter; fail-open (None → full catalog).
            access_allow = None
            if settings.enable_skill_router:
                from searchos.skills.catalog.router import select_access_skills
                access_allow = await select_access_skills(
                    query,
                    self._skill_registry,
                    top_k=settings.skill_router_top_k,
                )
            # TUI /skill overrides: ``access_only`` pins the catalog to an exact
            # set (ignoring the router); ``access_deny`` subtracts names from
            # whatever the catalog would otherwise be.
            if access_only is not None:
                access_allow = set(access_only)
            if access_deny:
                if access_allow is None:
                    access_allow = {
                        s.meta.name
                        for s in self._skill_registry.list_by_category(SkillCategory.ACCESS)
                    }
                access_allow = set(access_allow) - set(access_deny)
            # Strategy skills carry no router; default all-on, minus any the
            # /skill picker unchecked.
            strategy_allow = None
            if strategy_deny:
                strategy_allow = {
                    s.meta.name
                    for s in self._skill_registry.list_by_category(SkillCategory.STRATEGY)
                } - set(strategy_deny)
            skill_catalog = self._skill_registry.generate_catalog(
                access_allow=access_allow, strategy_allow=strategy_allow)
        else:
            orchestrator_playbook = ""
            skill_catalog = ""

        system_prompt = build_orchestrator_prompt(
            agent_catalog=generate_agent_catalog_text(),
            skill_catalog=skill_catalog,
            max_dispatches=settings.orch_max_dispatches,
            max_searches_per_agent=settings.max_searches_per_sub_agent,
            # Date-only: minute precision forks the prompt-cache prefix
            # across sessions started in different minutes.
            current_time=_dt.now().strftime("%Y-%m-%d"),
            orch_toolset=render_toolset(orchestrator_tools, header="## Available Tools"),
            enable_explore=settings.enable_explore,
            orchestrator_playbook=orchestrator_playbook,
            follow_up=follow_up or bool(context_preamble),
        )
        if targeted_repair_mode:
            system_prompt += (
                "\n\n## Targeted Repair Mode (overrides the normal workflow)\n"
                "The selected cells in the user message are an immutable allowlist. "
                "Plan the work yourself and call `enqueue_tasks` with search_agent "
                "tasks. Every task MUST provide the exact `target_table` and explicit "
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

        from searchos.harness.middleware.sensor.harness import (
            BudgetState,
            HarnessMiddleware,
        )
        from deepagents.backends import FilesystemBackend

        # Orchestrator never calls `search` — bound by iterations + sensors.
        orch_budget = BudgetState(
            max_queries=0,
            max_iterations=settings.orch_max_iterations,
            max_time_s=self._blueprint.budget.max_time_s,
        )
        from searchos.harness.middleware.sensor.dispatch_round_sensor import (
            DispatchRoundSensor,
        )
        orch_harness = HarnessMiddleware(
            sensors=[
                DispatchRoundSensor(max_rounds=settings.orch_max_dispatches),
            ],
            budget=orch_budget,
            trajectory_logger=traj_logger,
            workspace=workspace,
            worker_name="orchestrator",
        )
        from searchos.harness.middleware import build_layered_stack
        from searchos.harness.middleware.context import ControlMiddleware
        orch_middleware = build_layered_stack(
            control=[ControlMiddleware(
                trim_max_tokens=settings.orch_trim_max_tokens, force_layered=False,
            )],
            sensor=[orch_harness],
        )
        orch_backend = FilesystemBackend(
            root_dir=str(workspace.path / "orchestrator_logs"),
            virtual_mode=False,
        )

        graph = create_search_agent_graph(
            model=self._model,
            tools=orchestrator_tools,
            system_prompt=system_prompt,
            middleware=orch_middleware,
            backend=orch_backend,
            name="orchestrator",
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

        # --- Run Orchestrator ---
        logger.info(
            "Starting Orchestrator: %s (session=%s)",
            query[:60],
            workspace.session_id,
        )
        final_state = None
        prev_msg_count = 0

        pending_tool_calls: dict[str, dict[str, Any]] = {}
        phase_tracker = _PhaseTracker(token_usage)
        cancelled = False  # set when the user interrupts (Ctrl-C → task.cancel)
        try:
            model_name = getattr(self._model, "model_name", None) or getattr(self._model, "model", "") or ""
            # SOCM context is injected on every orchestrator step by
            # HarnessMiddleware._render_socm_via_views, so no need to
            # bake a snapshot into the initial user message.
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
                    "search_agent tasks with enqueue_tasks; set target_table and "
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
                injected_steer: str | None = None
                async for event in graph.astream(
                    input_payload,
                    config=astream_config,
                    stream_mode="values",
                ):
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
                                # Persist too, so file-tailing UIs (the web WS)
                                # see the call the moment it starts — the full
                                # `step` record only lands after the tool
                                # returns, which for check_agents can be
                                # minutes later.
                                try:
                                    traj_logger._append_raw({
                                        "type": "tool_call_started",
                                        "agent": "orchestrator",
                                        "tool": _name, "tool_call_id": _tcid,
                                        "args": _full_args(_targs),
                                    })
                                except Exception:
                                    pass

                    # Live steering: at a safe boundary (the last message is
                    # not an AI turn with unanswered tool calls), drain any
                    # queued user follow-up and break to re-enter the thread
                    # with it. Sub-agents in the task pool keep running.
                    if (
                        steer_queue is not None
                        and not steer_queue.empty()
                        and _is_safe_steer_boundary(event)
                    ):
                        drained: list[str] = []
                        while not steer_queue.empty():
                            try:
                                drained.append(steer_queue.get_nowait())
                            except (asyncio.QueueEmpty, _queue.Empty):
                                break
                        if drained:
                            injected_steer = "\n".join(drained)
                            traj_logger._append_raw({
                                "type": "harness",
                                "kind": "steer_injected",
                                "text": injected_steer[:300],
                            })
                            break

                if injected_steer is not None:
                    # Re-enter the same thread_id with the follow-up as a new
                    # user message; the checkpoint from the broken step carries
                    # the full prior context.
                    input_payload = {
                        "messages": [
                            {"role": "user", "content": _steer_nudge(injected_steer)},
                        ],
                    }
                    continue

                reason = _premature_end_reason(workspace, orch_harness)
                if (
                    reason is None
                    or resume_attempts >= settings.orch_premature_end_max_resumes
                ):
                    if reason is not None:
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
        except Exception:
            logger.error("Orchestrator execution failed", exc_info=True)
        finally:
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
                        "phase": "synthesis",
                        "status": "start",
                    })
                    if self._skip_synthesis:
                        _export_eval_table(
                            workspace=workspace,
                            state=final_search_state,
                            query=query,
                        )
                    else:
                        await _harness_synthesize(
                            workspace=workspace,
                            state=final_search_state,
                            query=query,
                            model=self._synthesis_model,
                        )
                    traj_logger._append_raw({
                        "type": "harness", "kind": "post_session_phase",
                        "phase": "synthesis",
                        "status": "done",
                    })
                except Exception:
                    logger.error(
                        "Harness synthesis crashed; writing minimal marker",
                        exc_info=True,
                    )
                    try:
                        workspace.write_output(
                            "report.md",
                            f"# {query}\n\n_Synthesis crashed. See logs._\n",
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

        result = SearchResult(
            query=query,
            session_id=workspace.session_id,
            workspace_path=str(workspace.path),
            search_state=final_search_state,
            eval_verdict="COMPLETE",
            coverage_score=final_search_state.coverage_map.coverage_score,
            evidence_count=final_search_state.evidence_graph.node_count,
            total_queries=traj_logger.tool_counts.get("search", 0),
            total_steps=traj_logger.step_count,
            elapsed_s=elapsed,
            final_messages=final_messages,
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
        })
        result.token_usage = token_dict
        result.token_phases = token_phases
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

        # --- Reactive access-skill generation (fire-and-forget, opt-in) ---
        # Independent of skill evolution. Off by default
        # (settings.enable_access_skill_generation). When on, hosts opened
        # repeatedly in this run's trajectory are baked into agent_called
        # skills via the LLM-driven dynamic builder, so later runs can call
        # them as typed ``skill_<name>`` tools.
        if settings.enable_access_skill_generation:
            async def _generate_access_skills() -> None:
                from pathlib import Path
                from searchos.skills.evolution.host_miner import (
                    generate_access_skills_from_trace,
                )
                try:
                    lib = self._skill_library_path or "searchos/skills/library"
                    reports = await generate_access_skills_from_trace(
                        workspace.trajectory_path,
                        judge_model=self._skill_evolver_model,
                        library_path=Path(lib) / "access",
                        max_per_run=settings.access_skill_max_per_run,
                        min_opens=settings.access_skill_min_opens,
                        obs_chars=settings.access_skill_obs_chars,
                    )
                    installed = sum(1 for r in reports if r.get("status") == "installed")
                    if installed:
                        logger.info("Generated %d access skill(s)", installed)
                except Exception:
                    logger.warning("Access-skill generation failed", exc_info=True)

            access_task = asyncio.create_task(
                _generate_access_skills(),
                name=f"access-gen-{workspace.session_id}",
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


async def _harness_synthesize(
    *,
    workspace: WorkspaceManager,
    state: SearchState,
    query: str,
    model: Any,
) -> None:
    """Harness-owned final report generation.
    """
    logger.info(
        "_harness_synthesize called: session=%s, evidence=%d, coverage=%.0f%%",
        workspace.session_id, state.evidence_graph.node_count,
        state.coverage_map.coverage_score * 100,
    )
    import json as _json

    evidence = state.evidence_graph.nodes

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

    # ---- Common: URL citation map + coverage table + sources ----
    # These are deterministic / code-built and used by both the
    # outline-first path and the Phase 2 fallback below.
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

    # ---- 报告产出:续写 writer 线程拿正文 + 代码拼 coverage table/sources ----
    # LLM 多阶段兜底已弃用 —— writer 是唯一叙述正文来源;无 writer 时降级为纯
    # 结构化表(coverage table + sources),不再发起任何 synthesis LLM 调用。
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
    if finalize_body:
        writer_body, writer_agent_id = finalize_body
        report = _assemble(writer_body.strip())
        workspace.write_output("report.md", report)
        workspace.write_output("result.json", _json.dumps({
            "query": query,
            "answer": report,
            "mode": "writer_finalize",
            "writer_agent_id": writer_agent_id,
            "evidence_count": len(evidence),
            "coverage": state.coverage_map.coverage_score,
            "evidence_backed_coverage": _evidence_backed_coverage(state),
            "frontier_progress": _frontier_progress(state),
            "outline_sections_total": total_sec,
            "outline_sections_with_content": sec_with_content,
            "url_citations": url_map,
        }, ensure_ascii=False, indent=2))
        logger.info(
            "Harness synthesis (writer_finalize): writer=%s, %d evidence, "
            "%d unique sources, body_len=%d",
            writer_agent_id, len(evidence), len(url_map), len(writer_body),
        )
        return

    # 兜底:无 writer / finalize 失败 → 渲染 outline 原文;无 outline 则纯结构化表
    logger.info(
        "Harness synthesis: writer_finalize unavailable, "
        "falling back to outline-verbatim render",
    )
    outline_body = state.outline.rendered().strip()
    report = _assemble(outline_body if outline_body else "")
    workspace.write_output("report.md", report)
    workspace.write_output("result.json", _json.dumps({
        "query": query,
        "answer": report,
        "mode": "outline_writer" if outline_body else "structured_only",
        "evidence_count": len(evidence),
        "coverage": state.coverage_map.coverage_score,
        "evidence_backed_coverage": _evidence_backed_coverage(state),
        "frontier_progress": _frontier_progress(state),
        "outline_sections_total": total_sec,
        "outline_sections_with_content": sec_with_content,
        "url_citations": url_map,
    }, ensure_ascii=False, indent=2))
    logger.info(
        "Harness synthesis (outline_writer): %d/%d sections with content, "
        "%d evidence, %d unique sources",
        sec_with_content, total_sec, len(evidence), len(url_map),
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
    """Continue the writer sub-agent's LangGraph thread with a 'finalize'
    HumanMessage and return ``(body_markdown, writer_agent_id)``.

    Bypasses the orchestrator tools layer (no budget gate): the
    search run may have terminated via ``budget_exhausted`` + hard_block,
    but synthesis owns the terminal step. We feed HumanMessage directly
    to ``graph.astream`` on the writer's thread_id.

    Returns None on any failure (no writer registered, astream raised,
    empty body) — caller should fall back to outline-verbatim render.
    """
    from searchos.agents.runtime import _ctx
    from searchos.harness.report.synthesis import build_writer_finalize_message

    try:
        graphs = _ctx.agent_graphs
    except RuntimeError:
        logger.info("writer_finalize: no orchestrator context (agent_graphs)")
        return None

    # Pick the most recently registered writer sub-agent. agent_type is
    # "writer_agent" per agents/catalog.py:101.
    writer_entries = [
        (aid, info) for aid, info in graphs.items()
        if info.get("agent_type") == "writer_agent"
    ]
    if not writer_entries:
        logger.info("writer_finalize: no writer_agent in registry")
        return None
    # "Most recent" — started_at monotonic, highest wins.
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
        async for event in graph.astream(
            {"messages": [{"role": "user", "content": message}]},
            config={"configurable": {"thread_id": thread_id}},
            stream_mode="values",
        ):
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
        self.access_task: asyncio.Task[None] | None = None
        self.token_usage: dict[str, Any] = {}
        self.token_phases: dict[str, Any] = {}
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
