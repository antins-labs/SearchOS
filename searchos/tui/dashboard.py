"""SearchOS live dashboard — run progress as stacked rich panels.

SearchOS dashboard with four sections (Agents /
Progress+Coverage / Frontier / Events) and the same symbol/colour vocabulary,
but driven by an in-process trajectory callback (``feed``) instead of tailing
the file, and rendered to an ANSI string for embedding in the prompt_toolkit
fullscreen app.
"""

from __future__ import annotations

import json
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rich.columns import Columns
from rich.console import Group
from rich.markdown import Markdown
from rich.panel import Panel
from rich.progress_bar import ProgressBar
from rich.table import Table
from rich.text import Text

MAX_RECENT_EVENTS = 8
MAX_AGENTS = 12

FRONTIER_ICON = {
    "running":   ("▶", "bold cyan"),
    "pending":   ("○", "white"),
    "blocked":   ("⊘", "yellow"),
    "completed": ("✓", "green"),
    "cancelled": ("✗", "red dim"),
}
FRONTIER_ORDER = {"running": 0, "blocked": 1, "pending": 2, "completed": 3, "cancelled": 4}
FRONTIER_MAX_ROWS = 10

# Orchestrator tool-call colour by category (Claude-Code-style ⏺ marker).
# ----- Palette ------------------------------------------------------------
# One cohesive scheme: cyan is the SearchOS identity; everything else is a
# muted neutral or a semantic accent. Imported by app.py so markers/prompt
# stay in sync with the stream.
ACCENT      = "#22d3ee"   # primary cyan (logo, prompt, separators)
ACCENT_SOFT = "#5eead4"   # teal — reasoning marker, highlights
THINK       = "#7d8590"   # muted slate — reasoning text
MUTED       = "#9aa4af"   # secondary text (tool args, result text)
FAINT       = "#6e7681"   # faint markers / punctuation
WARN        = "#f4bf4f"   # amber — interrupt / blocked
DANGER      = "#f87171"   # red — errors

# Orchestrator tool-call colour by category (Claude-Code-style ⏺ marker).
C_SEARCH   = "#38bdf8"   # sky — search / fetch
C_SCHEMA   = "#c084fc"   # violet — schema ops
C_DISPATCH = "#f4bf4f"   # amber — dispatch / enqueue
C_AGENTS   = "#4ade80"   # green — agent polling
DEFAULT_TOOL_COLOR = "#34d399"   # emerald — generic tool

ORCH_TOOL_COLOR = {
    "search": C_SEARCH, "web_search": C_SEARCH,
    "tavily_search": C_SEARCH, "serper_search": C_SEARCH, "open": C_SEARCH,
    "create_schema": C_SCHEMA, "update_schema": C_SCHEMA,
    "enqueue_tasks": C_DISPATCH,
    "check_agents": C_AGENTS, "continue_agent": C_AGENTS,
}


def _fmt_args(args: Any) -> str:
    """Compact one-line ``key: value`` rendering of tool args."""
    if not isinstance(args, dict) or not args:
        return ""
    parts = []
    for k, v in args.items():
        s = str(v).replace("\n", " ").strip()
        if len(s) > 60:
            s = s[:59] + "…"
        parts.append(f"{k}: {s}")
    out = ", ".join(parts)
    return out[:140] + ("…" if len(out) > 140 else "")


# ----- Orchestrator stream line builders ----------------------------------
# The Textual app appends these straight into an append-only RichLog as the
# events arrive (Claude-Code-style timeline). They live at module scope so the
# rendering vocabulary (markers, colours) stays in one place.

def stream_reasoning(text: str, verbose: bool = False) -> Text:
    limit = 4000 if verbose else 800
    line = Text()
    line.append("✻ ", style=ACCENT_SOFT)
    line.append(text[:limit], style=f"{THINK} italic")
    return line


def stream_content(text: str, verbose: bool = False) -> Markdown:  # noqa: ARG001
    # Render the orchestrator's prose as Markdown (headings, tables, lists,
    # code blocks) instead of raw text. Never truncated — the final answer
    # streams in as the last content block and must be shown in full.
    return Markdown(text)


