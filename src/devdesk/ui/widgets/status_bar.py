"""Bottom status bar: per-service indicators and session uptime."""

from __future__ import annotations

from datetime import datetime

from textual.widgets import Static

from devdesk.models.service import Service
from devdesk.utils.terminal import STATUS_GLYPHS, format_port, format_uptime


class StatusBar(Static):
    def __init__(self) -> None:
        super().__init__("", id="status-bar")
        self._started = datetime.now()

    def show(self, services: list[Service], *, hint: str = "") -> None:
        if not services:
            text = "No project loaded"
            if hint:
                text = f"{text}  ·  {hint}"
            self.update(text)
            return
        parts = [self._chip(service) for service in services]
        parts.append(f"Uptime {format_uptime(self._started)}")
        if hint:
            parts.append(hint)
        self.update("   ".join(parts))

    def reset_uptime(self) -> None:
        self._started = datetime.now()

    @staticmethod
    def _chip(service: Service) -> str:
        glyph = STATUS_GLYPHS[service.state]
        port = format_port(service.port)
        return f"{service.name} {glyph} {port}".rstrip()
