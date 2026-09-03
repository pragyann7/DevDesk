"""Reusable header for a service log panel."""

from __future__ import annotations

from textual.containers import Horizontal
from textual.widgets import Button, Static

from devdesk.models.service import Service, ServiceState
from devdesk.ui import ServiceAction
from devdesk.utils.terminal import format_port, status_label


class ServiceHeader(Horizontal):
    def __init__(self, title: str = "SERVICE", live: bool = True, **kwargs) -> None:
        super().__init__(classes="service-header", **kwargs)
        self._title = title
        self._live = live
        self._service_name: str | None = None
        self._title_widget: Static | None = None
        self._status_widget: Static | None = None
        self._controls: Horizontal | None = None
        self._btn_start: Button | None = None
        self._btn_stop: Button | None = None
        self._btn_restart: Button | None = None

    def compose(self):
        suffix = " — LIVE" if self._live else ""
        self._title_widget = Static(f"{self._title.upper()}{suffix}", classes="service-header-title")
        self._status_widget = Static("○ STOPPED", classes="service-header-status status-stopped")
        self._btn_start = Button("START", id="service-start", classes="btn-mini")
        self._btn_stop = Button("STOP", id="service-stop", classes="btn-mini")
        self._btn_restart = Button("RESTART", id="service-restart", classes="btn-mini")
        self._controls = Horizontal(
            self._btn_start,
            self._btn_stop,
            self._btn_restart,
            id="service-controls",
        )

        yield self._title_widget
        yield self._controls
        yield self._status_widget

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if not self._service_name or not event.button.id:
            return
        action = event.button.id.removeprefix("service-")
        self.post_message(ServiceAction(self._service_name, action))

    def set_title(self, title: str, live: bool | None = None) -> None:
        self._title = title
        if live is not None:
            self._live = live
        suffix = " — LIVE" if self._live else ""
        new_text = f"{self._title.upper()}{suffix}"
        if self._title_widget is not None and new_text != getattr(self, "_last_title_text", None):
            self._last_title_text = new_text
            self._title_widget.update(new_text, layout=False)

    def set_service(self, service: Service | None) -> None:
        self._service_name = service.name if service else None
        if self._controls is None:
            self._controls = self.query_one("#service-controls", Horizontal)
        self._controls.display = service is not None

        if self._status_widget is None:
            self._status_widget = self.query_one(".service-header-status", Static)

        if service is None:
            if self._status_widget is not None and getattr(self, "_last_status_text", None) != "○ NONE":
                self._last_status_text = "○ NONE"
                self._status_widget.update("○ NONE", layout=False)
                self._status_widget.set_classes("service-header-status status-stopped")
            return

        port = format_port(service.port)
        extra = f" {port}" if port else ""
        pid = f" pid {service.pid}" if service.pid else ""
        status_text = f"{status_label(service.state)}{extra}{pid}"
        status_class = f"service-header-status status-{service.state.value.lower()}"

        if self._status_widget is not None:
            if status_text != getattr(self, "_last_status_text", None):
                self._last_status_text = status_text
                self._status_widget.update(status_text, layout=False)
            if status_class != getattr(self, "_last_status_class", None):
                self._last_status_class = status_class
                self._status_widget.set_classes(status_class)

        # Enable/disable buttons based on state
        is_active = service.is_active
        if self._btn_start is None:
            self._btn_start = self.query_one("#service-start", Button)
        if self._btn_stop is None:
            self._btn_stop = self.query_one("#service-stop", Button)
        if self._btn_restart is None:
            self._btn_restart = self.query_one("#service-restart", Button)

        self._btn_start.disabled = is_active
        self._btn_stop.disabled = not is_active
        self._btn_restart.disabled = not is_active

    def set_state(self, state: ServiceState, port: int | None = None, pid: int | None = None) -> None:
        port_text = f" {format_port(port)}" if port else ""
        pid_text = f" pid {pid}" if pid else ""
        status_text = f"{status_label(state)}{port_text}{pid_text}"
        status_class = f"service-header-status status-{state.value.lower()}"
        if self._status_widget is not None:
            if status_text != getattr(self, "_last_status_text", None):
                self._last_status_text = status_text
                self._status_widget.update(status_text, layout=False)
            if status_class != getattr(self, "_last_status_class", None):
                self._last_status_class = status_class
                self._status_widget.set_classes(status_class)