def stream_tool_call(tool: str, args: Any, verbose: bool = False) -> Text:
    """The ``⏺ tool(args)`` line, emitted the instant the call is made.

    Compact: one line, ``tool(key: val, …)`` truncated. Verbose: the tool
    name, then every arg on its own indented line with the full value, so the
    detail toggle can show what the orchestrator actually passed.
    """
    color = ORCH_TOOL_COLOR.get(tool or "", DEFAULT_TOOL_COLOR)
    line = Text()
    line.append("⏺ ", style=f"bold {color}")
    line.append(tool or "?", style=f"bold {color}")
    if verbose:
        if isinstance(args, dict) and args:
            for k, v in args.items():
                val = str(v).replace("\r", "")
                line.append(f"\n    {k}: ", style=MUTED)
                line.append(val, style=FAINT)
        return line
    args_str = _fmt_args(args)
    if args_str:
        line.append("(", style=FAINT)
        line.append(args_str, style=MUTED)
        line.append(")", style=FAINT)
    return line


def stream_tool_result(result: str, verbose: bool = False) -> Text:
    """The indented ``⎿ result`` line, appended when the result returns.

    Compact: single line, truncated to 200 chars. Verbose: the full result
    payload (as sent by the harness, up to its own 500-char cap), newlines
    preserved and continuation lines indented under the ``⎿`` marker.
    """
    line = Text()
    line.append("  ⎿ ", style=FAINT)
    if verbose:
        r = (result or "").rstrip()
        line.append(r.replace("\n", "\n     "), style=MUTED)
        return line
    r = (result or "").replace("\n", " ").strip()
    line.append(r[:200] + ("…" if len(r) > 200 else ""), style=MUTED)
    return line


@dataclass
class AgentRun:
    agent: str
    skills: list[str] = field(default_factory=list)
    step_count: int = 0
    last_action: str = ""
    status: str = "running"  # running | completed
    summary: str = ""


