"""Persistent navigation sidebar."""

from __future__ import annotations

from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.events import Click
from textual.widget import Widget
from textual.widgets import Static

from devdesk.ui import SidebarCommand

_SECTIONS: list[tuple[str, str]] = [
    ("section:project-nav", "PROJECT"),
    ("dashboard", "Dashboard"),
    ("backend", "Backend"),
    ("frontend", "Frontend"),
    ("api_monitor", "API Monitor"),
    ("section:actions", "ACTIONS"),
    ("start_all", "Start All"),
    ("restart_all", "Restart All"),
    ("stop_all", "Stop All"),
    ("section:project", "PROJECT"),
    ("switch_project", "Switch Project"),
    ("configure_project", "Configure Project"),
    ("section:system", "SYSTEM"),
    ("settings", "Settings"),
    ("exit", "Exit"),
]

_SELECTABLE = [item_id for item_id, _label in _SECTIONS if not item_id.startswith("section:")]


class Sidebar(VerticalScroll):
    can_focus = True
    BINDINGS = [
        Binding("up", "move(-1)", "Up", show=False),
        Binding("down", "move(1)", "Down", show=False),
        Binding("enter", "choose", "Select", show=False),
    ]

    def __init__(self) -> None:
        super().__init__(id="sidebar")
        self.selected = "dashboard"

    def compose(self):
        for item_id, label in _SECTIONS:
            if item_id.startswith("section:"):
                yield Static(label, classes="nav-section")
            else:
                marker = "❯ " if item_id == self.selected else "  "
                yield Static(f"{marker}{label}", id=f"nav-{item_id}", classes="nav-item")

    def on_mount(self) -> None:
        self._refresh()

    def highlight(self, command: str) -> None:
        if command in _SELECTABLE:
            self.selected = command
            self._refresh()

    def action_move(self, delta: int) -> None:
        index = _SELECTABLE.index(self.selected)
        index = max(0, min(len(_SELECTABLE) - 1, index + delta))
        self.selected = _SELECTABLE[index]
        self._refresh()

    def action_choose(self) -> None:
        self.post_message(SidebarCommand(self.selected))

    def on_click(self, event: Click) -> None:
        widget = event.widget
        if not isinstance(widget, Widget) or widget.id is None or not widget.id.startswith("nav-"):
            return
        command = widget.id.removeprefix("nav-")
        if command in _SELECTABLE:
            self.selected = command
            self._refresh()
            self.post_message(SidebarCommand(command))

    def _refresh(self) -> None:
        for item_id, label in _SECTIONS:
            if item_id.startswith("section:"):
                continue
            node = self.query_one(f"#nav-{item_id}", Static)
            selected = item_id == self.selected
            node.update(f"{'❯ ' if selected else '  '}{label}")
            node.set_class(selected, "--selected")
