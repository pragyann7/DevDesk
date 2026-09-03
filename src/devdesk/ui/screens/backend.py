"""Expanded live view for the backend-role service."""

from __future__ import annotations

from textual.containers import Vertical
from textual.widgets import Static

from devdesk.models.service import Service
from devdesk.ui.widgets.log_panel import LogPanel


class BackendView(Vertical):
    def compose(self):
        yield Static(
            "Pause P  ·  Follow L  ·  Clear C  ·  Restart R  ·  Stop S",
            classes="muted",
        )
        yield LogPanel(title="Backend", id="backend-panel")
        yield Static(
            "No backend-role service in this project.",
            id="backend-empty",
            classes="muted",
        )

    def bind_service(self, service: Service | None) -> None:
        panel = self.query_one("#backend-panel", LogPanel)
        empty = self.query_one("#backend-empty", Static)
        if service is None:
            panel.display = False
            empty.display = True
            return
        empty.display = False
        panel.display = True
        panel.set_service(service)
