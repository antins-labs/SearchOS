"""SearchOS fullscreen interactive TUI (Textual).

A Claude-Code-style shell built on Textual's single-compositor renderer: the
orchestrator's reasoning / content / tool calls stream into an append-only
``RichLog`` pinned above the input, the live coverage / agents / frontier
panels sit on top, and an always-available input line queues a query while one
is running (Esc/Ctrl-C interrupts the current run without leaving the app).

Textual owns one consistent layout + width model, so there is no Rich→ANSI→
prompt_toolkit bridge to drift and corrupt the screen on long runs.
"""

from __future__ import annotations

import asyncio
import queue
import threading
from collections import deque

from rich.console import Group
from rich.panel import Panel
from rich.text import Text
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Input, OptionList, RichLog, Static
from textual.widgets.option_list import Option

from searchos.config.effort import EFFORT_LEVELS
from searchos.harness.telemetry.conversation_context import build_preamble
from searchos.tui.dashboard import (
    ACCENT,
    C_AGENTS,
    DANGER,
    FAINT,
    MUTED,
    WARN,
    LiveDashboard,
    stream_content,
    stream_reasoning,
    stream_tool_call,
    stream_tool_result,
)
from searchos.tui.widgets import DashboardPanel, TrajectoryEvent

LOGO_LINES = [
    "  _____                     _      ____   _____",
    " / ____|                   | |    / __ \\ / ____|",
    "| (___   ___  __ _ _ __ ___| |__ | |  | | (___",
    " \\___ \\ / _ \\/ _` | '__/ __| '_ \\| |  | |\\___ \\",
    " ____) |  __/ (_| | | | (__| | | | |__| |____) |",
    "|_____/ \\___|\\__,_|_|  \\___|_| |_|\\____/|_____/",
]
# Cyan gradient stops (light → deep) the logo shimmer cycles through.
LOGO_GRADIENT = [
    (207, 250, 254), (165, 243, 252), (103, 232, 249),
    (34, 211, 238), (6, 182, 212), (2, 132, 199),
]


def _grad(pos: float) -> str:
    """Hex colour at a cyclic position along ``LOGO_GRADIENT``."""
    n = len(LOGO_GRADIENT)
    pos %= n
    i = int(pos)
    f = pos - i
    c1, c2 = LOGO_GRADIENT[i], LOGO_GRADIENT[(i + 1) % n]
    r, g, b = (round(a + (b - a) * f) for a, b in zip(c1, c2))
    return f"#{r:02x}{g:02x}{b:02x}"


# Slash commands. Each spec: (canonical, aliases, handler method, help text,
# equivalent key binding). Handlers take a single ``arg`` string (everything
# after the first space) so future commands can be parameterised — the first
# batch all ignore it. ``_COMMANDS`` flattens canonical + aliases → handler.
_COMMAND_SPECS = (
    ("new",     ("clear",),  "_cmd_new",     "开新话题（清空历史与覆盖表）",      "Ctrl-N"),
    ("verbose", ("detail",), "_cmd_verbose", "切换精简 / 详细流",                "Ctrl-T"),
    ("effort",  (),          "_cmd_effort",  "投入档位 low/medium/high/max",     ""),
    ("skill",   (),          "_cmd_skill",   "选择 access 技能 list/only/off/on/all", ""),
    ("stop",    ("cancel",), "_cmd_stop",    "中断当前运行",                     "Esc"),
    ("help",    ("?",),      "_cmd_help",    "显示本帮助",                       ""),
    ("quit",    ("exit",),   "_cmd_quit",    "退出 SearchOS",                    "Ctrl-D"),
)
_COMMANDS = {
    name: spec[2]
    for spec in _COMMAND_SPECS
    for name in (spec[0], *spec[1])
}

# /effort presets live in searchos.config.effort (shared with the web API).


class EffortModal(ModalScreen):
    """Interactive picker for the /effort budget level.

    ``/effort`` with no argument pushes this so the user can see every level
    (and the budget each implies) and pick one — rather than having to know
    the level names up front. ``/effort high`` still sets it directly.
    Dismisses with the chosen level name, or ``None`` on cancel.
    """

    DEFAULT_CSS = """
    EffortModal { align: center middle; }
    #effort-box {
        width: 72; height: auto; padding: 1 2;
        background: $surface; border: round #22d3ee;
    }
    #effort-title { text-style: bold; color: #22d3ee; padding-bottom: 1; }
    #effort-list  { height: auto; max-height: 10; background: $surface; }
    #effort-hint  { color: #6e7681; padding-top: 1; }
    """

    BINDINGS = [("escape", "cancel", "取消")]

    def __init__(self, current: str) -> None:
        super().__init__()
        self._current = current

    def compose(self) -> ComposeResult:
        with Vertical(id="effort-box"):
            yield Static("⚙ 选择投入档位 (effort)", id="effort-title")
            opts = []
            for lvl, cfg in EFFORT_LEVELS.items():
                mark = "● " if lvl == self._current else "  "
                desc = (f"迭代 {cfg['orch_max_iterations']} · "
                        f"并行 {cfg['max_parallel_agents']} · "
                        f"搜索 {cfg['max_searches_per_sub_agent']} · "
                        f"{cfg['default_max_time_s'] // 60}min")
                opts.append(Option(f"{mark}{lvl:<7}{desc}", id=lvl))
            yield OptionList(*opts, id="effort-list")
            yield Static("↑↓ 选择 · 回车 应用 · Esc 取消", id="effort-hint")

    def on_mount(self) -> None:
        ol = self.query_one("#effort-list", OptionList)
        try:
            ol.highlighted = list(EFFORT_LEVELS).index(self._current)
        except ValueError:
            pass
        ol.focus()

    def on_option_list_option_selected(
            self, event: OptionList.OptionSelected) -> None:
        self.dismiss(event.option.id)

    def action_cancel(self) -> None:
        self.dismiss(None)


