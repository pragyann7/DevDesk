"""Reusable live log widget. One instance per service; buffers stay in LogManager."""

from __future__ import annotations

from collections.abc import Iterable

from textual.containers import Vertical
from textual.geometry import Size
from textual.widgets import Log

from devdesk.core.log_manager import LogEvent
from devdesk.models.service import Service
from devdesk.ui.widgets.service_header import ServiceHeader


class SmoothLog(Log):
    """Textual Log widget optimized for high-throughput live streams.

    Disables background thread pool worker size calculations that trigger
    delayed width callbacks, horizontal scrollbar pops, and visual jitter.
    Guarantees steady, non-bouncing auto-scrolling pinned to the latest output.
    """

    def _update_size(self, updates: int, lines: list[str]) -> None:
        # Avoid spawning thread pool workers that fire delayed asynchronous
        # callbacks modifying virtual width and causing horizontal jitter.
        pass

    def write_lines(
        self,
        lines: Iterable[str],
        scroll_end: bool | None = None,
    ) -> SmoothLog:
        auto_scroll = self.auto_scroll if scroll_end is None else scroll_end
        new_lines: list[str] = []
        for line in lines:
            new_lines.extend(line.splitlines())
        if not new_lines:
            return self
        start_line = len(self._lines)
        self._lines.extend(new_lines)
        if self.max_lines is not None and len(self._lines) > self.max_lines:
            self._prune_max_lines()
        width = self.size.width if self.size.width > 0 else 80
        self.virtual_size = Size(width, len(self._lines))
        self.refresh_lines(start_line, len(new_lines))
        user_scrolled_away = self.max_scroll_y > 0 and self.scroll_y < (self.max_scroll_y - 1)
        if auto_scroll and not self.is_vertical_scrollbar_grabbed and not user_scrolled_away:
            self.scroll_end(animate=False, immediate=True, x_axis=False)
        else:
            self.refresh()
        return self


class LogPanel(Vertical):
    can_focus = True

    def __init__(
        self,
        service_name: str | None = None,
        title: str | None = None,
        max_lines: int | None = 2000,
        **kwargs,
    ) -> None:
        classes = f"log-panel {kwargs.pop('classes', '')}".strip()
        super().__init__(classes=classes, **kwargs)
        self.service_name = service_name
        self._title = title or (service_name or "Service")
        self._max_lines = max_lines
        self.paused = False
        self.follow = True
        self._pending: list[LogEvent] = []
        self._log_widget: Log | None = None
        self._header_widget: ServiceHeader | None = None

    def compose(self):
        yield ServiceHeader(self._title)
        yield SmoothLog(highlight=False, max_lines=self._max_lines, classes="log-body")

    def on_mount(self) -> None:
        self._log_widget = self.query_one(Log)
        self._header_widget = self.query_one(ServiceHeader)
        self._log_widget.auto_scroll = self.follow

    @property
    def log_widget(self) -> Log:
        if self._log_widget is None:
            self._log_widget = self.query_one(Log)
        return self._log_widget

    @property
    def header_widget(self) -> ServiceHeader:
        if self._header_widget is None:
            self._header_widget = self.query_one(ServiceHeader)
        return self._header_widget

    def set_service(self, service: Service | None, title: str | None = None) -> None:
        self.service_name = service.name if service else None
        if title:
            self._title = title
        elif service:
            self._title = service.name
        header = self.header_widget
        header.set_title(self._title)
        header.set_service(service)

    def set_follow(self, follow: bool) -> None:
        self.follow = follow
        self.log_widget.auto_scroll = follow

    def set_max_lines(self, max_lines: int | None) -> None:
        self._max_lines = max_lines
        self.log_widget.max_lines = max_lines

    def toggle_pause(self) -> bool:
        self.paused = not self.paused
        if not self.paused:
            self._flush_pending()
        return self.paused

    def append_events(self, events: list[LogEvent]) -> None:
        if self.service_name is None or not events:
            return
        matching = [e for e in events if e.service == self.service_name]
        if not matching:
            return
        if self.paused:
            self._pending.extend(matching)
            return
        if self._max_lines and len(matching) > self._max_lines:
            matching = matching[-self._max_lines:]
        lines = [
            f"{e.timestamp.strftime('%H:%M:%S')}{'!' if e.stream == 'stderr' else ' '} {e.message}"
            for e in matching
        ]
        self.log_widget.write_lines(lines)

    def append_event(self, event: LogEvent) -> None:
        self.append_events([event])

    def load_events(self, events: list[LogEvent]) -> None:
        self.clear_view()
        if not events:
            return
        matching = [e for e in events if self.service_name is None or e.service == self.service_name]
        if self._max_lines and len(matching) > self._max_lines:
            matching = matching[-self._max_lines:]
        lines = [
            f"{e.timestamp.strftime('%H:%M:%S')}{'!' if e.stream == 'stderr' else ' '} {e.message}"
            for e in matching
        ]
        self.log_widget.write_lines(lines)

    def clear_view(self) -> None:
        self._pending.clear()
        self.log_widget.clear()

    def _flush_pending(self) -> None:
        if not self._pending:
            return
        pending = self._pending
        self._pending = []
        self.append_events(pending)
