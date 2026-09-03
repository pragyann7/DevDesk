"""Compact service status line used in lists and the status bar."""

from __future__ import annotations

from textual.widgets import Static

from devdesk.models.service import Service
from devdesk.utils.terminal import format_port, status_label


class ServiceStatus(Static):
    def __init__(self, service: Service | None = None) -> None:
        super().__init__(self._text(service), classes="service-status")
        self._service_name = service.name if service else ""

    def show(self, service: Service | None) -> None:
        self._service_name = service.name if service else ""
        self.update(self._text(service))
        state = service.state.value.lower() if service else "stopped"
        self.set_classes(f"service-status status-{state}")

    @staticmethod
    def _text(service: Service | None) -> str:
        if service is None:
            return ""
        pid = f" pid {service.pid}" if service.pid else ""
        return f"{service.name} {status_label(service.state)} {format_port(service.port)}{pid}".rstrip()