class LiveDashboard:
    """Holds run state fed by trajectory events; renders to an ANSI string."""

    def __init__(self, query: str = "", state_path: str | Path | None = None) -> None:
        self._query = query
        self._state_path: Path | None = Path(state_path) if state_path else None

        self._complexity = "?"
        self._orchestrator_actions: deque[str] = deque(maxlen=6)
        self._agents: list[AgentRun] = []
        self._coverage = 0.0
        self._evidence_backed = 0.0
        self._evidence_count = 0
        self._search_count = 0
        self._recent_events: deque[str] = deque(maxlen=MAX_RECENT_EVENTS)
        self._code_events: deque[str] = deque(maxlen=3)
        self._tables: list[dict] = []
        self._relations: list[dict] = []
        self._cells: dict[str, dict[str, Any]] = {}
        self._frontier_tasks: list[dict[str, Any]] = []
        # The orchestrator timeline (reasoning / content / tool calls) is no
        # longer buffered here — the Textual app appends each item straight to
        # an append-only RichLog widget as the events arrive (see app.py /
        # the module-level ``stream_*`` helpers below).

    # ----- Inputs -----

    def set_state_path(self, path: str | Path) -> None:
        self._state_path = Path(path)

    def feed(self, event: dict) -> None:
        """Apply one trajectory event (the in-process on_event callback)."""
        try:
            self._apply(event)
        except Exception:
            pass

    def poll_state(self) -> None:
        """Read canonical coverage + frontier from search_state.json.

        Event deltas can miss updates (extraction is batched); polling the
        state file keeps coverage/frontier honest. O(1), safe to call often.
        """
        if not self._state_path or not self._state_path.exists():
            return
        try:
            state = json.loads(self._state_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return
        cov_map = state.get("coverage_map", {})
        tables = cov_map.get("tables", {}) or {}
        self._tables = [
            {
                "table_id": tid,
                "table_label": t.get("table_label", "") or "",
                "entities": t.get("entities", []) or [],
                "attributes": t.get("attributes", []) or [],
                "primary_key": t.get("primary_key", []) or t.get("key_columns", []) or [],
                "row_label": t.get("row_label", "") or "",
            }
            for tid, t in tables.items()
        ]
        self._relations = cov_map.get("relations", []) or []
        self._cells = cov_map.get("cells", {}) or {}
        if self._cells:
            filled = sum(
                1 for c in self._cells.values()
                if c.get("status") in ("filled", "resolved")
            )
            self._coverage = filled / len(self._cells)
            backed = sum(
                1 for c in self._cells.values()
                if c.get("supporting_evidence_ids")
            )
            self._evidence_backed = backed / len(self._cells)
        nodes = state.get("evidence_graph", {}).get("nodes", [])
        if nodes:
            self._evidence_count = len(nodes)
        self._frontier_tasks = [
            {
                "id": q.get("id", ""),
                "question": q.get("question", "") or q.get("task_prompt", ""),
                "status": q.get("status") or "pending",
                "agent": q.get("assigned_agent_id", "") or "",
                "blocked_by": q.get("blocked_by", []) or [],
                "priority": q.get("priority", 0.5),
            }
            for q in (state.get("frontier", {}).get("questions", []) or [])
        ]

    # ----- Event application (ported verbatim) -----

    def _apply(self, event: dict) -> None:
        etype = event.get("type")
        if etype == "task_start":
            self._complexity = event.get("complexity", "?")
        elif etype == "dispatch":
            agent = AgentRun(
                agent=event.get("agent", "unknown"),
                skills=event.get("skills", []) or [],
            )
            self._agents.append(agent)
            self._agents = self._agents[-MAX_AGENTS:]
        elif etype == "step":
            agent_name = event.get("agent")
            if not agent_name or agent_name == "orchestrator":
                return
            current = next((a for a in self._agents if a.agent == agent_name), None)
            if current is None:
                return
            current.step_count = event.get("step_index", current.step_count) + 1
            action = event.get("action", {})
            name = action.get("name", "?")
            args_preview = str(action.get("args", ""))[:60]
            current.last_action = f"{name}({args_preview})"
            if name == "execute_python":
                code_preview = str(action.get("args", ""))[:80].replace("\n", " ")
                self._code_events.append(f"[{current.agent}] {code_preview}")
                self._recent_events.append(f"[code] {name} in {current.agent}")
            delta = event.get("state_delta", {})
            cov = delta.get("coverage_after")
            if cov is not None:
                self._coverage = cov
            self._evidence_count += int(delta.get("new_evidence_count", 0))
            if name in {"search", "open", "find",
                        "web_search", "tavily_search", "serper_search"}:
                self._search_count += 1
        elif etype == "agent_complete":
            agent_name = event.get("agent", "")
            for a in self._agents:
                if a.agent == agent_name and a.status == "running":
                    a.status = "completed"
                    s = event.get("summary", "")
                    for prefix in ("Completed: ", "Continued: "):
                        if s.startswith(prefix):
                            s = s[len(prefix):]
                            break
                    a.summary = s[:60]
                    break
        elif etype == "harness":
            kind = event.get("kind", "")
            detail = ""
            if kind == "skill_injection":
                detail = f"skills={','.join(event.get('skills', []))}"
            elif kind == "budget_warning":
                detail = f"{event.get('consumed')}/{event.get('max')}"
            elif kind == "force_stop":
                detail = event.get("reason", "")
            elif kind == "evaluator":
                detail = f"verdict={event.get('verdict')}"
            self._recent_events.append(f"[harness:{kind}] {detail}")
        elif etype == "skill_evolution":
            phase = event.get("phase", "")
            decision = event.get("decision", "")
            self._recent_events.append(f"[skill_evo:{phase}] {decision}")
        elif etype == "orchestrator_tool":
            # The visual stream row is appended by the app; here we only fold
            # the call into the panel-side summary (actions strip + counters).
            tool = event.get("tool", "?")
            args = event.get("args", {})
            result = event.get("result_preview", "")
            if tool == "create_schema":
                self._orchestrator_actions.append(f"create_schema: {result[:80]}")
            elif tool == "search":
                q = args.get("query", "")[:50]
                self._orchestrator_actions.append(f"search: {q}")
                self._search_count += 1
            else:
                self._orchestrator_actions.append(tool)
            self._recent_events.append(f"[orchestrator] {tool}")
        elif etype == "task_complete":
            self._coverage = event.get("coverage", self._coverage)
            self._evidence_backed = event.get(
                "evidence_backed_coverage", self._evidence_backed,
            )

    # ----- Rendering -----

    def stats_line(self) -> str:
        filled = sum(
            1 for c in self._cells.values()
            if c.get("status") in ("filled", "resolved")
        )
        total = len(self._cells)
        cells = f"{filled}/{total}" if total else "0/0"
        return (
            f"覆盖 {self._coverage:.0%} · 单元 {cells} · 证据 {self._evidence_count} "
            f"· 动作 {self._search_count} · agents {len(self._agents)}"
        )

    def _render_agents(self) -> Panel:
        # The orchestrator's own tool calls now live in the stream view, so the
        # Agents panel stays compact: just the dispatched sub-agent tiles.
        sections: list[Any] = []
        if not self._agents:
            sections.append(Text("(waiting for agents)", style="dim"))

        if self._agents:
            tile_width = 52
            body_width = tile_width - 6
            tiles = []
            for a in self._agents:
                if a.status == "completed":
                    icon, color = "✓", "green"
                    body = Text(a.summary or "(done)", style="dim",
                                overflow="ellipsis", no_wrap=True)
                else:
                    icon, color = "→", "yellow"
                    body = Text(a.last_action or "(pending)",
                                overflow="ellipsis", no_wrap=True)
                body.truncate(body_width, overflow="ellipsis")
                title = f"{icon} {a.agent} [{a.step_count}]"
                tiles.append(Panel(body, title=title, border_style=color,
                                   padding=(0, 1), height=3, width=tile_width))
            sections.append(Columns(tiles, expand=False, equal=False, column_first=False))

        return Panel(Group(*sections), title="Agents", border_style=ACCENT)

    def _render_progress(self) -> Panel:
        bar = ProgressBar(total=1.0, completed=self._coverage, width=30)
        filled = sum(
            1 for c in self._cells.values()
            if c.get("status") in ("filled", "resolved")
        )
        total = len(self._cells)
        counter = Table.grid(padding=(0, 2))
        for _ in range(4):
            counter.add_column()
        counter.add_row(
            bar,
            Text(f"{self._coverage:.0%}", style="bold green"),
            Text(f"Cells: {filled}/{total}", style="bold"),
            Text(
                f"Backed: {self._evidence_backed:.0%}  "
                f"Evidence: {self._evidence_count}  Actions: {self._search_count}",
                style="bold",
            ),
        )
        matrix = self._render_coverage_matrix()
        body: Any = Group(counter, matrix) if matrix is not None else counter
        return Panel(body, title="Progress", border_style=DEFAULT_TOOL_COLOR)

    def _render_coverage_matrix(self) -> Any:
        if not self._tables:
            return None
        status_icon = {
            "filled": ("●", "green"),
            "resolved": ("●", "green"),
            "uncertain": ("?", "yellow"),
            "hard_cell": ("✗", "red"),
            "missing": ("·", "bright_black"),
        }
        sections: list[Any] = []
        for t in self._tables[:3]:
            tid = t["table_id"]
            entities = t["entities"]
            attrs = t["attributes"]
            pk = t["primary_key"]
            label = t["table_label"] or tid
            prefix = f"{tid}/"
            t_cells = [c for k, c in self._cells.items() if k.startswith(prefix)]
            t_total = len(t_cells)
            t_filled = sum(1 for c in t_cells if c.get("status") in ("filled", "resolved"))
            t_pct = (t_filled / t_total) if t_total else 0.0
            sections.append(Text(
                f"[{tid}] {label} — {t_filled}/{t_total} ({t_pct:.0%})",
                style="bold cyan",
            ))
            if not entities or not attrs:
                sections.append(Text("  (no rows yet)", style="dim"))
                sections.append(Text(""))
                continue
            has_keys = bool(pk)
            if has_keys:
                pk_cols = list(pk)
                data_cols = [a for a in attrs if a not in set(pk)]
            else:
                pk_cols = ["entity"]
                data_cols = attrs
            matrix = Table(show_header=True, header_style="bold cyan",
                           pad_edge=False, padding=(0, 1), box=None)
            pk_max_width = max(10, 24 // max(len(pk_cols), 1))
            for pk_col in pk_cols:
                pk_label = pk_col if len(pk_col) <= 14 else pk_col[:13] + "…"
                matrix.add_column(pk_label, style="bold white on grey23",
                                  header_style="bold yellow on grey23", no_wrap=True,
                                  overflow="ellipsis", max_width=pk_max_width)
            for attr in data_cols[:6]:
                attr_label = attr if len(attr) <= 18 else attr[:17] + "…"
                matrix.add_column(attr_label, justify="center", no_wrap=True)
            for ent in entities[:12]:
                if has_keys:
                    parts = ent.split("|")
                    if len(parts) < len(pk_cols):
                        parts = parts + [""] * (len(pk_cols) - len(parts))
                    pk_cells = [
                        Text((p if len(p) <= pk_max_width else p[: pk_max_width - 1] + "…"),
                             style="bold white on grey23")
                        for p in parts[: len(pk_cols)]
                    ]
                else:
                    lbl = ent if len(ent) <= 22 else ent[:21] + "…"
                    pk_cells = [Text(lbl, style="bold white on grey23")]
                row: list[Any] = list(pk_cells)
                for attr in data_cols[:6]:
                    cell = self._cells.get(f"{tid}/{ent}.{attr}")
                    if cell is None:
                        row.append(Text("--", style="dim"))
                        continue
                    icon, color = status_icon.get(
                        cell.get("status", "missing"), ("·", "bright_black"))
                    if cell.get("status") in ("filled", "resolved") and cell.get("value"):
                        val = cell["value"]
                        if isinstance(val, list):
                            val = val[0] if val else ""
                        val_str = str(val)
                        display = val_str[:16] + ("…" if len(val_str) > 16 else "")
                        row.append(Text(display, style=color))
                    else:
                        row.append(Text(icon, style=color))
                matrix.add_row(*row)
            if len(entities) > 12:
                matrix.add_row(Text(f"... +{len(entities) - 12} more", style="dim"))
            sections.append(matrix)
            sections.append(Text(""))
        if len(self._tables) > 3:
            sections.append(Text(f"... +{len(self._tables) - 3} tables", style="dim"))
        if self._relations:
            rel_strs = []
            for r in self._relations[:4]:
                ft = r.get("from_table", "")
                tt = r.get("to_table", "")
                fk = r.get("foreign_key", []) or []
                fk_str = ",".join(fk) if fk else ""
                rel_strs.append(f"{ft}.[{fk_str}] → {tt}")
            sections.append(Text("relations: " + "  |  ".join(rel_strs), style="dim italic"))
        return Group(*sections)

    def _render_events(self) -> Panel:
        table = Table.grid(padding=(0, 1))
        table.add_column()
        if self._code_events:
            for c in self._code_events:
                table.add_row(Text(f"⚙ {c}", style="magenta bold"))
        if not self._recent_events and not self._code_events:
            table.add_row(Text("(no events yet)", style="dim"))
        for e in list(self._recent_events)[-MAX_RECENT_EVENTS:]:
            table.add_row(Text(e, style="dim"))
        return Panel(table, title="Recent Events", border_style=C_SCHEMA)

    def _render_frontier(self) -> Panel:
        from collections import Counter
        counts = Counter(t["status"] for t in self._frontier_tasks)
        total = len(self._frontier_tasks)
        done = counts.get("completed", 0)
        pct = (done / total) if total else 0.0
        head = Table.grid(padding=(0, 1))
        head.add_column()
        head.add_column()
        head.add_row(
            ProgressBar(total=1.0, completed=pct, width=22),
            Text(f"{done}/{total} done ({pct:.0%})", style="green"),
        )
        bits = []
        for st, label in (("running", "running"), ("pending", "queued"),
                          ("blocked", "blocked"), ("cancelled", "cancelled")):
            if counts.get(st):
                icon, style = FRONTIER_ICON[st]
                bits.append(f"[{style}]{icon} {counts[st]} {label}[/]")
        rows: list[Any] = [
            head,
            Text.from_markup("   ·   ".join(bits)) if bits else Text(""),
        ]
        ordered = sorted(
            self._frontier_tasks,
            key=lambda t: (FRONTIER_ORDER.get(t["status"], 9), -t.get("priority", 0.0)),
        )
        for t in ordered[:FRONTIER_MAX_ROWS]:
            icon, style = FRONTIER_ICON.get(t["status"], ("·", "white"))
            line = Text()
            line.append(f"{icon} ", style=style)
            task_text = (t["question"] or t["id"]).replace("\n", " ")
            line.append(task_text[:58],
                        style="strike dim" if t["status"] == "cancelled" else "")
            if t["status"] == "running" and t["agent"]:
                line.append(f"  → {t['agent']}", style="cyan dim")
            elif t["status"] == "blocked" and t["blocked_by"]:
                line.append(f"  ⛔ {len(t['blocked_by'])} dep", style="yellow dim")
            rows.append(line)
        hidden = len(self._frontier_tasks) - min(len(ordered), FRONTIER_MAX_ROWS)
        if hidden > 0:
            rows.append(Text(f"... +{hidden} more", style="dim"))
        return Panel(Group(*rows), title="Frontier (plan)", border_style=C_DISPATCH)
