"""Reusable live log widget. One instance per service; buffers stay in LogManager."""

from __future__ import annotations

from textual.containers import Vertical
from textual.widgets import Log

from devdesk.core.log_manager import LogEvent
from devdesk.models.service import Service
from devdesk.ui.widgets.service_header import ServiceHeader


class LogPanel(Vertical):
    can_focus = True

    def __init__(self, service_name: str | None = None, title: str | None = None, **kwargs) -> None:
        classes = f"log-panel {kwargs.pop('classes', '')}".strip()
        super().__init__(classes=classes, **kwargs)
        self.service_name = service_name
        self._title = title or (service_name or "Service")
        self.paused = False
        self.follow = True
        self._pending: list[LogEvent] = []

    def compose(self):
        yield ServiceHeader(self._title)
        yield Log(highlight=False, classes="log-body")

    def set_service(self, service: Service | None, title: str | None = None) -> None:
        self.service_name = service.name if service else None
        if title:
            self._title = title
        elif service:
            self._title = service.name
        header = self.query_one(ServiceHeader)
        header.set_title(self._title)
        header.set_service(service)

    def set_follow(self, follow: bool) -> None:
        self.follow = follow
        self.query_one(Log).auto_scroll = follow

    def toggle_pause(self) -> bool:
        self.paused = not self.paused
        if not self.paused:
            self._flush_pending()
        return self.paused

    def append_event(self, event: LogEvent) -> None:
        if self.service_name is None or event.service != self.service_name:
            return
        if self.paused:
            self._pending.append(event)
            return
        self._write(event)

    def load_events(self, events: list[LogEvent]) -> None:
        log = self.query_one(Log)
        log.clear()
        self._pending.clear()
        for event in events:
            self._write(event)

    def clear_view(self) -> None:
        self._pending.clear()
        self.query_one(Log).clear()

    def _flush_pending(self) -> None:
        for event in self._pending:
            self._write(event)
        self._pending.clear()

    def _write(self, event: LogEvent) -> None:
        log = self.query_one(Log)
        prefix = "!" if event.stream == "stderr" else " "
        stamp = event.timestamp.strftime("%H:%M:%S")
        log.write_line(f"{stamp}{prefix} {event.message}")
        if self.follow:
            log.scroll_end(animate=False)
