"""Expanded live view for the frontend-role service.

The label comes from the service name; this is not tied to a web framework.
"""

from __future__ import annotations

from textual.containers import Vertical
from textual.widgets import Static

from devdesk.models.service import Service
from devdesk.ui.widgets.log_panel import LogPanel


class FrontendView(Vertical):
    def compose(self):
        yield Static(
            "Pause P  ·  Follow L  ·  Clear C  ·  Restart R  ·  Stop S",
            classes="muted",
        )
        yield LogPanel(title="Frontend", id="frontend-panel")
        yield Static(
            "No frontend-role service in this project.",
            id="frontend-empty",
            classes="muted",
        )

    def bind_service(self, service: Service | None) -> None:
        panel = self.query_one("#frontend-panel", LogPanel)
        empty = self.query_one("#frontend-empty", Static)
        if service is None:
            panel.display = False
            empty.display = True
            return
        empty.display = False
        panel.display = True
        panel.set_service(service)
