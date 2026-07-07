"""Textual widgets backing the SearchOS TUI.

The heavy lifting lives in :mod:`searchos.tui.dashboard` (the data model and
the per-section Rich renderables). These widgets are thin adapters: each panel
renders one section of the dashboard, and ``TrajectoryEvent`` carries one
trajectory event from the run callback onto the Textual event loop.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.text import Text
from textual.message import Message
from textual.widgets import Static

if TYPE_CHECKING:
    from searchos.tui.dashboard import LiveDashboard


class TrajectoryEvent(Message):
    """One trajectory event, posted from the (loop-local) run callback so it
    is handled on the Textual event loop rather than mutating widgets inline."""

    def __init__(self, event: dict) -> None:
        self.event = event
        super().__init__()


class DashboardPanel(Static):
    """A status panel that re-renders one dashboard section on ``refresh()``.

    ``renderer`` names a bound method on the dashboard (e.g. ``_render_agents``)
    that returns a Rich renderable; the widget just delegates to it so all
    rendering vocabulary stays in the dashboard.
    """

    def __init__(self, dash: LiveDashboard, renderer: str, **kwargs) -> None:
        super().__init__("", **kwargs)
        self._dash = dash
        self._renderer = renderer

    def render(self):
        try:
            return getattr(self._dash, self._renderer)()
        except Exception:  # noqa: BLE001 — never let a render error kill the UI
            return Text("")
