"""Reusable header for a service log panel."""

from __future__ import annotations

from textual.containers import Horizontal
from textual.widgets import Static

from devdesk.models.service import Service, ServiceState
from devdesk.utils.terminal import format_port, status_label


class ServiceHeader(Horizontal):
    def __init__(self, title: str = "SERVICE", live: bool = True, **kwargs) -> None:
        super().__init__(classes="service-header", **kwargs)
        self._title = title
        self._live = live

    def compose(self):
        suffix = " — LIVE" if self._live else ""
        self._title_widget = Static(f"{self._title.upper()}{suffix}", classes="service-header-title")
        self._status_widget = Static("○ STOPPED", classes="service-header-status status-stopped")
        yield self._title_widget
        yield self._status_widget

    def set_title(self, title: str, live: bool | None = None) -> None:
        self._title = title
        if live is not None:
            self._live = live
        suffix = " — LIVE" if self._live else ""
        self._title_widget.update(f"{self._title.upper()}{suffix}")

    def set_service(self, service: Service | None) -> None:
        if service is None:
            self._status_widget.update("○ NONE")
            self._status_widget.set_classes("service-header-status status-stopped")
            return
        port = format_port(service.port)
        extra = f" {port}" if port else ""
        pid = f" pid {service.pid}" if service.pid else ""
        self._status_widget.update(f"{status_label(service.state)}{extra}{pid}")
        self._status_widget.set_classes(
            f"service-header-status status-{service.state.value.lower()}"
        )

    def set_state(self, state: ServiceState, port: int | None = None, pid: int | None = None) -> None:
        port_text = f" {format_port(port)}" if port else ""
        pid_text = f" pid {pid}" if pid else ""
        self._status_widget.update(f"{status_label(state)}{port_text}{pid_text}")
        self._status_widget.set_classes(f"service-header-status status-{state.value.lower()}")
