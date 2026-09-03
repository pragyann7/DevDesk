"""API request table populated only from parsed service output."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Static

from devdesk.api.monitor import ApiRequest


class ApiRequestDetailScreen(ModalScreen[None]):
    BINDINGS = [("escape", "close", "Close")]

    def __init__(self, request: ApiRequest) -> None:
        super().__init__()
        self.request = request

    def compose(self) -> ComposeResult:
        item = self.request
        duration = f"{item.duration_ms:.0f}ms" if item.duration_ms is not None else "—"
        status = "—" if item.status is None else str(item.status)
        with Vertical():
            yield Static("Request details", classes="error-title")
            yield Static(f"Time     {item.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
            yield Static(f"Service  {item.service}")
            yield Static(f"Method   {item.method}")
            yield Static(f"Endpoint {item.endpoint}")
            yield Static(f"Status   {status}")
            yield Static(f"Duration {duration}")
            yield Static("Raw log line", classes="muted")
            yield Static(item.raw)
            yield Button("Close", id="close", variant="primary")

    def action_close(self) -> None:
        self.dismiss(None)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "close":
            self.dismiss(None)


class ApiMonitorView(Vertical):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._rows: dict[object, ApiRequest] = {}

    def compose(self):
        yield Static(
            "API Monitor  ·  Enter a row for details  ·  rows appear only from service output",
            classes="muted",
        )
        yield DataTable(id="api-table", cursor_type="row", zebra_stripes=True)

    def on_mount(self) -> None:
        table = self.query_one("#api-table", DataTable)
        table.add_columns("TIME", "SERVICE", "METHOD", "ENDPOINT", "STATUS", "DURATION")
        self._rows: dict[object, ApiRequest] = {}

    def replace_rows(self, requests: list[ApiRequest]) -> None:
        table = self.query_one("#api-table", DataTable)
        table.clear()
        self._rows = {}
        for item in reversed(requests[-200:]):
            duration = f"{item.duration_ms:.0f}ms" if item.duration_ms is not None else ""
            status = "" if item.status is None else str(item.status)
            key = table.add_row(
                item.timestamp.strftime("%H:%M:%S"),
                item.service,
                item.method,
                item.endpoint,
                status,
                duration,
            )
            self._rows[key] = item

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        request = self._rows.get(event.row_key)
        if request is not None:
            self.app.push_screen(ApiRequestDetailScreen(request))
