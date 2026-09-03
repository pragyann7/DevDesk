"""API request table populated only from parsed service output."""

from __future__ import annotations

import asyncio
import json
import urllib.request

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Static

from devdesk.api.monitor import ApiRequest


class ApiRequestDetailScreen(ModalScreen[None]):
    BINDINGS = [
        ("escape", "close", "Close"),
        ("f", "fetch_response", "Fetch Response"),
    ]

    def __init__(self, request: ApiRequest, service_port: int | None = None) -> None:
        super().__init__()
        self.request = request
        self.service_port = service_port

    def compose(self) -> ComposeResult:
        item = self.request
        duration = f"{item.duration_ms:.0f}ms" if item.duration_ms is not None else "—"
        status = "—" if item.status is None else str(item.status)
        is_get_or_safe = item.method.upper() in {"GET", "HEAD", "OPTIONS"}
        with Vertical(id="api-detail-modal"):
            with VerticalScroll():
                yield Static("Request Details", classes="error-title")
                yield Static(f"Time     {item.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
                yield Static(f"Service  {item.service}")
                yield Static(f"Method   {item.method}")
                yield Static(f"Endpoint {item.endpoint}")
                yield Static(f"Status   {status}")
                yield Static(f"Duration {duration}")

                # Query parameters (crucial for GET requests!)
                if item.query_params:
                    yield Static("Query Parameters (GET Data)", classes="body-label")
                    yield Static(json.dumps(item.query_params, indent=2), classes="body-content")

                # Request Body (what client sent to server)
                yield Static("Request Body (Sent by client)", classes="body-label")
                if item.request_body:
                    yield Static(item.request_body, classes="body-content")
                elif is_get_or_safe:
                    yield Static(
                        "(N/A — HTTP GET requests do not send a payload body. Request parameters are in the URL query string above.)",
                        classes="muted",
                    )
                else:
                    yield Static("(No request payload found in service logs)", classes="muted")

                # Response Body (what server returned to client)
                yield Static("Response Body (Returned by server)", classes="body-label")
                if item.response_body:
                    yield Static(item.response_body, id="response-body-content", classes="body-content")
                else:
                    msg = (
                        "(No response payload captured in logs.\n"
                        "Click [Fetch Live Response] below or press 'f' to query the server directly.)"
                    )
                    yield Static(msg, id="response-body-content", classes="muted")

                yield Static("Raw log line", classes="muted")
                yield Static(item.raw)

            with Horizontal(id="api-detail-actions"):
                if is_get_or_safe:
                    yield Button("Fetch Live Response (f)", id="btn-fetch-response", variant="success")
                yield Button("Close (Esc)", id="close", variant="primary")

    def action_close(self) -> None:
        self.dismiss(None)

    def action_fetch_response(self) -> None:
        if self.request.method.upper() in {"GET", "HEAD", "OPTIONS"}:
            self.run_worker(self._fetch_live_response(), exclusive=True)

    async def _fetch_live_response(self) -> None:
        port = self.service_port or 8000
        url = f"http://127.0.0.1:{port}{self.request.endpoint}"
        status_widget = self.query_one("#response-body-content", Static)
        status_widget.update(f"Fetching from {url}...")

        def _do_fetch() -> str:
            req = urllib.request.Request(
                url,
                headers={"Accept": "application/json", "User-Agent": "DevDesk-Monitor/1.0"},
            )
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                data = resp.read().decode("utf-8", errors="replace")
                try:
                    return json.dumps(json.loads(data), indent=2)
                except Exception:
                    return data

        try:
            body = await asyncio.to_thread(_do_fetch)
            self.request.response_body = body
            status_widget.remove_class("muted")
            status_widget.add_class("body-content")
            status_widget.update(body)
            self.notify("Live response fetched successfully!")
        except Exception as exc:
            status_widget.update(f"Could not connect to {url}:\n{exc}")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "close":
            self.dismiss(None)
        elif event.button.id == "btn-fetch-response":
            self.action_fetch_response()


class ApiMonitorView(Vertical):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._rows: dict[object, ApiRequest] = {}
        self._table: DataTable | None = None

    def compose(self):
        yield Static(
            "API Monitor  ·  Enter a row for details  ·  rows appear only from service output",
            classes="muted",
        )
        yield DataTable(id="api-table", cursor_type="row", zebra_stripes=True)

    def on_mount(self) -> None:
        self._table = self.query_one("#api-table", DataTable)
        self._table.add_columns("TIME", "SERVICE", "METHOD", "ENDPOINT", "STATUS", "DURATION", "DATA")
        self._rows = {}

    @property
    def table_widget(self) -> DataTable:
        if self._table is None:
            self._table = self.query_one("#api-table", DataTable)
        return self._table

    def replace_rows(self, requests: list[ApiRequest]) -> None:
        table = self.table_widget
        table.clear()
        self._rows = {}
        for item in reversed(requests[-200:]):
            duration = f"{item.duration_ms:.0f}ms" if item.duration_ms is not None else ""
            status = "" if item.status is None else str(item.status)
            if item.request_body and item.response_body:
                data_indicator = "req+res"
            elif item.request_body:
                data_indicator = "req"
            elif item.response_body:
                data_indicator = "res"
            elif item.query_params:
                data_indicator = "params"
            else:
                data_indicator = "—"
            key = table.add_row(
                item.timestamp.strftime("%H:%M:%S"),
                item.service,
                item.method,
                item.endpoint,
                status,
                duration,
                data_indicator,
            )
            self._rows[key] = item

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        request = self._rows.get(event.row_key)
        if request is not None:
            port = None
            if hasattr(self.app, "service_manager"):
                svc = self.app.service_manager.get(request.service)
                if svc and svc.port:
                    port = svc.port
            self.app.push_screen(ApiRequestDetailScreen(request, service_port=port))
