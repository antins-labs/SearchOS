"""Orchestrator sub-agent lifecycle (paper §Agent Roles).

Spawn → run → collect machinery for the orchestrator's sub-agents, plus the
prompt / scope / report helpers it needs. The @tool surface lives in
``searchos.tools.tasks`` (queue) and ``searchos.tools.schema``
(schema); this module holds the spawn lifecycle those tools and the Scheduler
drive. ``_ctx`` and friends are re-exported from ``searchos.agents.runtime`` so
the Scheduler / task tools import everything from one place.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from searchos.agents.runtime import (
    _ctx,  # noqa: F401 — re-exported (scheduler / skill_catalog import _ctx from here)
    _post_mortem_count_var,
    _post_mortem_tasks_var,
    _sub_agent_counter_var,
)
from searchos.agents import explore as _explore, search as _search, writer as _writer
from searchos.agents.orchestrator.post_mortem import (
    build_failure_memory_prompt as _build_failure_memory_prompt,
    run_post_mortem as _run_post_mortem,
)

logger = logging.getLogger(__name__)

# Role packages own their own ``get_tools`` / ``agent.md`` (paper §Agent Roles).
_ROLE_REGISTRY = {
    _explore.AGENT_TYPE: _explore,
    _search.AGENT_TYPE: _search,
    _writer.AGENT_TYPE: _writer,
}

_MD_TABLE_SEP_RE = re.compile(
    r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)+\|?\s*$"
)
_SCOPE_AUDIT_NOTE = (
    "Before ending, audit the ROW SET against the task's expected scope: "
    "enumerate the dimensions the query implies (years, regions, categories, "
    "top-N, ...) and check every combination has rows. Fill rates count only "
    "rows already in the schema — all-filled does NOT mean the scope is "
    "covered. If rows are missing, add_entities + enqueue_tasks for the "
    "gaps; end your turn only when the audit passes or further search "
    "cannot help."
)
WRITER_CONTINUE_EVIDENCE_DELTA = 3
MAX_SKILLS_PER_DISPATCH = 5
_OUTLINE_MIN_SECTIONS = 3
_OUTLINE_CONTENT_RATIO = 0.6
_ANTIPATTERN_DECAY_S = 1800  # 30 min — patterns older than this drop from prompt
_ANTIPATTERN_BLOCK_THRESHOLD = 2  # 2+ = "proven invalid, avoid"
_EXPLORE_PAGE_URL_HDR = re.compile(r"^URL:\s*(\S+)", re.MULTILINE)
_EXPLORE_PAGE_MIN_CHARS = 300
_EXPLORE_PAGE_MAX_CHARS = 30_000  # per-page cap fed to extraction
_KNOWN_AGENT_TYPES = {"search_agent", "writer_agent", "explore_agent"}
_KIND_FROM_AGENT = {
    "search_agent": "search",
    "writer_agent": "write",
    "explore_agent": "explore",
}
_KIND_TO_AGENT_BY_KIND = {
    "search": "search_agent",
    "write": "writer_agent",
    "explore": "explore_agent",
}

_LEGACY_EXPLORE_BUDGET = {"max_searches": 8, "max_opens": 8, "max_finds": 8}


def _agent_budget_override(agent_type: str) -> dict[str, int]:
    """Resolve the active per-role budget, including Explore rollback mode."""
    from searchos.config.settings import AGENT_BUDGET_OVERRIDES, settings

    if agent_type == "explore_agent" and not settings.enable_explore_batch:
        return dict(_LEGACY_EXPLORE_BUDGET)
    return dict(AGENT_BUDGET_OVERRIDES.get(agent_type, {}))


def _strip_markdown_tables(text: str) -> str:
    """Replace markdown pipe-tables in a sub-agent brief with a one-line stub.

    Search agents often re-paste the whole table they just extracted into
    their final brief. That data is already captured as evidence/cells, so
    echoing it to the orchestrator is pure context bloat. Prose around the
    table (the actual conclusions) is kept; each table block collapses to
    ``[data table omitted — N rows]``.
    """
    if not text or "|" not in text:
        return text
    lines = text.split("\n")
    out: list[str] = []
    i, n = 0, len(lines)
    while i < n:
        if i + 1 < n and "|" in lines[i] and _MD_TABLE_SEP_RE.match(lines[i + 1]):
            j = i + 2
            while j < n and "|" in lines[j]:
                j += 1
            out.append(f"[data table omitted — {j - (i + 2)} rows]")
            i = j
        else:
            out.append(lines[i])
            i += 1
    return "\n".join(out)
def _format_full_list(items: list[Any], *, per_line: int = 20) -> str:
    """Render every item while keeping long prompt blocks scan-friendly."""
    vals = [str(x) for x in items]
    if not vals:
        return ""
    if len(vals) <= per_line:
        return ", ".join(vals)
    lines = []
    for i in range(0, len(vals), per_line):
        lines.append(", ".join(vals[i:i + per_line]))
    return "\n  " + "\n  ".join(lines)
def _format_capped_list(items: list[Any], *, cap: int = 30, show: int = 20) -> str:
    """Like ``_format_full_list`` but truncates past ``cap`` items — for
    writer prompt blocks where the full enumeration is queryable via tools."""
    vals = [str(x) for x in items]
    if len(vals) <= cap:
        return _format_full_list(vals)
    return f"{', '.join(vals[:show])} ... (+{len(vals) - show} more)"
def _check_schema_exists() -> str:
    """Preflight: schema must exist before dispatching data-collecting agents.

    Returns empty string on pass, error string on block.
    """
    assert _ctx.workspace is not None
    state = _ctx.workspace.load_state()
    if not state.coverage_map.tables:
        return (
            "Error: schema is empty. Call ``create_schema(tables_json=..., "
            "relations_json=...)`` BEFORE dispatching any sub-agents. "
            "Single-table queries pass a length-1 array; multi-table "
            "queries pass one object per table plus relations linking them."
        )
    return ""
async def _continue_sub_agent_run(
    agent_id: str,
    follow_up: str,
) -> Any:
    """Coroutine body for a `continue_agent` Task.

    Re-enters the same compiled graph via the same thread_id. MemorySaver
    restores prior ``messages`` / tool state; the ``follow_up`` human
    message is appended to that
    history. A fresh pre-snapshot is taken at continue-time so the new
    AgentReport's ``cells_filled`` / ``discovered_entities`` reflect only
    what changed during THIS continuation, not the agent's full lifetime.
    """
    import time

    info = _ctx.agent_graphs.get(agent_id)
    if info is None:
        from searchos.socm import AgentReport
        return AgentReport(
            agent_id=agent_id, status="error",
            result=f"cannot continue {agent_id}: not in agent graph registry",
        )

    graph = info["graph"]
    thread_id = info["thread_id"]
    scope_entities = info.get("scope_entities")
    # Refresh pre-snapshot + started_at for this turn's delta window.
    pre_snapshot = _snapshot_state_for_diff(_ctx.workspace.load_state())
    started_at = time.time()
    # Update registry so subsequent continue_agents on same id diff
    # against this turn's start, not the original spawn.
    info["pre_snapshot"] = pre_snapshot
    info["started_at"] = started_at
    info["wrapped_task"] = follow_up  # for trace parity
    info["continue_turn_count"] = info.get("continue_turn_count", 1) + 1

    if _ctx.trajectory_logger:
        _ctx.trajectory_logger._append_raw({
            "type": "continue",
            "agent": agent_id,
            "follow_up": follow_up[:200],
        })

    # Re-bind the "current agent" ContextVar so writer tools
    # can identify themselves. _spawn_sub_agent does this at initial
    # spawn; a continuation must repeat it because ContextVars are
    # per-task and the orchestrator's context may have been overwritten
    # by later spawns before this continue coroutine runs.
    from searchos.tools.search_state import (
        set_current_agent, set_current_table, set_current_task,
    )
    set_current_agent(thread_id)
    set_current_table(info.get("target_table", "") or "")
    # Re-bind the current task too: SOCM resolver reads it to scope
    # the per-agent view (entities whose name appears in task = in_scope).
    # Without this rebind, _continue_sub_agent_run leaves stale task
    # text from a sibling spawn that ran before in this orchestrator turn.
    set_current_task(info.get("task", "") or "")

    try:
        prev_msg_count = 0
        async for event in graph.astream(
            {"messages": [{"role": "user", "content": follow_up}]},
            config={"configurable": {"thread_id": thread_id}},
            stream_mode="values",
        ):
            if _ctx.conversation_logger and "messages" in event:
                from searchos.harness.telemetry.conversation import (
                    langchain_msg_to_conversation_msgs,
                )
                msgs = event["messages"]
                for msg in msgs[prev_msg_count:]:
                    for conv_msg in langchain_msg_to_conversation_msgs(msg):
                        conv_msg.agent_name = thread_id
                        conv_msg.parent_agent = "orchestrator"
                        _ctx.conversation_logger.log(conv_msg)
                prev_msg_count = len(msgs)

        # No global stats — see the comment in _collect_sub_agent_result.
        report = _compute_agent_report(
            agent_id=agent_id, thread_id=thread_id,
            pre_snapshot=pre_snapshot, started_at=started_at,
            status="completed", result="Continued",
            scope_entities=scope_entities,
        )
        # Logged AFTER report computation so the live view's agent tile
        # shows this agent's own delta, not a bare "Continued".
        if _ctx.trajectory_logger:
            _ctx.trajectory_logger._append_raw({
                "type": "agent_complete",
                "agent": agent_id,
                "turn": "continued",
                "summary": report.result,
            })
        _ctx.completed[agent_id] = report
        return report
    except Exception as e:
        import traceback

        tb = traceback.format_exc()
        logger.error(
            "continue_agent %s failed: %s(%s)",
            agent_id, type(e).__name__, str(e).strip(), exc_info=True,
        )
        err_msg = str(e).strip() or type(e).__name__
        if _ctx.trajectory_logger:
            _ctx.trajectory_logger._append_raw({
                "type": "agent_error",
                "agent": agent_id,
                "turn": "continued",
                "error": err_msg[:500],
                "error_type": type(e).__name__,
                "traceback": tb[-2000:],
            })
        report = _compute_agent_report(
            agent_id=agent_id, thread_id=thread_id,
            pre_snapshot=pre_snapshot, started_at=started_at,
            status="error", result=f"Error: {err_msg}",
            scope_entities=scope_entities,
        )
        _ctx.completed[agent_id] = report
        return report
def _find_writer_id() -> str | None:
    """Return the agent_id of the single writer (if one exists in this session).

    Writer is singleton by v2 design (§4 point 3: single writer, long-lived).
    """
    for aid, info in _ctx.agent_graphs.items():
        if info.get("agent_type") == "writer_agent":
            return aid
    return None
def _outline_status(state: Any) -> dict[str, Any]:
    """Summarize how 'done' the writer's outline is, plus pointer to a
    writer agent if one is registered. Used by check_agents to surface
    draft status to the orchestrator (so it knows where the draft stands
    without reading state itself).
    """
    sections = list(getattr(state.outline, "sections", []) or [])
    total = len(sections)
    with_content = sum(1 for s in sections if (s.content or "").strip())
    threshold = max(1, int(total * _OUTLINE_CONTENT_RATIO))
    complete = total >= _OUTLINE_MIN_SECTIONS and with_content >= threshold
    writer_id = _find_writer_id()
    writer_alive = bool(
        writer_id
        and writer_id in _ctx.task_pool
        and not _ctx.task_pool[writer_id].done()
    )
    return {
        "total_sections": total,
        "sections_with_content": with_content,
        "complete": complete,
        "writer_id": writer_id or "",
        "writer_alive": writer_alive,
    }
def _writer_last_evidence_count_var(writer_id: str) -> int:
    """Tracks last evidence count seen at writer's last continue.

    Stashed in agent_graphs[writer_id] so it survives across broker ticks.
    """
    info = _ctx.agent_graphs.get(writer_id, {})
    return info.get("last_evidence_count", 0)
def _set_writer_last_evidence_count(writer_id: str, n: int) -> None:
    info = _ctx.agent_graphs.get(writer_id)
    if info is not None:
        info["last_evidence_count"] = n
def _detect_scope_entities(task: str, entities: list[str]) -> set[str]:
    """Infer this sub-agent's owned entities by matching the task text.

    Dispatches routinely name several rows ("目标院校：A、B、C…"), so the
    scope is a SET — scoping reports to a single longest match undercounted
    every multi-row agent's cells/evidence to near zero. Empty set means no
    schema entity appears in the task (discovery / factoid / free-form
    exploration) — callers fall back to unscoped accounting.
    """
    if not task or not entities:
        return set()
    from searchos.harness.middleware.sensor.harness import HarnessMiddleware
    return HarnessMiddleware._match_entities_in_task(task, entities)
def _record_skill_failure(skill_name: str, params: dict) -> None:
    """Plan §5.5 写入来源 2 — record a kind=skill StrategyPattern when an
    access skill ran but produced zero new evidence. Scope to the
    target cell when params carry ``entity`` (+ optionally ``attribute``
    /``fields``) — otherwise record global.

    StrategyMemory.record dedups on (kind, signature), so a second
    failure bumps observed_count to 2 and the skill becomes ban-worthy
    under the §6.4 list_skills filter.
    """
    if _ctx.workspace is None:
        return
    from searchos.socm.strategy import record_strategy_pattern
    from searchos.socm import AntiPatternKind, AntiPatternScope
    entity = str(params.get("entity", "")).strip() if isinstance(params, dict) else ""
    attribute = ""
    if isinstance(params, dict):
        fields = params.get("fields") or params.get("attributes") or []
        if isinstance(fields, list) and fields:
            attribute = str(fields[0]).strip()
        elif isinstance(params.get("attribute"), str):
            attribute = params["attribute"].strip()
    cells: list[str] = []
    if entity and attribute:
        cells = [f"{entity}.{attribute}"]
    scope = AntiPatternScope(target_cells=cells, global_scope=not cells)

    record_strategy_pattern(
        _ctx.workspace,
        kind=AntiPatternKind.SKILL,
        signature=skill_name,
        scope=scope,
        reason="access-skill executor returned no new evidence",
        created_by="sensor",
    )
def _build_antipattern_prompt(state: Any, *, scope_entities: set[str] | None = None) -> str:
    """Plan §5.5 消费方 — render anti-patterns as a system-prompt block.

    Filters:
    - Scope: ``global_scope=True`` or ``target_cells`` matching any of
      the current spawn's scope entities (prefix ``"<entity>."``).
    - Age: entries older than ``_ANTIPATTERN_DECAY_S`` (30 min) are
      dropped — stale signals shouldn't dominate late-session decisions.
    - Severity: ``observed_count >= 2`` ⇒ rendered under "⛔ Blocked",
      ``observed_count == 1`` ⇒ "⚠ Warn" (try a different angle).
    Per-kind cap of 10 keeps the block bounded.
    """
    import time
    patterns = getattr(state, "strategy_log", None)
    if patterns is None:
        return ""
    records = getattr(patterns, "patterns", []) or []
    if not records:
        return ""

    now = time.time()

    def _in_scope(p: Any) -> bool:
        scope = getattr(p, "scope", None)
        if scope is None:
            return True
        if getattr(scope, "global_scope", False):
            return True
        cells = list(getattr(scope, "target_cells", []) or [])
        if not cells:
            return True
        if not scope_entities:
            return False
        return any(
            c == e or c.startswith(f"{e}.")
            for e in scope_entities for c in cells
        )

    # severity → kind → list of (sig, reason, count, age_s)
    by_sev: dict[str, dict[str, list[tuple[str, str, int, float]]]] = {
        "block": {k: [] for k in ("query", "source", "skill", "branch", "claim")},
        "warn":  {k: [] for k in ("query", "source", "skill", "branch", "claim")},
    }
    for p in records:
        if not _in_scope(p):
            continue
        age = now - (getattr(p, "last_seen", 0.0) or getattr(p, "first_seen", 0.0) or now)
        if age > _ANTIPATTERN_DECAY_S:
            continue
        kind = getattr(p.kind, "value", str(p.kind))
        if kind not in by_sev["block"]:
            continue
        bucket = "block" if p.observed_count >= _ANTIPATTERN_BLOCK_THRESHOLD else "warn"
        by_sev[bucket][kind].append((p.signature, p.reason, p.observed_count, age))

    if not any(any(v) for v in by_sev.values()):
        return ""

    for sev_buckets in by_sev.values():
        for kind, entries in sev_buckets.items():
            # Put the most repeated and most recent failures first so the
            # bounded prompt block preserves the highest-value warnings.
            sev_buckets[kind] = sorted(entries, key=lambda e: (-e[2], e[3]))

    labels = {
        "query": "Queries that returned no new evidence",
        "source": "Sources that returned placeholders / paywalls",
        "skill": "Skills that failed on the current cell",
        "branch": "Frontier subtrees already dropped",
        "claim": "Evidence claims marked rejected",
    }

    lines = ["## Anti-patterns (此 session 内已碰壁的路径)"]
    # Blocked section
    if any(by_sev["block"].values()):
        lines.append("\n### ⛔ Proven invalid — avoid (observed ≥2×)")
        for kind, entries in by_sev["block"].items():
            if not entries:
                continue
            lines.append(f"**{labels[kind]}:**")
            for sig, reason, count, age in entries[:10]:
                detail = f" — {reason[:90]}" if reason else ""
                lines.append(f"- `{sig[:80]}` (×{count}, {int(age/60)}m ago){detail}")
    # Warn section
    if any(by_sev["warn"].values()):
        lines.append("\n### ⚠ Tried once — prefer a different angle")
        for kind, entries in by_sev["warn"].items():
            if not entries:
                continue
            lines.append(f"**{labels[kind]}:**")
            for sig, reason, count, age in entries[:10]:
                detail = f" — {reason[:90]}" if reason else ""
                lines.append(f"- `{sig[:80]}` ({int(age/60)}m ago){detail}")
    return "\n".join(lines)
def _build_sub_agent_context(state: Any, *, agent_type: str | None = None) -> str:
    """Render the SOCM schema overview for a sub-agent.

    Sub-agents receive only the task text; this block lists every
    table's schema (and relations) so the agent knows what entities /
    attributes / relations exist. Cell-level filling is the
    orchestrator's responsibility — the agent should browse, extract,
    and let the middleware write evidence.
    """
    if agent_type == "writer_agent":
        return _build_writer_socm_block(state)

    cmap = getattr(state, "coverage_map", None)
    if cmap is None or not cmap.tables:
        return ""

    lines: list[str] = ["## Schema (read-only)"]
    for tid, ts in cmap.tables.items():
        label = ts.table_label or tid
        lines.append(f"### {label} (`{tid}`)")
        if ts.primary_key:
            lines.append(f"- Primary key: {', '.join(ts.primary_key)}")
        if ts.row_label:
            lines.append(f"- Row: {ts.row_label}")
        lines.append(f"- Attributes: {', '.join(ts.attributes)}")
        if ts.entities:
            lines.append(
                f"- Known rows ({len(ts.entities)}): "
                f"{_format_full_list(ts.entities)}"
            )

    if cmap.relations:
        lines.append("### Relations")
        for r in cmap.relations:
            fk = ",".join(r.foreign_key.columns)
            tc = ",".join(r.foreign_key.target_columns)
            tail = f" — {r.label}" if r.label else ""
            lines.append(
                f"- {r.from_table}.[{fk}] → {r.foreign_key.target_table}.[{tc}] "
                f"({r.kind.value}){tail}"
            )

    lines.append("")
    lines.append(
        "Note: extract evidence by browsing — the middleware records findings into "
        "the evidence graph; the orchestrator maps evidence to cells later."
    )
    return "\n".join(lines)
def _build_writer_socm_block(state: Any) -> str:
    """Compact SOCM summary for writer_agent: coverage progress + open questions.

    Writer has global drafting responsibility, so it gets an overview
    instead of the task-cells slice that search agents receive.
    """
    from searchos.tools.socm_read import coverage_summary

    cmap = getattr(state, "coverage_map", None)
    lines = ["## Coverage Progress"]
    if cmap is not None and cmap.total_cells > 0:
        summary = coverage_summary(state)
        by_status = summary["by_status"]
        filled = by_status.get("filled", 0)
        pct = round(100 * filled / summary["total"]) if summary["total"] else 0
        lines.append(
            f"Filled: {filled}/{summary['total']} cells ({pct}%) | "
            f"uncertain: {by_status.get('uncertain', 0)} | "
            f"missing: {by_status.get('missing', 0)} | "
            f"conflicts: {len(summary['conflict_cells'])}"
        )
        for t in summary["tables"]:
            lines.append(
                f"Table {t['table_label'] or t['table_id']}: "
                f"{t['n_entities']} entities × {t['n_attributes']} attributes"
            )
        lines.append(
            f"Entities ({len(cmap.table_schema.entities)}): "
            f"{_format_capped_list(cmap.table_schema.entities)}"
        )
        lines.append(
            f"Attributes ({len(cmap.table_schema.attributes)}): "
            f"{_format_capped_list(cmap.table_schema.attributes)}"
        )
        worst_attrs = sorted(
            summary["by_attribute"], key=lambda a: -a["missing"]
        )[:8]
        worst_attrs = [a for a in worst_attrs if a["missing"]]
        if worst_attrs:
            lines.append(
                "Top missing attributes: "
                + ", ".join(f"{a['attribute']}({a['missing']})" for a in worst_attrs)
            )
        if summary["worst_entities"]:
            lines.append(
                "Top missing entities: "
                + ", ".join(
                    f"{e['entity']}({e['missing']})"
                    for e in summary["worst_entities"][:8]
                )
            )
        lines.append(
            "Drill down with read_coverage(mode=\"cells\", ...) filters; "
            "do not pull the full cell list unfiltered."
        )
    else:
        lines.append("(schema not yet built)")

    nodes = getattr(getattr(state, "evidence_graph", None), "nodes", []) or []
    if nodes:
        lines.append(
            f"\n## Evidence\n{len(nodes)} nodes — read with "
            "read_evidence(entity=..., attribute=...) slices; never guess content from ids."
        )

    frontier = getattr(state, "frontier", None)
    tasks = getattr(frontier, "questions", []) or []
    if tasks:
        counts: dict[str, int] = {}
        for t in tasks:
            counts[t.status.value] = counts.get(t.status.value, 0) + 1
        with_report = sum(1 for t in tasks if t.resolution)
        lines.append(
            "\n## Frontier\n"
            + " | ".join(f"{k}: {v}" for k, v in sorted(counts.items()))
            + (
                f" — {with_report} task(s) carry agent reports "
                "(list_frontier + read_task_report)"
                if with_report
                else ""
            )
        )
        open_q = sorted(frontier.open_questions, key=lambda q: -q.priority)[:10]
        if open_q:
            lines.append("Open questions (top 10 by priority):")
            for q in open_q:
                lines.append(f"- [{q.id}] {q.question[:120]}")

    return "\n".join(lines)
def _snapshot_state_for_diff(state: Any) -> dict[str, Any]:
    """Capture the fields AgentReport needs to compute deltas against later.

    Minimal: coverage filled-cell keys + evidence node ids + draft length.
    These feed the search/writer report variants without dragging
    the whole SearchState.
    """
    filled_keys = {
        k for k, c in state.coverage_map.cells.items()
        if c.status.value == "filled"
    }
    evidence_ids = {n.id for n in state.evidence_graph.nodes}
    return {
        "filled_keys": filled_keys,
        "evidence_ids": evidence_ids,
        "draft_length": len(getattr(state, "draft", "") or ""),
    }
def _extract_explore_open_pages(messages: list) -> list[dict]:
    """Pull (url, markdown) for every page returned by ``open``
    during a explore run.

    Skips error tool-results and pages with no parseable URL header.
    """
    out: list[dict] = []
    for msg in messages:
        kind = (getattr(msg, "type", "") or msg.__class__.__name__).lower()
        if "tool" not in kind:
            continue
        name = (getattr(msg, "name", "") or "").lower()
        if name not in ("open", "browser_open", "explore_web"):
            continue
        content = getattr(msg, "content", "") or ""
        if isinstance(content, list):
            content = "\n".join(
                p.get("text", "") if isinstance(p, dict) else str(p)
                for p in content
            )
        content = str(content)
        if not content.strip() or content.lstrip().lower().startswith("error"):
            continue
        content = content.strip()
        # ``explore_web`` returns several independently replayable page
        # blocks in one tool result. Keep every block; treating the combined
        # output as one page would silently retain only its first hub URL.
        candidates = [content]
        if name == "explore_web":
            candidates = [
                block.split("<<<END_EXPLORE_PAGE>>>", 1)[0].strip()
                for block in content.split("<<<EXPLORE_PAGE>>>")[1:]
            ]
        for page_content in candidates:
            if len(page_content) < _EXPLORE_PAGE_MIN_CHARS:
                continue
            m = _EXPLORE_PAGE_URL_HDR.search(page_content)
            url = m.group(1).strip() if m else ""
            if not url.startswith("http"):
                continue
            if len(page_content) > _EXPLORE_PAGE_MAX_CHARS:
                page_content = page_content[:_EXPLORE_PAGE_MAX_CHARS]
            out.append({"source_url": url, "content": page_content})
    # Dedup by URL — keep the longest body per URL
    by_url: dict[str, dict] = {}
    for item in out:
        prev = by_url.get(item["source_url"])
        if prev is None or len(item["content"]) > len(prev["content"]):
            by_url[item["source_url"]] = item
    return list(by_url.values())
def _is_rate_limit_error(result: str) -> bool:
    low = (result or "").lower()
    return "429" in low or "rate limit" in low or "rate_limit" in low
def _recycle_failed_task(
    task_id: str, agent_id: str, status: str, result: str,
) -> None:
    """失败 agent 的绑定任务回收：翻回 PENDING 允许重派（attempts 已由
    set_running/next 累加），达到 MAX_TASK_ATTEMPTS 则 CANCELLED。
    429/限流类失败额外记 ``not_before`` 冷却，防止下一个 tick 立刻把
    空槽填回同一个限流里（派发风暴）。"""
    import time as _time

    from searchos.config.settings import settings as _settings
    from searchos.socm import MAX_TASK_ATTEMPTS
    from searchos.socm import FrontierTaskStatus as _Q

    outcome = {"v": ""}
    rate_limited = _is_rate_limit_error(result)

    def _apply(s: Any) -> Any:
        for q in s.frontier.questions:
            if q.id != task_id:
                continue
            if q.status not in (_Q.RUNNING, _Q.BLOCKED):
                break
            if q.attempts >= MAX_TASK_ATTEMPTS:
                q.status = _Q.CANCELLED
                q.resolution = f"max_attempts ({q.attempts}): {result[:300]}"
                outcome["v"] = "cancelled"
            else:
                q.status = _Q.PENDING
                q.priority = max(0.05, q.priority * 0.9)
                outcome["v"] = "requeued"
                if rate_limited:
                    q.not_before = (
                        _time.time() + _settings.rate_limit_recycle_cooldown_s
                    )
            q.assigned_agent_id = ""
            q.last_agent_report_excerpt = f"[{status}] {agent_id}: {result}"[:200]
            q.updated_at = _time.time()
            break
        return s

    try:
        _ctx.workspace.atomic_update_state(_apply)
    except Exception:  # noqa: BLE001 — 回收失败不应拖垮报告路径
        logger.warning("task recycle failed for %s", task_id, exc_info=True)
        return
    tlog = getattr(_ctx, "trajectory_logger", None)
    if outcome["v"] and tlog:
        event = {
            "type": "harness",
            "kind": "task_recycled",
            "task_id": task_id,
            "agent": agent_id,
            "agent_status": status,
            "outcome": outcome["v"],
        }
        if rate_limited and outcome["v"] == "requeued":
            from searchos.config.settings import settings as _settings
            event["rate_limit_cooldown_s"] = _settings.rate_limit_recycle_cooldown_s
        tlog._append_raw(event)
def _compute_agent_report(
    *,
    agent_id: str,
    thread_id: str,
    pre_snapshot: dict[str, Any],
    started_at: float,
    status: str,
    result: str,
    scope_entities: set[str] | None = None,
    last_ai_text: str = "",
    explore_pages: list[dict] | None = None,
) -> Any:
    """Diff post-state against pre_snapshot to build an AgentReport.

    Dispatches to the correct subclass by looking up the agent_type we
    stashed at spawn time. Downstream consumers read the ``kind`` field
    to branch.

    Respects sensor signals: if LoopSensor has written
    ``state.agent_status[thread_id] = "looped"`` the status argument is
    overridden to ``"looped"``.
    """
    import time

    from searchos.socm import (
        SearchReport, ExploreReport, WriterReport,
    )

    duration_s = time.time() - started_at
    agent_type = "search_agent"
    info = _ctx.agent_graphs.get(agent_id) if _ctx.agent_graphs else None
    if info is not None:
        agent_type = info.get("agent_type", "search_agent")

    if _ctx.workspace is None:
        # Degraded: return a minimal report of the right kind
        if agent_type == "writer_agent":
            return WriterReport(agent_id=agent_id, status=status,
                                result=result, duration_s=duration_s)
        if agent_type == "explore_agent":
            return ExploreReport(agent_id=agent_id, status=status,
                                result=result, duration_s=duration_s)
        return SearchReport(agent_id=agent_id, status=status,
                            result=result, duration_s=duration_s)

    state = _ctx.workspace.load_state()

    # Sensor signals are the final run outcome. Apply them before deciding
    # whether the bound Frontier task completed or needs to be recycled.
    sensor_status = state.agent_status.get(thread_id)
    if sensor_status == "looped":
        status = "looped"

    # Agent 没有正常完成时回收其绑定任务：留在 RUNNING 会让后续同 target 的
    # 重派被 _find_duplicate 判重而静默拒绝，目标永远得不到验证。
    if status in ("error", "failed", "looped"):
        bound_task_id = ""
        if info:
            bound_task_id = (
                info.get("assigned_task_id", "") or info.get("write_task_id", "")
            )
        if bound_task_id:
            _recycle_failed_task(bound_task_id, agent_id, status, result)
            state = _ctx.workspace.load_state()

    if agent_type == "explore_agent":
        # Stash the briefing as a synthetic page so create_schema can
        # replay extraction over it once tables are declared. Explore
        # has no extraction middleware attached, so this is the only
        # surface where the briefing exists in stashable form.
        if status == "completed" and len(last_ai_text.strip()) >= 50:
            synthetic_url = f"agent://{agent_id or 'explore_agent'}/final_summary"
            pages_to_stash = list(explore_pages or [])
            def _stash(s: Any) -> Any:
                s.pending_agent_summaries.append({
                    "agent_id": agent_id,
                    "source_url": synthetic_url,
                    "content": last_ai_text,
                })
                # Also stash the raw hub pages explore opened so extraction
                # sees the full source content, not just the briefing's
                # LLM-summarized subset (briefing typically captures only
                # ~65% of the entities visible on the page; the missing
                # 35% would otherwise be lost until search_agent re-fetches).
                for p in pages_to_stash:
                    s.pending_agent_summaries.append({
                        "agent_id": agent_id,
                        "source_url": p["source_url"],
                        "content": p["content"],
                    })
                return s
            try:
                _ctx.workspace.atomic_update_state(_stash)
                if _ctx.trajectory_logger:
                    _ctx.trajectory_logger._append_raw({
                        "type": "harness",
                        "kind": "pending_summary_stashed",
                        "agent": agent_id,
                        "chars": len(last_ai_text),
                        "explore_pages": len(pages_to_stash),
                    })
            except Exception:  # noqa: BLE001 — stash is best-effort
                logger.debug("explore pending-summary stash failed", exc_info=True)

        # Resolve the bound Frontier task so the Scheduler doesn't re-drain it.
        assigned_explore_task_id = info.get("assigned_task_id", "") if info else ""
        if assigned_explore_task_id and status == "completed":
            import time as _time
            def _resolve_explore(s: Any) -> Any:
                from searchos.socm import FrontierTaskStatus as _Q
                for q in s.frontier.questions:
                    if q.id == assigned_explore_task_id:
                        if q.status not in (_Q.COMPLETED, _Q.CANCELLED):
                            q.status = _Q.COMPLETED
                            q.resolution = (last_ai_text or result)[:500]
                            q.updated_at = _time.time()
                        break
                return s
            _ctx.workspace.atomic_update_state(_resolve_explore)

        return ExploreReport(
            agent_id=agent_id,
            status=(
                "completed" if (status == "completed" and last_ai_text.strip())
                else (status if status in ("error", "looped") else "failed")
            ),
            # ``result`` is the short stat summary (for UI); the verbatim
            # brief lives in ``last_message`` — don't duplicate it here.
            result=(result or "explore_agent exited without emitting a final brief"),
            duration_s=duration_s,
            last_message=last_ai_text,
        )

    if agent_type == "writer_agent":
        rendered = state.outline.rendered()
        draft_len_post = len(rendered)
        draft_len_pre = pre_snapshot.get("draft_length", 0)
        my_search = [
            q for q in state.frontier.questions
            if q.kind == "search" and q.created_by == "writer"
            and q.status.value in ("pending", "running")
        ]
        # Close the sensor-authored kind=write task when the writer
        # completes — plan §5.2.3 写入来源 4 lifecycle.
        write_task_id = info.get("write_task_id", "") if info else ""
        if write_task_id and status == "completed":
            import time as _time
            def _resolve_write(s: Any) -> Any:
                for q in s.frontier.questions:
                    if q.id == write_task_id:
                        from searchos.socm import FrontierTaskStatus as _Q
                        q.status = _Q.COMPLETED
                        q.resolution = (last_ai_text or result)
                        q.updated_at = _time.time()
                        break
                return s
            _ctx.workspace.atomic_update_state(_resolve_write)

        turn_count = info.get("continue_turn_count", 1) if info else 1
        draft_delta = max(0, draft_len_post - draft_len_pre)
        own_delta = f"draft +{draft_delta} chars (total {draft_len_post})"
        return WriterReport(
            agent_id=agent_id,
            status=("completed" if status == "completed" else status),
            result=f"{result}: {own_delta}" if result else own_delta,
            draft_length=draft_len_post,
            draft_delta=draft_delta,
            missing_evidence_count=len(my_search),
            continue_turn_count=turn_count,
            duration_s=duration_s,
            last_message=last_ai_text,
        )

    # Default: SearchReport.
    # If this search agent was bound to a FrontierTask (orchestrator
    # dispatch with target_cells, or broker-drained agent-emit), close
    # that task on completion so the queue reflects reality and the
    # writer's list_frontier sees it gone.
    assigned_search_task_id = info.get("assigned_task_id", "") if info else ""
    if assigned_search_task_id and status == "completed":
        import time as _time
        def _resolve_search(s: Any) -> Any:
            for q in s.frontier.questions:
                if q.id == assigned_search_task_id:
                    from searchos.socm import FrontierTaskStatus as _Q
                    if q.status not in (_Q.COMPLETED, _Q.CANCELLED):
                        q.status = _Q.COMPLETED
                        q.resolution = (last_ai_text or result)
                        q.updated_at = _time.time()
                    break
            return s
        _ctx.workspace.atomic_update_state(_resolve_search)
        # Refresh state for downstream metrics that read frontier.
        state = _ctx.workspace.load_state()

    # Auto-fill CoverageMap from new evidence for existing schema entities.
    # The extraction middleware only writes EvidenceNodes; we fill cells here.
    new_nodes = [
        n for n in state.evidence_graph.nodes
        if n.id not in pre_snapshot["evidence_ids"]
    ]
    if new_nodes:
        def _fill_from_new_evidence(s: Any) -> Any:
            s.coverage_map.fill_from_evidence(new_nodes)
            return s
        _ctx.workspace.atomic_update_state(_fill_from_new_evidence)
        state = _ctx.workspace.load_state()

    post_filled = {
        k for k, c in state.coverage_map.cells.items()
        if c.status.value == "filled"
    }
    newly_filled = post_filled - pre_snapshot["filled_keys"]

    # Per-agent attribution: each sub-agent's own ExtractionMiddleware records
    # the node ids it committed. The global pre/post diff (new_nodes) also counts
    # peers' evidence written concurrently, so intersect with that tally; fall
    # back to the scope filter, then the raw diff.
    new_nodes = [
        n for n in state.evidence_graph.nodes
        if n.id not in pre_snapshot["evidence_ids"]
    ]
    extraction_mw = info.get("extraction_mw") if info else None
    own_ids = getattr(extraction_mw, "_added_node_ids", None)
    if own_ids is not None:
        agent_new_nodes = [n for n in new_nodes if n.id in own_ids]
    elif scope_entities:
        agent_new_nodes = [n for n in new_nodes if n.entity in scope_entities]
    else:
        agent_new_nodes = new_nodes

    # Same attribution for filled cells (newly_filled also holds peer-filled).
    if own_ids is not None:
        attributing_entities: set[str] | None = {
            n.entity for n in agent_new_nodes if n.entity
        }
    else:
        attributing_entities = scope_entities
    if attributing_entities is not None:
        # Cell keys are "tid/entity.attr" — parse, never prefix-match on
        # the raw key (the tid prefix made entity prefixes match nothing,
        # so every scoped agent reported 0 cells filled).
        from searchos.socm import CoverageMap
        cells_filled = sorted(
            k for k in newly_filled
            if CoverageMap.parse_cell_key(k)[1] in attributing_entities
        )
    else:
        cells_filled = sorted(newly_filled)

    schema_entities = set(state.coverage_map.table_schema.entities)
    # Discovered rows = new entities among this agent's own nodes not yet in schema.
    discovery_nodes = agent_new_nodes if own_ids is not None else new_nodes
    discovered = sorted({
        n.entity for n in discovery_nodes
        if n.entity and n.entity not in schema_entities
    })
    dead_ends = list(state.agent_dead_ends.get(thread_id, []))

    # P1: evidence/scope signals so orchestrator can distinguish
    # "found data but scope mismatched" from "truly nothing".
    evidence_nodes_added = len(agent_new_nodes)
    partial_scope_count = sum(
        1 for n in agent_new_nodes if n.scope_match == "partial"
    )

    # Append this agent's OWN delta — never global coverage, which reads
    # as task progress and misleads the orchestrator. Kept compact: the
    # live-view tile shows ~46 chars.
    own_delta = (
        f"+{evidence_nodes_added} evidence"
        + (f" ({partial_scope_count} partial)" if partial_scope_count else "")
        + (f", {len(discovered)} new rows" if discovered else "")
    )
    result = f"{result}: {own_delta}" if result else own_delta

    return SearchReport(
        agent_id=agent_id,
        status=status, result=result,
        cells_filled=cells_filled,
        dead_ends=dead_ends,
        discovered_entities=discovered,
        evidence_nodes_added=evidence_nodes_added,
        partial_scope_count=partial_scope_count,
        duration_s=duration_s,
        # Strip re-pasted data tables — that data is already in evidence/cells;
        # only the agent's prose conclusions are useful to the orchestrator.
        last_message=_strip_markdown_tables(last_ai_text),
    )
def _next_agent_label(agent_type: str) -> str:
    """Per-type monotonic label, scoped to the current orchestrator context.

    First instance of a type gets the bare type name (``explore_agent``).
    Second and subsequent instances get a ``_N`` suffix where N starts at 2
    (``search_agent``, ``search_agent_2``, ``search_agent_3``).

    Counter lives in a ContextVar so concurrent harness runs (e.g. eval
    benchmark with N parallel queries) don't share IDs.
    """
    counters = _sub_agent_counter_var.get()
    if counters is None:
        counters = {}
        _sub_agent_counter_var.set(counters)
    n = counters.get(agent_type, 0) + 1
    counters[agent_type] = n
    return agent_type if n == 1 else f"{agent_type}_{n}"
async def _spawn_sub_agent(
    agent_type: str,
    task: str,
    skill_names: list[str],
    bind_task_id: str = "",
    *,
    target_table: str = "",
    search_budget: int | None = None,
) -> str:
    """Build sub-agent graph, register it, create an asyncio.Task wrapping
    its run — return ``agent_id`` immediately.

    ``bind_task_id`` (scheduler only): when set, binds this spawn to an
    existing FrontierTask being picked off the queue.

    ``target_table``: which CoverageMap table this agent's evidence
    should fill. Stored on agent_graphs and re-bound to the
    ``_current_table_var`` ContextVar inside the agent's coroutine
    so the extraction middleware routes findings correctly.
    """
    import time

    from searchos.agents.runtime import create_search_agent_graph
    from searchos.harness.middleware.sensor.harness import (
        BudgetState,
        HarnessMiddleware,
    )

    assert _ctx.workspace is not None
    assert _ctx.model is not None

    # Plan §6.4 单 agent strategy skill 注入上限 K — clamp here so no
    # caller can blow up the system prompt by passing 20 skills.
    if skill_names and len(skill_names) > MAX_SKILLS_PER_DISPATCH:
        logger.warning(
            "Spawn %s requested %d skills > K=%d; truncating to first %d "
            "(plan §6.4).",
            agent_type, len(skill_names), MAX_SKILLS_PER_DISPATCH,
            MAX_SKILLS_PER_DISPATCH,
        )
        skill_names = skill_names[:MAX_SKILLS_PER_DISPATCH]

    if agent_type not in _KNOWN_AGENT_TYPES:
        logger.info(
            "Mapping unknown agent_type %r → search_agent", agent_type,
        )
        agent_type = "search_agent"

    agent_label = _next_agent_label(agent_type)
    assigned_task_id = ""
    # Bind for every type (scheduler always passes bind_task_id; without
    # this, an OPEN task gets re-drained while its agent is still running).
    if bind_task_id:
        assigned_task_id = bind_task_id
        def _bind(s: Any) -> Any:
            from searchos.socm import FrontierTaskStatus as _S
            for q in s.frontier.questions:
                if q.id == bind_task_id:
                    q.assigned_agent_id = agent_label
                    if q.status == _S.PENDING:
                        q.status = _S.RUNNING
                        q.attempts += 1
                    break
            return s
        _ctx.workspace.atomic_update_state(_bind)

    # Per-role assembly (paper §Agent Roles): each role package owns its
    # toolset. ``agent_type`` is already normalized to a known role above, so
    # search injects typed skill_* tools for the dispatched skills, explore
    # gets browser only, writer gets the drafting tools.
    role = _ROLE_REGISTRY[agent_type]
    is_search_type = agent_type == "search_agent"
    tools = list(role.get_tools(skill_names))

    # Build system prompt: agent.md first (persona), then SOCM context
    state = _ctx.workspace.load_state()
    prompt_parts: list[str] = []

    from pathlib import Path
    from searchos.config.settings import settings as _prompt_settings

    agent_md_name = (
        "agent_legacy.md"
        if agent_type == "explore_agent" and not _prompt_settings.enable_explore_batch
        else "agent.md"
    )
    agent_md_path = Path(role.__file__).parent / agent_md_name
    if agent_md_path.exists():
        from searchos.agents.toolset_render import render_toolset
        persona = agent_md_path.read_text(encoding="utf-8")
        rendered = render_toolset(tools, header="## Available Tools")
        persona = persona.replace("{toolset}", rendered)
        prompt_parts.append(persona)

    # After the persona and date-only: dynamic content at the top of the
    # system prompt forks the prompt-cache prefix on every dispatch, so
    # same-type sub-agents could never share the cached persona/toolset.
    from datetime import datetime as _dt

    from searchos.agents.temporal import render_temporal_grounding
    prompt_parts.append(render_temporal_grounding(
        _dt.now().strftime("%Y-%m-%d"),
        agent_type,
    ))

    # Explore-specific budget self-awareness. The harness hard-blocks
    # open() once max_opens is hit, but explore has no extraction
    # middleware to write coverage/evidence — its only output is the
    # final assistant briefing. Without an explicit wind-down rule it
    # spends every open trying to read more pages, then runs out of
    # budget before emitting the briefing. Pull the cap from
    # AGENT_BUDGET_OVERRIDES so this stays in sync with settings.
    if agent_type == "explore_agent":
        from searchos.config.settings import settings as _s

        _ov = _agent_budget_override("explore_agent")
        _max_s = _ov.get("max_searches", _s.max_searches_per_sub_agent)
        _max_o = _ov.get("max_opens", 0)
        _max_f = _ov.get("max_finds", _s.max_finds_per_sub_agent)
        if _s.enable_explore_batch:
            prompt_parts.append(
                "# Runtime coverage contract\n\n"
                f"Complete at least **{_s.explore_min_waves}** and at most "
                f"**{_s.explore_max_waves}** `explore_web` coverage waves. "
                "A credible hub alone never satisfies the completion rule.\n\n"
                f"The hard resource caps are **{_max_s} underlying searches** and "
                f"**{_max_o} underlying page opens**. One batch call is charged "
                "by the number of queries and `queries × open_top_k`, not as one "
                "unit. If a proposed batch does not fit, shrink it to the "
                "remaining capacity.\n\n"
                "After the minimum waves, stop only when the saturation checklist "
                "in your role prompt passes or the resource/wave cap is reached. "
                "Always reserve one final model turn to emit the complete briefing "
                "as a plain assistant message with no tool call.\n\n"
                "Coverage and evidence nodes will stay at zero throughout your "
                "run — that is by design (no extraction middleware is attached "
                "to explore). Your value is the briefing text, nothing else."
            )
        else:
            prompt_parts.append(
                "# Legacy budget discipline\n\n"
                f"You have a hard cap of **{_max_s} `search()` calls**, "
                f"**{_max_o} `open()` calls**, and **{_max_f} `find()` calls**. "
                f"After your **{max(1, _max_o - 1)}-th** `open()`, do one final "
                "`find()` if needed and immediately emit the final briefing as "
                "a plain assistant message with no tool call."
            )

    scope_entities = _detect_scope_entities(
        task, state.coverage_map.table_schema.entities,
    )

    if agent_type != "explore_agent":
        socm_block = _build_sub_agent_context(state, agent_type=agent_type)
        if socm_block:
            prompt_parts.append(socm_block)

    missing_skills: list[str] = []
    if skill_names and _ctx.skill_registry:
        skill_parts: list[str] = []
        for sname in skill_names:
            skill = _ctx.skill_registry.get(sname)
            if not skill:
                logger.warning("Skill '%s' not found in registry — Orchestrator hallucinated a name", sname)
                missing_skills.append(sname)
                continue
            if skill.body:
                skill_parts.append(f"### {skill.meta.name}\n{skill.body}")
                # Anti-patterns live in a sibling ``anti_patterns.md``
                # and are loaded separately into the Skill object. Inject
                # only the one-line index by default; sub-agents pull
                # details on demand via ``load_anti_patterns``. This
                # keeps the injected skill footprint small (~300 tokens
                # vs ~3-6k for a fully-inlined AP list).
                ap_index = getattr(skill, "anti_patterns_index", "") or ""
                if ap_index:
                    skill_parts.append(
                        f"**{skill.meta.name} — known failure modes** "
                        f"(call `load_anti_patterns(\"{sname}\")` for "
                        "details if any of these look relevant):\n"
                        + ap_index
                    )
                if skill.meta.has_executor:
                    # Access skills are exposed as typed tools named
                    # ``skill_<name>`` (auto-registered via get_skill_tools
                    # from manifest.yaml's params_schema).
                    skill_parts.append(
                        f"**Note**: call `skill_{sname}(...)` directly — "
                        "the tool is typed (see its args schema)."
                    )
        if skill_parts:
            prompt_parts.append("## Loaded Skills\n" + "\n\n".join(skill_parts))

    # Plan §5.5 消费方 — Control: inject anti-patterns so the agent
    # avoids paths that have already failed in this session. Scoped by
    # target_cell when the spawn has scope entities, plus any global
    # entries.
    # Failure-memory block (post-mortem distilled advice) renders ABOVE
    # the anti-pattern block — strategy guidance precedes the raw bullet
    # list of failed queries/sources/skills.
    failure_memory_block = _build_failure_memory_prompt(state, scope_entities=scope_entities, task=task)
    if failure_memory_block:
        prompt_parts.append(failure_memory_block)
    ap_block = _build_antipattern_prompt(state, scope_entities=scope_entities)
    if ap_block:
        prompt_parts.append(ap_block)

    system_prompt = "\n\n".join(prompt_parts)

    # Create middleware for trajectory logging + loop detection
    middleware_stack = []
    if _ctx.trajectory_logger:
        from searchos.config.settings import settings
        from searchos.harness.middleware.sensor.loop_sensor import LoopSensorImpl

        override = _agent_budget_override(agent_type)
        # Precedence: per-task > agent-type override > settings default.
        if search_budget is not None:
            max_searches = max(
                1, min(int(search_budget),
                       settings.max_searches_per_sub_agent_ceiling),
            )
        else:
            max_searches = override.get("max_searches", settings.max_searches_per_sub_agent)
        max_opens = override.get("max_opens", 0)
        max_finds = override.get("max_finds", settings.max_finds_per_sub_agent)

        sensors: list[Any] = [LoopSensorImpl(
            workspace=_ctx.workspace,
            thread_id=agent_label,
        )]

        worker_mw = HarnessMiddleware(
            sensors=sensors,
            trajectory_logger=_ctx.trajectory_logger,
            budget=BudgetState(
                max_queries=max_searches,
                max_opens=max_opens,
                max_finds=max_finds,
            ),
            workspace=_ctx.workspace,
            worker_name=agent_label,
        )

        from searchos.harness.middleware import build_layered_stack
        from searchos.harness.middleware.context import ControlMiddleware
        from searchos.harness.middleware.extraction import ExtractionMiddleware

        control_mw: list = [ControlMiddleware(
            judge_model=_ctx.judge_model,
            workspace=_ctx.workspace,
            layer1_max_tokens=settings.layered_context_layer1_max_tokens,
            layer2_max_tokens=settings.layered_context_layer2_max_tokens,
            layer3_max_tokens=settings.layered_context_layer3_max_tokens,
            trim_max_tokens_fraction=0.85,
        )]
        sensor_mw: list = [worker_mw]
        extraction_mw: list = []
        _extraction_instance = None
        if is_search_type and _ctx.extraction_model is not None:
            _extraction_instance = ExtractionMiddleware(
                judge_model=_ctx.extraction_model,
                alias_resolver_model=_ctx.alias_resolver_model,
                workspace=_ctx.workspace,
                trajectory_logger=_ctx.trajectory_logger,
            )
            extraction_mw.append(_extraction_instance)
            # Hand the same extraction instance to HarnessMiddleware so it can
            # ``await_pending_flushes`` before rendering each SOCM update — without
            # this, the per-turn snapshot may miss evidence that's still in the
            # background flush queue from the prior tool call.
            worker_mw._extraction_mw = _extraction_instance
        middleware_stack.extend(build_layered_stack(
            control=control_mw, sensor=sensor_mw, extraction=extraction_mw,
        ))

    from searchos.tools.simple_browser import reset_browser_for_sub_agent
    reset_browser_for_sub_agent()

    from deepagents.backends import FilesystemBackend
    agent_backend = FilesystemBackend(
        root_dir=str(_ctx.workspace.path / "agent_logs"),
        virtual_mode=False,
    )

    # Create and run graph — sub-agents use the sub_agent role, separate
    # from the orchestrator's main loop. Falls back to orchestrator model
    # if sub_agent role wasn't bound (legacy callers).
    logger.info("Sub-agent '%s' tools: %s", agent_type, [getattr(t, "name", str(t)) for t in tools])
    sub_agent_model = _ctx.sub_agent_model or _ctx.model
    graph = create_search_agent_graph(
        model=sub_agent_model,
        tools=tools,
        system_prompt=system_prompt,
        middleware=middleware_stack,
        backend=agent_backend,
        name=agent_type,
    )

    thread_id = agent_label

    from searchos.tools.search_state import (
        set_current_agent, set_current_task, set_current_table,
    )
    set_current_agent(thread_id)
    set_current_task(task)
    set_current_table("")

    if _ctx.conversation_logger:
        _ctx.conversation_logger.register_sub_agent(
            agent_name=thread_id,
            parent="orchestrator",
            task=task,
            system_prompt="\n\n".join(prompt_parts),
            agent_type=agent_type,
        )

    if _ctx.trajectory_logger:
        _ctx.trajectory_logger._append_raw({
            "type": "dispatch",
            "agent": agent_label,
            "task": task,
            "skills": skill_names,
        })

    wrapped_task = task

    # Pre-snapshot for AgentReport delta computation at completion time.
    pre_snapshot = _snapshot_state_for_diff(_ctx.workspace.load_state())

    _ctx.agent_graphs[agent_label] = {
        "graph": graph,
        "thread_id": thread_id,
        "agent_type": agent_type,
        "task": task,
        "wrapped_task": wrapped_task,
        "skill_names": list(skill_names),
        "missing_skills": missing_skills,
        "pre_snapshot": pre_snapshot,
        "scope_entities": scope_entities,  # used by _compute_agent_report to
                                       # filter out peer-filled cells
        "started_at": time.time(),
        "continue_turn_count": 1,
        "assigned_task_id": assigned_task_id,
        "target_table": target_table,
        "extraction_mw": _extraction_instance,
    }

    t = asyncio.create_task(
        _collect_sub_agent_result(agent_label),
        name=f"sub-agent:{agent_label}",
    )
    _ctx.task_pool[agent_label] = t

    return agent_label
async def _collect_sub_agent_result(agent_id: str) -> Any:
    """Coroutine body of a spawned sub-agent Task.

    Runs ``graph.astream`` to completion, streaming conversation messages
    to the logger, then computes an ``AgentReport`` from the pre/post
    state diff and registers it in ``_ctx.completed``. Returns the
    ``AgentReport`` so ``await pool[agent_id]`` yields structured data.
    """
    info = _ctx.agent_graphs.get(agent_id)
    if info is None:
        from searchos.socm import AgentReport
        return AgentReport(
            agent_id=agent_id, status="error",
            result=f"agent {agent_id} not registered — internal bug",
        )

    graph = info["graph"]
    thread_id = info["thread_id"]
    wrapped_task = info["wrapped_task"]
    task_desc = info["task"]
    pre_snapshot = info["pre_snapshot"]
    missing_skills = info["missing_skills"]
    started_at = info["started_at"]
    scope_entities = info.get("scope_entities")
    target_table = info.get("target_table", "") or ""
    agent_type = info.get("agent_type", "search_agent")

    from searchos.tools.search_state import (
        set_current_agent, set_current_task, set_current_table,
    )
    set_current_agent(thread_id)
    set_current_task(task_desc)
    set_current_table(target_table)


    try:
        prev_msg_count = 0
        latest_messages: list[Any] = []
        async for event in graph.astream(
            {"messages": [{"role": "user", "content": wrapped_task}]},
            config={"configurable": {"thread_id": thread_id}},
            stream_mode="values",
        ):
            if "messages" in event:
                latest_messages = event["messages"]

            if _ctx.conversation_logger and "messages" in event:
                from searchos.harness.telemetry.conversation import (
                    langchain_msg_to_conversation_msgs,
                )
                msgs = event["messages"]
                for msg in msgs[prev_msg_count:]:
                    for conv_msg in langchain_msg_to_conversation_msgs(msg):
                        conv_msg.agent_name = thread_id
                        conv_msg.parent_agent = "orchestrator"
                        _ctx.conversation_logger.log(conv_msg)
                prev_msg_count = len(msgs)

        # Drain extraction before reading state for the report — an agent
        # interrupted mid-tool-call (recursion/budget) has no final turn, so
        # its residual buffer / background flushes are otherwise uncounted and
        # the report undercounts cells → orchestrator re-dispatches filled work.
        ext = info.get("extraction_mw") if info else None
        if ext is not None:
            from searchos.config.settings import settings as _s
            try:
                await ext.finalize(timeout=_s.extraction_finalize_timeout_s)
            except Exception:  # noqa: BLE001
                logger.warning("extraction finalize failed for %s", agent_id, exc_info=True)

        # Human-readable result. Deliberately NO global stats here: global
        # coverage/frontier numbers in a per-agent result read as task
        # progress and mislead the orchestrator (the SOCM block already
        # carries global state every turn). _compute_agent_report appends
        # this agent's OWN delta for search reports.
        summary = "Completed"
        if missing_skills:
            available = (
                [s.meta.name for s in _ctx.skill_registry.list_all()][:10]
                if _ctx.skill_registry else []
            )
            summary = (
                f"[WARN: skills {missing_skills} not found in registry. "
                f"Available: {available}] {summary}"
            )

        # Last AIMessage with no tool_calls is the agent's end-of-run
        # briefing (plan §一 总则 3). The orchestrator reads it to decide
        # what to do next; explore parses it into a ExploreReport.
        #
        # Qwen3 / GLM-5 / DeepSeek-R1 emit thinking into a separate
        # `reasoning_content` field and leave `content` empty. Fall back to
        # reasoning_content so the briefing is never silently lost.
        last_ai_text = ""
        for msg in reversed(latest_messages):
            if getattr(msg, "tool_calls", None):
                continue
            kind = getattr(msg, "type", "") or msg.__class__.__name__.lower()
            if "ai" in kind.lower():
                content = getattr(msg, "content", "") or ""
                if isinstance(content, list):
                    content = " ".join(
                        p.get("text", "") if isinstance(p, dict) else str(p)
                        for p in content
                    )
                text = str(content).strip()
                if not text:
                    extras = getattr(msg, "additional_kwargs", None) or {}
                    if isinstance(extras, dict):
                        text = str(extras.get("reasoning_content", "") or "").strip()
                last_ai_text = text
                break

        # For explore_agent only, pluck out the raw hub pages it opened so
        # extraction can replay over them after schema is committed.
        explore_pages = (
            _extract_explore_open_pages(latest_messages)
            if agent_type == "explore_agent" else None
        )

        report = _compute_agent_report(
            agent_id=agent_id, thread_id=thread_id,
            pre_snapshot=pre_snapshot, started_at=started_at,
            status="completed", result=summary,
            scope_entities=scope_entities,
            last_ai_text=last_ai_text,
            explore_pages=explore_pages,
        )
        # Logged AFTER report computation so the live view's agent tile
        # shows this agent's own delta (cells/evidence/draft), not a bare
        # "Completed".
        if _ctx.trajectory_logger:
            _ctx.trajectory_logger._append_raw({
                "type": "agent_complete",
                "agent": agent_id,
                "task": task_desc,
                "summary": report.result,
            })

        # --- Post-mortem failure-memory trigger ---
        # Fire when:
        #   - status in {"error","budget_exhausted"} — the agent
        #     crashed (RPC / runtime exception) or was hard-stopped
        #     by the harness for blowing its search/open budget.
        #     Set in _compute_agent_report.
        #   - dead_ends non-empty — LoopSensor recorded specific stuck
        #     queries on agent_dead_ends[thread_id]. Per-thread map,
        #     so this is concurrency-safe.
        # Deliberately NOT triggered on status=="looped" (overlaps with
        # dead_ends but with a wider, noisier judgement) or on
        # cells_filled==0 (concurrency-polluted: a sibling's writes
        # also count, and many legitimate sub-agent missions are
        # evidence-gathering and do not emit cells themselves).
        # Gated by a per-session counter so a string of bad runs
        # cannot burn an unbounded number of opus calls. fire-and-
        # forget; the task writes a FailureMemory into
        # state.strategy_log.failure_memories which the NEXT sub-agent
        # picks up via _build_failure_memory_prompt.
        from searchos.config.settings import settings
        from searchos.socm import SearchReport
        _pm_state = _ctx.workspace.load_state() if _ctx.workspace else None
        _pm_sensor = (
            _pm_state.agent_status.get(thread_id) if _pm_state else None
        )
        if (
            settings.enable_failure_memory
            and isinstance(report, SearchReport)
            and _ctx.post_mortem_model is not None
            and (
                report.status in ("error", "budget_exhausted")
                or _pm_sensor == "budget_exhausted"
                or len(report.dead_ends) >= 1
            )
        ):
            count_box = _post_mortem_count_var.get()
            if (
                count_box is not None
                and count_box[0] < settings.max_post_mortems_per_session
            ):
                count_box[0] += 1
                try:
                    pm_task = asyncio.create_task(
                        _run_post_mortem(thread_id, agent_id, report)
                    )
                    pm_tasks = _post_mortem_tasks_var.get()
                    if pm_tasks is not None:
                        pm_tasks.append(pm_task)
                except RuntimeError:
                    # No running loop — degraded path (sync caller).
                    # Skip silently; failure memories are best-effort.
                    pass

        _ctx.completed[agent_id] = report
        return report

    except Exception as e:
        import traceback

        tb = traceback.format_exc()
        logger.error(
            "Sub agent %s failed: %s(%s)",
            agent_id, type(e).__name__, str(e).strip(), exc_info=True,
        )
        # Some exceptions stringify to "" — fall back to class name.
        err_msg = str(e).strip() or type(e).__name__
        if _ctx.trajectory_logger:
            _ctx.trajectory_logger._append_raw({
                "type": "agent_error",
                "agent": agent_id,
                "error": err_msg[:500],
                "error_type": type(e).__name__,
                "traceback": tb[-2000:],
            })
        ext = info.get("extraction_mw") if info else None
        if ext is not None:
            from searchos.config.settings import settings as _s
            try:
                await ext.finalize(timeout=_s.extraction_finalize_timeout_s)
            except Exception:  # noqa: BLE001
                logger.warning("extraction finalize (error path) failed for %s", agent_id, exc_info=True)
        report = _compute_agent_report(
            agent_id=agent_id, thread_id=thread_id,
            pre_snapshot=pre_snapshot, started_at=started_at,
            status="error", result=f"Error: {err_msg}",
            scope_entities=scope_entities,
        )
        _ctx.completed[agent_id] = report
        return report


def _task_redundancy_reason(
    state: Any, *, target_cells: list[str], table_id: str,
) -> str:
    """Non-empty reason when a search task's explicit target_cells are
    all filled. Returns "" otherwise — tasks without target_cells are
    never rejected (they may be open-set enumeration).
    """
    if not target_cells:
        return ""
    cmap = state.coverage_map
    tid = table_id or (cmap.primary_table_id if cmap.tables else "")
    keys = [c if "/" in c else (f"{tid}/{c}" if tid else c) for c in target_cells]
    cells = [cmap.cells.get(k) for k in keys]
    if cells and all(
        c is not None and c.status.value == "filled" and not c.has_conflict
        for c in cells
    ):
        return f"all {len(cells)} target_cells already filled"
    return ""