class SkillModal(ModalScreen):
    """Interactive picker for which skills to load, grouped by category.

    Skills are folded under collapsible category headers (the library's three
    top-level dirs: ``orchestrator`` / ``access`` / ``strategy``). A header
    row reads ``▼`` (expanded) / ``▶`` (collapsed) plus an ``启用 N/total``
    tally; pressing Enter/Space on it folds the group. A skill row reads
    ``●`` (green) = enabled / ``○`` (dim) = disabled, so state shows in the
    glyph's shape, not just a checkbox/colour. ``self._states`` is the source
    of truth, keyed by skill name, so collapsing or filtering never loses a
    toggle. Dismisses with the set of enabled names (across all groups), or
    ``None`` on cancel.
    """

    DEFAULT_CSS = """
    SkillModal { align: center middle; }
    #skill-box {
        width: 84; height: 80%; padding: 1 2;
        background: $surface; border: round #22d3ee;
    }
    #skill-title  { text-style: bold; color: #22d3ee; }
    #skill-filter { height: 1; border: none; padding: 0; margin: 1 0;
                    background: $boost; }
    #skill-list   { height: 1fr; background: $surface; }
    #skill-hint   { color: #6e7681; padding-top: 1; }
    """

    BINDINGS = [
        ("escape", "cancel", "取消"),
        ("space", "toggle", "切换"),
        ("ctrl+t", "toggle_group", "整组开关"),
        ("ctrl+a", "enable_all", "全启用"),
        ("ctrl+r", "disable_all", "全禁用"),
    ]

    # Folding a group with this many members is the default so the modal opens
    # navigable rather than as one long wall of rows.
    _COLLAPSE_OVER = 40

    def __init__(
        self, groups: "list[tuple[str, list[str]]]", enabled: set[str]
    ) -> None:
        super().__init__()
        self._order = [label for label, _ in groups]
        self._members = {label: list(names) for label, names in groups}
        self._cat_of = {n: label for label, names in groups for n in names}
        self._states: dict[str, bool] = {
            n: (n in enabled) for _, names in groups for n in names
        }
        self._collapsed: set[str] = {
            label for label, names in groups if len(names) > self._COLLAPSE_OVER
        }
        self._flt = ""
        self._header_index: dict[str, int] = {}
        self._skill_index: dict[str, int] = {}

    def compose(self) -> ComposeResult:
        with Vertical(id="skill-box"):
            yield Static("", id="skill-title")
            yield Input(placeholder="输入以过滤…", id="skill-filter")
            yield OptionList(id="skill-list")
            yield Static(
                "输入过滤 · Tab 进入列表 · 分组标题上 回车/空格 = 展开/折叠 · "
                "技能上 = 启用/禁用 · Ctrl-T 整组开关 · Ctrl-A 全启用 · "
                "Ctrl-R 全禁用 · 过滤框回车 应用 · Esc 取消",
                id="skill-hint")

    def on_mount(self) -> None:
        self._rebuild("")
        self.query_one("#skill-filter", Input).focus()

    # --- row renderers -----------------------------------------------------
    def _expanded(self, label: str) -> bool:
        # A live filter force-expands every matching group.
        return bool(self._flt) or label not in self._collapsed

    def _header_row(self, label: str) -> Text:
        members = self._members[label]
        shown = [n for n in members if not self._flt or self._flt in n.lower()]
        on = sum(1 for n in members if self._states[n])
        arrow = "▼" if self._expanded(label) else "▶"
        t = Text()
        t.append(f"{arrow} ", style=ACCENT)
        t.append(label, style=f"bold {ACCENT}")
        extra = f" · 启用 {on}/{len(members)}"
        if self._flt and len(shown) != len(members):
            extra += f" · 过滤 {len(shown)}"
        t.append(extra, style=MUTED)
        return t

    def _skill_row(self, name: str) -> Text:
        """Indented row: ● green = enabled, ○ dim = disabled."""
        on = self._states[name]
        t = Text("   ")
        t.append("● " if on else "○ ", style=C_AGENTS if on else FAINT)
        t.append(name, style="" if on else FAINT)
        return t

    def _rebuild(self, flt: str) -> None:
        ol = self.query_one("#skill-list", OptionList)
        ol.clear_options()
        self._flt = flt.strip().lower()
        self._header_index = {}
        self._skill_index = {}
        opts: list[Option] = []
        idx = 0
        for label in self._order:
            members = self._members[label]
            shown = [n for n in members
                     if not self._flt or self._flt in n.lower()]
            if self._flt and not shown:
                continue  # group has no match — hide its header too
            opts.append(Option(self._header_row(label), id=f"cat::{label}"))
            self._header_index[label] = idx
            idx += 1
            if self._expanded(label):
                for n in shown:
                    opts.append(Option(self._skill_row(n), id=f"sk::{n}"))
                    self._skill_index[n] = idx
                    idx += 1
        if opts:
            ol.add_options(opts)
            ol.highlighted = 0
        self._update_title()

    def _update_title(self) -> None:
        on = sum(1 for v in self._states.values() if v)
        total = len(self._states)
        self.query_one("#skill-title", Static).update(
            f"⚙ 技能加载 · 已启用 {on}/{total}"
            "（orchestrator / access / strategy）")

    # --- interaction -------------------------------------------------------
    def _activate(self, opt_id: "str | None") -> None:
        if opt_id is None:
            return
        kind, _, key = opt_id.partition("::")
        if kind == "cat":
            self._collapsed.discard(key) if key in self._collapsed \
                else self._collapsed.add(key)
            self._rebuild(self._flt)
            ol = self.query_one("#skill-list", OptionList)
            if key in self._header_index:
                ol.highlighted = self._header_index[key]
        elif kind == "sk":
            self._toggle_skill(key)

    def _toggle_skill(self, name: str) -> None:
        self._states[name] = not self._states[name]
        ol = self.query_one("#skill-list", OptionList)
        if name in self._skill_index:  # refresh glyph in place — keeps scroll
            ol.replace_option_prompt_at_index(
                self._skill_index[name], self._skill_row(name))
        label = self._cat_of[name]
        if label in self._header_index:  # the group tally changed too
            ol.replace_option_prompt_at_index(
                self._header_index[label], self._header_row(label))
        self._update_title()

    def action_toggle(self) -> None:
        ol = self.query_one("#skill-list", OptionList)
        # Only when the list (not the filter box) has focus, so SPACE still
        # types a space in the filter input.
        if not ol.has_focus:
            return
        idx = ol.highlighted
        if idx is None:
            return
        self._activate(ol.get_option_at_index(idx).id)

    def on_option_list_option_selected(
            self, event: OptionList.OptionSelected) -> None:
        event.stop()  # Enter toggles the row (don't bubble to the App)
        self._activate(event.option.id)

    def action_toggle_group(self) -> None:
        """Flip the whole group the highlight sits in (header or any of its
        skills): all-on ⇒ all-off, otherwise all-on. Refreshes in place so the
        scroll position and highlight stay put."""
        ol = self.query_one("#skill-list", OptionList)
        if not ol.has_focus:  # keep Ctrl-T inert while typing in the filter
            return
        idx = ol.highlighted
        if idx is None:
            return
        opt_id = ol.get_option_at_index(idx).id
        if opt_id is None:
            return
        kind, _, key = opt_id.partition("::")
        label = key if kind == "cat" else self._cat_of.get(key)
        if label is None:
            return
        members = self._members[label]
        target = not all(self._states[n] for n in members)
        for n in members:
            self._states[n] = target
        if label in self._header_index:
            ol.replace_option_prompt_at_index(
                self._header_index[label], self._header_row(label))
        for n in members:  # only the rendered (expanded) rows need a refresh
            if n in self._skill_index:
                ol.replace_option_prompt_at_index(
                    self._skill_index[n], self._skill_row(n))
        self._update_title()

    def action_enable_all(self) -> None:
        for n in self._states:
            self._states[n] = True
        self._rebuild(self._flt)

    def action_disable_all(self) -> None:
        for n in self._states:
            self._states[n] = False
        self._rebuild(self._flt)

    def on_input_changed(self, event: Input.Changed) -> None:
        # Stop bubbling so the App's own on_input_changed (which colours the
        # main prompt) doesn't react to the filter box.
        event.stop()
        if event.input.id == "skill-filter":
            self._rebuild(event.value)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        if event.input.id == "skill-filter":
            self.dismiss({n for n, on in self._states.items() if on})

    def action_cancel(self) -> None:
        self.dismiss(None)


