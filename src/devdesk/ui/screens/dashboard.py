"""Primary dashboard: two independent live output panels."""

from __future__ import annotations

from textual.containers import Vertical
from textual.widgets import Static

from devdesk.models.project import Project
from devdesk.ui.widgets.log_panel import LogPanel


class DashboardView(Vertical):
    def compose(self):
        yield LogPanel(title="Frontend", id="panel-top")
        yield LogPanel(title="Backend", id="panel-bottom")
        yield Static(
            "No project loaded.\nOpen a project from the sidebar to configure services.\n"
            "[ ] cycle extra services when a project has more than two.",
            id="empty-state",
        )

    def bind_project(self, project: Project | None, offset: int = 0) -> None:
        top_panel = self.query_one("#panel-top", LogPanel)
        bottom_panel = self.query_one("#panel-bottom", LogPanel)
        empty = self.query_one("#empty-state", Static)
        if project is None or not project.services:
            top_panel.display = False
            bottom_panel.display = False
            empty.display = True
            return
        empty.display = False
        top, bottom = project.display_pair(offset)
        top_panel.display = top is not None
        bottom_panel.display = bottom is not None
        if top:
            top_panel.set_service(top)
        if bottom:
            bottom_panel.set_service(bottom)
        elif top:
            bottom_panel.display = False
