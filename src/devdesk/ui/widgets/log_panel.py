"""Reusable live log widget. One instance per service; buffers stay in LogManager."""

from __future__ import annotations

import re
from collections.abc import Iterable

from rich.style import Style
from textual.containers import Vertical
from textual.geometry import Size
from textual.strip import Strip
from textual.widgets import Log

from devdesk.core.log_manager import LogEvent
from devdesk.models.service import Service
from devdesk.ui.widgets.service_header import ServiceHeader

_ERROR_LOG_RE = re.compile(
    r"(?:\b[45]\d{2}\b|\b(?:\w*error|\w*exception|fatal|critical|traceback|failed)\b)",
    re.IGNORECASE,
)


class SmoothLog(Log):
    """Textual Log widget optimized for high-throughput live streams.

    Disables background thread pool worker size calculations that trigger
    delayed width callbacks, horizontal scrollbar pops, and visual jitter.
    Guarantees steady, non-bouncing auto-scrolling pinned to the latest output.
    Highlights the latest log line with a distinct accent background and bold typography.
    """

    def _update_size(self, updates: int, lines: list[str]) -> None:
        # Avoid spawning thread pool workers that fire delayed asynchronous
        # callbacks modifying virtual width and causing horizontal jitter.
        pass

    def _render_line(self, y: int, scroll_x: int, width: int) -> Strip:
        rich_style = self.rich_style
        if y >= len(self._lines):
            return Strip.blank(width, rich_style)

        is_latest = (y == 0)
        if is_latest:
            line_str = self._lines[y]
            is_error = bool(_ERROR_LOG_RE.search(line_str))
            if is_error:
                style = Style(color="#ff7b72", bold=True, bgcolor="#321418")
            else:
                style = Style(color="#f0f6fc", bold=True, bgcolor="#173151")
            line = self._render_line_strip(y, style)
            assert line._cell_length is not None
            line = line.crop_extend(scroll_x, scroll_x + width, style)
        else:
            line = self._render_line_strip(y, rich_style)
            assert line._cell_length is not None
            line = line.crop_extend(scroll_x, scroll_x + width, rich_style)

        line = line.apply_offsets(scroll_x, y)
        return line

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

        # Newest logs at the top (reverse-chronological, latest stays above)
        self._lines = list(reversed(new_lines)) + self._lines
        if self.max_lines is not None and len(self._lines) > self.max_lines:
            self._lines = self._lines[:self.max_lines]

        width = self.size.width if self.size.width > 0 else 80
        self.virtual_size = Size(width, len(self._lines))
        self.refresh()

        user_scrolled_away = self.scroll_y > 0
        if auto_scroll and not self.is_vertical_scrollbar_grabbed and not user_scrolled_away:
            self.scroll_to(y=0, animate=False)
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