class SearchOSApp(App):
    """The interactive SearchOS shell."""

    CSS = """
    Screen { layers: base; }
    #banner   { height: auto; content-align: left top; padding: 1 2; }
    #panels   { height: auto; max-height: 50%; overflow-y: auto; padding: 0 1; }
    #stream   { height: 1fr; min-height: 3; padding: 0 1; margin: 0 1;
                border: round $primary; border-title-color: $primary;
                scrollbar-size-vertical: 1; }
    #footer   { dock: bottom; height: 2; }
    #statusbar{ height: 1; background: $accent; color: $text; }
    #promptline { height: 1; background: $surface; }
    #prompt   { width: 2; height: 1; color: #22d3ee; text-style: bold;
                background: $surface; }
    #input    { height: 1; border: none; padding: 0; background: $surface;
                width: 1fr; }
    """

    BINDINGS = [
        ("ctrl+d", "quit", "退出"),
        ("ctrl+q", "quit", "退出"),
        ("ctrl+c", "interrupt", "中断/退出"),
        ("escape", "interrupt", "中断/退出"),
        ("ctrl+t", "toggle_detail", "详细/精简"),
        ("ctrl+n", "new_topic", "新话题"),
    ]

    def __init__(self, session_factory, *, no_search: bool = False) -> None:
        super().__init__()
        self._session_factory = session_factory
        self._no_search = no_search

        self._mode = "idle"          # idle | running | done
        self._dash: LiveDashboard | None = None
        self._session = None
        self._queue: deque[str] = deque()
        self._note: str = ""
        # The search engine runs on its own event loop in a background thread
        # so heavy synchronous work (state serialization, disk I/O) never
        # blocks the Textual UI loop / input. One persistent loop across turns
        # keeps the browser singleton bound to a single, consistent loop.
        self._engine_loop: asyncio.AbstractEventLoop | None = None
        self._engine_thread: threading.Thread | None = None
        self._engine_task: asyncio.Task | None = None
        self._run_future = None
        # Orchestrator stream: buffer the raw items so the detail toggle can
        # re-render the whole log (compact ↔ verbose) instead of only
        # affecting items that arrive after the toggle.
        self._verbose = False
        self._stream_events: list[dict] = []
        self._banner_phase = 0.0
        # Multi-turn conversation: each completed turn carries forward its
        # workspace (session_id) + SearchState so follow-ups extend the same
        # coverage table. ``_steer_queue`` injects live follow-ups mid-run.
        self._turns: list[dict] = []
        # Thread-safe (the engine loop drains it; the UI thread fills it).
        self._steer_queue: queue.Queue[str] | None = None
        # Transient slash-command hint shown in the status bar while typing.
        self._cmd_hint: str = ""
        # /effort level (applied to the global settings budget knobs).
        self._effort: str = "medium"
        # /skill access-catalog selection, threaded into run() each turn:
        #  _access_only  — None = router decides; else pin to exactly this set
        #  _access_deny  — names always removed from the catalog
        self._access_only: set[str] | None = None
        self._access_deny: set[str] = set()
        # strategy/orchestrator skills carry no router — default all-on, with
        # the /skill picker's unchecked names subtracted via these deny sets.
        self._strategy_deny: set[str] = set()
        self._orchestrator_deny: set[str] = set()

    # ----- Layout -----

    def compose(self) -> ComposeResult:
        yield Static(self._render_banner(), id="banner")
        yield VerticalScroll(id="panels")
        yield RichLog(id="stream", wrap=True, auto_scroll=True, markup=False,
                      highlight=False)
        with Vertical(id="footer"):
            yield Static("", id="statusbar")
            with Horizontal(id="promptline"):
                yield Static("❯", id="prompt")
                yield Input(id="input", placeholder="输入问题，回车开始…")

    def on_mount(self) -> None:
        self.query_one("#stream", RichLog).border_title = "✻ Orchestrator"
        self._set_mode("idle")
        self.query_one("#input", Input).focus()
        self.set_interval(0.5, self._poll)
        # Banner: fade in, then run a slow cyan shimmer across the logo.
        banner = self.query_one("#banner", Static)
        banner.styles.opacity = 0.0
        banner.styles.animate("opacity", value=1.0, duration=0.6)
        self.set_interval(0.08, self._animate_banner)

    # ----- Banner -----

    def _render_banner(self):
        try:
            from importlib.metadata import version
            ver = version("searchos")
        except Exception:
            ver = "0.1.0"
        lines: list = [Text("")]
        for li, line in enumerate(LOGO_LINES):
            t = Text()
            for x, ch in enumerate(line):
                if ch == " ":
                    t.append(" ")
                else:
                    # col + per-line offset + animated phase → diagonal flow
                    t.append(ch, style=_grad(x * 0.13 + li * 0.5 + self._banner_phase))
            lines.append(t)
        lines.append(Text(f"the agentic search collaboration system · v{ver}", style=MUTED))
        lines.append(Text(""))
        welcome = Panel(
            Text.from_markup(
                f"[{ACCENT}]✻[/] Welcome to [bold]SearchOS[/]!\n\n"
                f"[{MUTED}]Ask anything. Agents fan out across the web, fill a "
                f"coverage table cell by cell, and forge the answer with "
                f"evidence.[/]\n"
                f"[{MUTED}]web search: {'off' if self._no_search else 'on'}[/]"
            ),
            border_style=ACCENT,
        )
        return Group(*lines, welcome)

    def _animate_banner(self) -> None:
        if self._mode != "idle":
            return
        self._banner_phase += 0.15
        self.query_one("#banner", Static).update(self._render_banner())

    # ----- Mode / display -----

    def _set_mode(self, mode: str) -> None:
        self._mode = mode
        # "done" keeps the live panels + the orchestrator stream on screen: the
        # final answer is just the last content the orchestrator streamed in —
        # no separate answer page.
        show = {
            "idle":    {"banner"},
            "running": {"panels", "stream"},
            "done":    {"panels", "stream"},
        }[mode]
        for wid in ("banner", "panels", "stream"):
            self.query_one(f"#{wid}").display = wid in show
        # Prompt glyph: bright cyan when ready for input, dimmed while running.
        try:
            self.query_one("#prompt").styles.color = (
                FAINT if mode == "running" else ACCENT)
        except Exception:
            pass
        self._update_statusbar()

    def _update_statusbar(self) -> None:
        # While typing a slash command, the live hint takes over the bar.
        if self._cmd_hint:
            self.query_one("#statusbar", Static).update(f" {self._cmd_hint} ")
            return
        note = f"  ·  {self._note}" if self._note else ""
        if self._mode == "running":
            stats = self._dash.stats_line() if self._dash else ""
            text = f" {stats}  ·  RUNNING — 回车追问 · Esc 中断 · Ctrl-T 详情{note} "
        elif self._mode == "done":
            text = (f" 完成 — 回车追问(续表) · Ctrl-N 新话题 · "
                    f"Ctrl-T 详情 · Ctrl-D 退出{note} ")
        else:
            text = " idle — 输入问题回车开始 · Ctrl-D 退出 "
        self.query_one("#statusbar", Static).update(text)

    # ----- Live panels -----

    def _mount_panels(self) -> None:
        """(Re)build the status panels bound to the current dashboard."""
        container = self.query_one("#panels", VerticalScroll)
        container.remove_children()
        container.mount(
            DashboardPanel(self._dash, "_render_agents"),
            DashboardPanel(self._dash, "_render_progress"),
            DashboardPanel(self._dash, "_render_frontier"),
            DashboardPanel(self._dash, "_render_events"),
        )

    def _refresh_panels(self) -> None:
        # layout=True so each panel's height is recomputed as the dashboard
        # data grows. With the default refresh() (layout=False) the height
        # stays frozen at the initial (empty) measurement, clipping panels
        # whose content has since grown (e.g. the agent tiles render only
        # their top border).
        for panel in self.query(DashboardPanel):
            panel.refresh(layout=True)

    def _poll(self) -> None:
        if self._mode != "running" or self._dash is None:
            return
        if self._dash._state_path is None and self._session is not None:
            ws = getattr(self._session, "_active_workspace", None)
            if ws is not None:
                self._dash.set_state_path(
                    ws.trajectory_path.parent / "search_state.json")
        try:
            self._dash.poll_state()
        except Exception:
            pass
        self._refresh_panels()
        self._update_statusbar()

    # ----- Trajectory stream -----

    def _on_event(self, event: dict) -> None:
        """Run-side callback (loop-local) — hand off to the Textual loop."""
        self.post_message(TrajectoryEvent(event))

    def on_trajectory_event(self, message: TrajectoryEvent) -> None:
        event = message.event
        if self._dash is not None:
            self._dash.feed(event)
        log = self.query_one("#stream", RichLog)
        for item in self._stream_items_from_event(event):
            self._stream_events.append(item)
            log.write(self._render_stream_item(item))

    @staticmethod
    def _stream_items_from_event(event: dict) -> list[dict]:
        """Normalize a trajectory event into renderable stream items."""
        etype = event.get("type")
        items: list[dict] = []
        if etype == "assistant":
            r = (event.get("reasoning", "") or "").strip()
            c = (event.get("content", "") or "").strip()
            if r:
                items.append({"kind": "reasoning", "text": r})
            if c:
                items.append({"kind": "content", "text": c})
        elif etype == "orchestrator_tool_call":
            items.append({"kind": "tool_call",
                          "tool": event.get("tool", "?"),
                          "args": event.get("args", {})})
        elif etype == "orchestrator_tool":
            res = event.get("result_preview", "")
            if res:
                items.append({"kind": "tool_result", "result": res})
        return items

    def _render_stream_item(self, item: dict):
        v = self._verbose
        kind = item["kind"]
        if kind == "reasoning":
            return stream_reasoning(item["text"], v)
        if kind == "content":
            return stream_content(item["text"], v)
        if kind == "tool_call":
            return stream_tool_call(item["tool"], item["args"], v)
        if kind == "tool_result":
            return stream_tool_result(item["result"], v)
        if kind == "marker":
            return Text(item["text"], style=item.get("style", ""))
        return Text("")

    def _write_marker(self, text: str, style: str = "") -> None:
        """Append a UI marker line (turn separator, follow-up echo, error) to
        the stream; buffered so the detail toggle keeps it on re-render."""
        item = {"kind": "marker", "text": text, "style": style}
        self._stream_events.append(item)
        self.query_one("#stream", RichLog).write(self._render_stream_item(item))

    @staticmethod
    def _extract_answer(result) -> str:
        """This turn's answer — the orchestrator's last AI text message.

        Read from ``result.final_messages`` (not the stream buffer) so it's
        independent of when the Textual message pump drained the last event;
        used as the prior-turn answer in the next follow-up's preamble.
        """
        for msg in reversed(getattr(result, "final_messages", []) or []):
            if msg.get("role") not in ("ai", "assistant"):
                continue
            content = msg.get("content", "")
            if isinstance(content, list):
                parts = [b.get("text", "") for b in content
                         if isinstance(b, dict) and b.get("type") == "text"]
                content = "\n".join(p for p in parts if p)
            if isinstance(content, str) and content.strip():
                return content.strip()
        return ""

    def action_toggle_detail(self) -> None:
        """Flip the orchestrator stream between compact and verbose, then
        re-render the buffered log so the change applies retroactively."""
        self._verbose = not self._verbose
        log = self.query_one("#stream", RichLog)
        log.clear()
        for item in self._stream_events:
            log.write(self._render_stream_item(item))
        self._note = "详细模式" if self._verbose else "精简模式"
        self._update_statusbar()

    # ----- Input / lifecycle -----

    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        self.query_one("#input", Input).clear()
        self._cmd_hint = ""
        self._set_input_color(None)
        if not text:
            self._update_statusbar()
            return
        if text.startswith("/"):
            # Slash commands take priority over the running-mode follow-up path
            # so e.g. /stop and /verbose work mid-run.
            self._dispatch_command(text)
            return
        if self._mode == "running":
            # Live follow-up: inject into the running orchestrator (sub-agents
            # keep running) rather than queueing for after completion.
            if self._steer_queue is not None:
                self._steer_queue.put_nowait(text)
            self._write_marker(f"❯ {text}", f"bold {ACCENT}")
            self._note = "已插入追问"
            self._update_statusbar()
        else:
            self._start_run(text)

    def action_interrupt(self) -> None:
        # In running mode we never exit — Esc/Ctrl-C cancels the run. Cancel on
        # the engine loop if the task is up yet, else cancel the pending future
        # (covers the schedule→start window so a stray Esc can't quit the app).
        if self._mode == "running":
            loop, task = self._engine_loop, self._engine_task
            if loop is not None and task is not None:
                loop.call_soon_threadsafe(task.cancel)
            elif self._run_future is not None:
                self._run_future.cancel()
            self._note = "已请求中断…"
            self._update_statusbar()
        else:
            self.exit()

    def action_new_topic(self) -> None:
        """Drop the conversation history so the next query starts a fresh
        workspace / coverage table instead of extending the previous one."""
        if self._mode == "running":
            self._note = "运行中无法开新话题（先 Esc 中断）"
            self._update_statusbar()
            return
        self._turns.clear()
        self._stream_events.clear()
        self.query_one("#stream", RichLog).clear()
        # Drop the previous run's dashboard + panels so nothing stale can
        # flash when the next run mounts its own.
        self._dash = None
        self.query_one("#panels", VerticalScroll).remove_children()
        self._note = "已开始新话题"
        self._set_mode("idle")

    # ----- Slash commands -----

    def on_input_changed(self, event: Input.Changed) -> None:
        """Live hint + colour feedback while typing a slash command: the input
        text turns cyan once it resolves to a real command, amber while it's a
        prefix of one, red when nothing matches (Claude-Code style)."""
        val = event.value
        if not val.startswith("/"):
            self._cmd_hint = ""
            self._set_input_color(None)
            self._update_statusbar()
            return
        cmd, sep, _rest = val[1:].partition(" ")
        cmd = cmd.lower()
        exact = cmd in _COMMANDS
        prefixes = [
            spec[0]
            for spec in _COMMAND_SPECS
            if any(n.startswith(cmd) for n in (spec[0], *spec[1]))
        ]
        if sep:
            # Typing an argument — hint the valid values for parameterised cmds.
            if cmd == "effort":
                self._cmd_hint = "档位： low · medium · high · max"
            elif cmd == "skill":
                self._cmd_hint = "子指令： list · only <名> · off <名> · on <名> · all"
            else:
                self._cmd_hint = ""
        elif prefixes:
            self._cmd_hint = "指令： " + "   ".join("/" + m for m in prefixes)
        else:
            self._cmd_hint = "无匹配指令（/help 查看全部）"
        # Colour: cyan = resolves to a command, amber = still a prefix, red = none.
        if exact:
            self._set_input_color(ACCENT)
        elif prefixes and not sep:
            self._set_input_color(WARN)
        else:
            self._set_input_color(DANGER)
        self._update_statusbar()

    def _set_input_color(self, color: str | None) -> None:
        """Tint the input text (``None`` resets to the theme default)."""
        inp = self.query_one("#input", Input)
        if color is None:
            inp.styles.color = None
            inp.styles.text_style = "none"
        else:
            inp.styles.color = color
            inp.styles.text_style = "bold"

    def _dispatch_command(self, raw: str) -> None:
        name, _, arg = raw[1:].partition(" ")
        name = name.lower().strip()
        handler = _COMMANDS.get(name)
        if handler is None:
            self._write_marker(
                f"未知指令 /{name}（输入 /help 查看全部）", DANGER)
            return
        getattr(self, handler)(arg.strip())

    def _cmd_new(self, arg: str) -> None:
        self.action_new_topic()

    def _cmd_verbose(self, arg: str) -> None:
        self.action_toggle_detail()

    def _cmd_stop(self, arg: str) -> None:
        if self._mode == "running":
            self.action_interrupt()
        else:
            self._note = "当前没有运行中的任务"
            self._update_statusbar()

    def _cmd_quit(self, arg: str) -> None:
        self.exit()

    def _cmd_help(self, arg: str) -> None:
        from rich.table import Table

        table = Table(
            title="斜杠指令", title_style=f"bold {ACCENT}",
            show_header=True, header_style=MUTED, box=None,
            padding=(0, 2, 0, 0),
        )
        table.add_column("指令", style=ACCENT, no_wrap=True)
        table.add_column("说明", style=MUTED)
        table.add_column("快捷键", style=FAINT, no_wrap=True)
        for canonical, aliases, _h, helptext, key in _COMMAND_SPECS:
            names = "/" + canonical
            if aliases:
                names += "  (" + ", ".join("/" + a for a in aliases) + ")"
            table.add_row(names, helptext, key)
        self.query_one("#stream", RichLog).write(table)

    # ----- /effort -----

    def _cmd_effort(self, arg: str) -> None:
        level = arg.strip().lower()
        if not level:
            # No argument → interactive picker so the user sees every level.
            self.push_screen(EffortModal(self._effort), self._on_effort_chosen)
            return
        if level not in EFFORT_LEVELS:
            self._write_marker(
                f"未知档位 {level!r}（可选：{' / '.join(EFFORT_LEVELS)}）", DANGER)
            return
        self._apply_effort(level)

    def _on_effort_chosen(self, level: str | None) -> None:
        if level:
            self._apply_effort(level)

    def _apply_effort(self, level: str) -> None:
        from searchos.config.settings import settings
        for key, val in EFFORT_LEVELS[level].items():
            if hasattr(settings, key):
                setattr(settings, key, val)
        # max_time_s is captured on the session blueprint at construction —
        # update it too so the change applies to the current session's runs.
        if self._session is not None:
            bp = getattr(self._session, "_blueprint", None)
            if bp is not None and hasattr(bp, "max_time_s"):
                bp.max_time_s = EFFORT_LEVELS[level]["default_max_time_s"]
        self._effort = level
        suffix = "（下一轮生效）" if self._mode == "running" else ""
        self._write_marker(f"⚙ effort → {level}{suffix}", f"bold {ACCENT}")
        self._show_effort()

    def _show_effort(self) -> None:
        from rich.table import Table

        cfg = EFFORT_LEVELS[self._effort]
        table = Table(
            title=f"effort = {self._effort}", title_style=f"bold {ACCENT}",
            show_header=True, header_style=MUTED, box=None, padding=(0, 2, 0, 0),
        )
        table.add_column("budget 旋钮", style=MUTED, no_wrap=True)
        table.add_column("值", style=ACCENT, no_wrap=True)
        labels = {
            "orch_max_iterations": "编排最大迭代",
            "max_parallel_agents": "最大并行子代理",
            "max_searches_per_sub_agent": "每代理搜索数",
            "max_finds_per_sub_agent": "每代理发现数",
            "default_max_time_s": "墙钟上限(秒)",
            "skill_router_top_k": "技能路由 top-k",
        }
        for key, label in labels.items():
            table.add_row(label, str(cfg[key]))
        self.query_one("#stream", RichLog).write(table)

    # ----- /skill -----

    def _access_skill_names(self) -> list[str]:
        """All access skill names from the (lazily built) registry, sorted."""
        if self._session is None:
            self._session = self._session_factory()
        try:
            from searchos.skills.core.models import SkillCategory
            reg = self._session.ensure_skill_registry()
            return sorted(
                s.meta.name
                for s in reg.list_by_category(SkillCategory.ACCESS)
            )
        except Exception:  # noqa: BLE001
            return []

    def _skill_pools(self) -> "dict[str, list[str]]":
        """Skill names grouped by category for the picker, in display order
        (orchestrator / access / strategy). Each value is sorted; empty dict
        if the registry can't be built (skills disabled)."""
        if self._session is None:
            self._session = self._session_factory()
        try:
            from searchos.skills.core.models import SkillCategory
            reg = self._session.ensure_skill_registry()
            cats = (
                ("orchestrator", SkillCategory.ORCHESTRATOR),
                ("access", SkillCategory.ACCESS),
                ("strategy", SkillCategory.STRATEGY),
            )
            return {
                label: sorted(s.meta.name for s in reg.list_by_category(cat))
                for label, cat in cats
            }
        except Exception:  # noqa: BLE001
            return {}

    def _group_enabled(self, label: str, name: str) -> bool:
        """Current enabled state of a skill, per its category's deny/only set."""
        if label == "access":
            return self._skill_enabled(name)
        if label == "strategy":
            return name not in self._strategy_deny
        if label == "orchestrator":
            return name not in self._orchestrator_deny
        return True

    def _resolve_skill_names(self, tokens: list[str], pool: list[str]) -> tuple[list[str], list[str]]:
        """Map user tokens to skill names by exact, then case-insensitive
        prefix/substring match. Returns (matched, unmatched_tokens)."""
        matched: list[str] = []
        unmatched: list[str] = []
        for tok in tokens:
            t = tok.strip()
            if not t:
                continue
            if t in pool:
                matched.append(t)
                continue
            low = t.lower()
            hits = [n for n in pool if n.lower().startswith(low)] or \
                   [n for n in pool if low in n.lower()]
            if hits:
                matched.extend(hits)
            else:
                unmatched.append(t)
        # de-dup preserving order
        seen: set[str] = set()
        return [n for n in matched if not (n in seen or seen.add(n))], unmatched

    def _cmd_skill(self, arg: str) -> None:
        sub, _, rest = arg.partition(" ")
        sub = sub.strip().lower()
        names = [t for t in rest.replace(",", " ").split() if t]
        if sub == "":
            # No subcommand → interactive category-grouped picker.
            pools = self._skill_pools()
            if not any(pools.values()):
                self._write_marker("未找到技能库（技能系统可能已禁用）", WARN)
                return
            groups = list(pools.items())
            enabled = {
                n for label, ns in pools.items() for n in ns
                if self._group_enabled(label, n)
            }
            self.push_screen(SkillModal(groups, enabled), self._on_skills_chosen)
            return
        pool = self._access_skill_names()
        if not pool:
            self._write_marker("未找到 access 技能库（技能系统可能已禁用）", WARN)
            return
        if sub in ("list", "ls"):
            self._show_skills(pool)
            return
        if sub == "all":
            self._access_only = None
            self._access_deny.clear()
            self._write_marker("✓ 已恢复全部 access 技能（由路由自动选取）", ACCENT)
            return
        if sub in ("only", "off", "on"):
            if not names:
                self._write_marker(f"/skill {sub} 需要技能名（/skill list 查看）", DANGER)
                return
            matched, unmatched = self._resolve_skill_names(names, pool)
            if unmatched:
                self._write_marker(f"未匹配：{', '.join(unmatched)}", WARN)
            if not matched:
                return
            if sub == "only":
                self._access_only = set(matched)
                self._access_deny.clear()
                self._write_marker(
                    f"✓ 仅启用 {len(matched)} 个 access 技能：{', '.join(matched)}", ACCENT)
            elif sub == "off":
                self._access_deny.update(matched)
                if self._access_only is not None:
                    self._access_only -= set(matched)
                self._write_marker(f"✓ 已禁用：{', '.join(matched)}", ACCENT)
            else:  # on
                self._access_deny -= set(matched)
                if self._access_only is not None:
                    self._access_only |= set(matched)
                self._write_marker(f"✓ 已启用：{', '.join(matched)}", ACCENT)
            return
        self._write_marker(
            f"未知子指令 /skill {sub}（list / only / off / on / all）", DANGER)

    def _on_skills_chosen(self, enabled: "set[str] | None") -> None:
        """Apply the SkillModal result. ``enabled`` is the set of checked skills
        across all categories (None = cancelled). Each category maps to its own
        runtime knob: access → only/deny (so a full set hands back to the
        router), strategy/orchestrator → a deny set."""
        if enabled is None:
            return
        pools = self._skill_pools()
        pa = set(pools.get("access", []))
        ps = set(pools.get("strategy", []))
        po = set(pools.get("orchestrator", []))

        # access: full set ⇒ let the query-driven router decide; else pin.
        self._access_deny.clear()
        en_a = enabled & pa
        self._access_only = None if en_a >= pa else set(en_a)
        # strategy / orchestrator: subtract the unchecked names.
        self._strategy_deny = ps - enabled
        self._orchestrator_deny = po - enabled

        def frac(p: set[str]) -> str:
            return f"{len(p & enabled)}/{len(p)}" if p else "—"

        self._write_marker(
            f"✓ 技能加载已更新 · access {frac(pa)} · "
            f"strategy {frac(ps)} · orchestrator {frac(po)}", ACCENT)

    def _skill_enabled(self, name: str) -> bool:
        if name in self._access_deny:
            return False
        if self._access_only is not None:
            return name in self._access_only
        return True

    def _show_skills(self, pool: list[str]) -> None:
        from rich.table import Table

        if self._access_only is not None:
            mode = f"only（{len(self._access_only)} 个白名单）"
        elif self._access_deny:
            mode = f"全部 − {len(self._access_deny)} 个禁用"
        else:
            mode = "全部（路由自动选取）"
        table = Table(
            title=f"access 技能 · {mode}", title_style=f"bold {ACCENT}",
            show_header=True, header_style=MUTED, box=None, padding=(0, 2, 0, 0),
        )
        table.add_column("状态", no_wrap=True)
        table.add_column("技能", style=MUTED)
        for name in pool:
            on = self._skill_enabled(name)
            table.add_row(
                Text("●", style=C_AGENTS) if on else Text("○", style=FAINT),
                Text(name, style=ACCENT if on else FAINT),
            )
        log = self.query_one("#stream", RichLog)
        log.write(table)
        log.write(Text(
            f"  共 {len(pool)} 个 · /skill 打开勾选弹窗 · /skill all 重置",
            style=FAINT))

    def _ensure_engine_loop(self) -> None:
        """Start the persistent background event loop the engine runs on."""
        if self._engine_loop is not None:
            return
        loop = asyncio.new_event_loop()
        t = threading.Thread(target=loop.run_forever, name="searchos-engine",
                             daemon=True)
        t.start()
        self._engine_loop = loop
        self._engine_thread = t

    def _start_run(self, query: str) -> None:
        self._note = ""
        follow_up = bool(self._turns)
        # Follow-up: reuse the prior turn's workspace + state (coverage table
        # carries over) and feed the orchestrator the conversation history.
        if follow_up:
            prev = self._turns[-1]
            session_id = prev["session_id"]
            initial_state = prev["state"]
            preamble = build_preamble(self._turns)
        else:
            session_id = initial_state = preamble = None
        self._dash = LiveDashboard(query=query)
        if self._session is None:
            self._session = self._session_factory()
        # The pointer still names the PREVIOUS run's workspace until run()
        # re-sets it on the engine thread; _poll fires every 0.5s and would
        # bind this fresh dashboard to the old search_state.json permanently
        # (set_state_path only happens while _state_path is None). Clear it
        # here, on the UI thread, before the engine future is scheduled.
        self._session._active_workspace = None
        self._steer_queue = queue.Queue()
        if follow_up:
            self._write_marker(f"\n──────  追问：{query}  ──────", f"bold {ACCENT}")
        else:
            self._stream_events.clear()
            self.query_one("#stream", RichLog).clear()
        self._mount_panels()
        self._set_mode("running")
        # Run the engine on its own loop/thread; never block the UI loop.
        self._ensure_engine_loop()
        self._run_future = asyncio.run_coroutine_threadsafe(
            self._engine_run(query, preamble, session_id, initial_state, follow_up),
            self._engine_loop,
        )

    async def _engine_run(self, query, preamble, session_id, initial_state, follow_up=False) -> None:
        """Runs on the engine loop (background thread). All UI mutations are
        marshalled back to the Textual thread via ``call_from_thread``."""
        self._engine_task = asyncio.current_task()
        try:
            result = await self._session.run(
                query,
                on_event=self._on_event,
                context_preamble=preamble,
                session_id=session_id,
                initial_state=initial_state,
                steer_queue=self._steer_queue,
                access_only=self._access_only,
                access_deny=self._access_deny or None,
                strategy_deny=self._strategy_deny or None,
                orchestrator_deny=self._orchestrator_deny or None,
                follow_up=follow_up,
            )
            self.call_from_thread(self._on_run_done, query, result, None)
        except asyncio.CancelledError:
            self.call_from_thread(self._on_run_done, query, None, "cancelled")
            raise
        except Exception as e:  # noqa: BLE001 — surface, don't crash the UI
            self.call_from_thread(self._on_run_done, query, None, e)
        finally:
            self._engine_task = None

    def _on_run_done(self, query: str, result, error) -> None:
        """UI-thread completion handler — the final answer is already streamed
        into #stream; here we just record the turn and flip status."""
        if error == "cancelled":
            self._note = "已中断"
            self._write_marker("⚠ 已中断本轮", WARN)
        elif isinstance(error, Exception):
            self._note = "error"
            self._write_marker(f"✗ 运行出错：{error}", f"bold {DANGER}")
        elif result is not None:
            self._note = (
                f"覆盖 {result.coverage_score:.0%} · 证据 {result.evidence_count} "
                f"· {result.elapsed_s:.0f}s · {result.eval_verdict}"
            )
            self._turns.append({
                "query": query,
                "answer": self._extract_answer(result),
                "session_id": result.session_id,
                "state": result.search_state,
            })
        self._set_mode("done")
        if self._queue:
            self._start_run(self._queue.popleft())


def run_tui(session_factory, *, no_search: bool = False) -> None:
    async def _main() -> None:
        app = SearchOSApp(session_factory, no_search=no_search)
        try:
            await app.run_async()
        finally:
            from searchos.harness.session import (
                close_browser_service,
                wait_for_all_evolutions,
            )
            # Evolutions + browser were created on the engine loop, so drain
            # and close them there, then stop that loop.
            loop = app._engine_loop
            if loop is not None and loop.is_running():
                async def _cleanup() -> None:
                    try:
                        await asyncio.wait_for(
                            wait_for_all_evolutions(timeout=None), timeout=5)
                    except Exception:
                        pass
                    await close_browser_service()
                try:
                    asyncio.run_coroutine_threadsafe(
                        _cleanup(), loop).result(timeout=30)
                except Exception:
                    pass
                loop.call_soon_threadsafe(loop.stop)

    asyncio.run(_main())
