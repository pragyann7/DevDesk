"""Persistent navigation sidebar."""

from __future__ import annotations

from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.events import Click
from textual.widget import Widget
from textual.widgets import Static

from devdesk.models.project import Project
from devdesk.ui import SidebarCommand

_BASE_ACTIONS = [
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


class SidebarItem(Static):
    """A single interactive item in the sidebar."""
    def __init__(self, label: str, command: str, **kwargs) -> None:
        super().__init__(label, **kwargs)
        self.command_key = command


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
        self._selectable: list[str] = ["dashboard"]
        self._labels: dict[str, str] = {"dashboard": "Dashboard"}
        self._project: Project | None = None
        self._version = 0

    def compose(self):
        yield Vertical(id="sidebar-container")

    def on_mount(self) -> None:
        self._rebuild()

    def bind_project(self, project: Project | None) -> None:
        self._project = project
        if self.is_mounted:
            self._rebuild()

    def _rebuild(self) -> None:
        """Clear and rebuild the sidebar contents safely."""
        container = self.query_one("#sidebar-container", Vertical)
        container.remove_children()

        self._version += 1
        items: list[tuple[str, str, bool]] = []
        self._labels.clear()

        # 1. Project Navigation
        items.append(("section:project-nav", "PROJECT", True))
        items.append(("dashboard", "Dashboard", False))

        # 2. Services
        if self._project and self._project.services:
            items.append(("section:services", "SERVICES", True))
            for service in self._project.services:
                items.append((f"svc-{service.name}", service.name, False))
        else:
            items.append(("backend", "Backend", False))
            items.append(("frontend", "Frontend", False))

        items.append(("api_monitor", "API Monitor", False))

        # 3. Actions & System
        items.extend([(i, l, True) if i.startswith("section") else (i, l, False) for i, l in _BASE_ACTIONS])

        self._selectable = [i for i, l, s in items if not s]
        if self.selected not in self._selectable:
            self.selected = "dashboard"

        new_widgets = []
        for item_id, label, is_section in items:
            if is_section:
                new_widgets.append(Static(label, classes="nav-section"))
            else:
                self._labels[item_id] = label
                selected = item_id == self.selected
                marker = "❯ " if selected else "  "
                node = SidebarItem(
                    f"{marker}{label}",
                    command=item_id,
                    id=f"nav-{item_id}-v{self._version}",
                    classes="nav-item"
                )
                if selected:
                    node.add_class("--selected")
                new_widgets.append(node)

        container.mount_all(new_widgets)

    def highlight(self, command: str) -> None:
        if command in self._selectable:
            self.selected = command
            self._refresh()

    def action_move(self, delta: int) -> None:
        try:
            index = self._selectable.index(self.selected)
        except ValueError:
            index = 0
        index = max(0, min(len(self._selectable) - 1, index + delta))
        self.selected = self._selectable[index]
        self._refresh()

    def action_choose(self) -> None:
        self.post_message(SidebarCommand(self.selected))

    def on_click(self, event: Click) -> None:
        widget = event.widget
        while widget is not self and not isinstance(widget, SidebarItem):
            widget = widget.parent
            if widget is None: return

        if isinstance(widget, SidebarItem):
            command = widget.command_key
            if command in self._selectable:
                self.selected = command
                self._refresh()
                self.post_message(SidebarCommand(command))

    def _refresh(self) -> None:
        for node in self.query(SidebarItem):
            item_id = node.command_key
            selected = item_id == self.selected
            label = self._labels.get(item_id, item_id)
            node.update(f"{'❯ ' if selected else '  '}{label}")
            node.set_class(selected, "--selected")
