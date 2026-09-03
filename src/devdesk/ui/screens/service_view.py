"""Generic expanded live view for any service."""

from __future__ import annotations

from textual.containers import Vertical
from textual.widgets import Static

from devdesk.models.service import Service
from devdesk.ui.widgets.log_panel import LogPanel


class ServiceView(Vertical):
    def compose(self):
        yield Static(
            "Pause P  ·  Follow L  ·  Clear C  ·  Restart R  ·  Stop S",
            classes="muted",
        )
        yield LogPanel(id="service-panel")
        yield Static(
            "Service not found.",
            id="service-empty",
            classes="muted",
        )

    def bind_service(self, service: Service | None) -> None:
        panel = self.query_one("#service-panel", LogPanel)
        empty = self.query_one("#service-empty", Static)
        if service is None:
            panel.display = False
            empty.display = True
            return
        empty.display = False
        panel.display = True
        panel.set_service(service)
