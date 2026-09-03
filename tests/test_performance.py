"""Performance and responsiveness tests under high log volume."""

from __future__ import annotations

import asyncio
import time
from datetime import datetime
from pathlib import Path

import pytest
from textual.app import App, ComposeResult

from devdesk.api.monitor import parse_api_line
from devdesk.app import DevDeskApp
from devdesk.core.log_manager import LogEvent
from devdesk.models.project import Project
from devdesk.models.service import Service
from devdesk.ui.widgets.log_panel import LogPanel


def test_fast_api_parser_skips_non_http() -> None:
    # Non-HTTP lines should return None instantly
    assert parse_api_line("compiling frontend bundle 12/48...") is None
    assert parse_api_line("database connection pool initialized") is None
    assert parse_api_line("User pragyanshrestha authenticated") is None

    # HTTP lines should parse correctly
    res = parse_api_line('127.0.0.1 - - [03/Sep/2026] "GET /api/v1/health HTTP/1.1" 200 -')
    assert res is not None
    assert res["method"] == "GET"
    assert res["endpoint"] == "/api/v1/health"
    assert res["status"] == 200


@pytest.mark.asyncio
async def test_log_panel_max_lines_and_batch_write() -> None:
    class DummyApp(App):
        def compose(self) -> ComposeResult:
            yield LogPanel(service_name="api", max_lines=50)

    app = DummyApp()
    async with app.run_test() as pilot:
        panel = app.query_one(LogPanel)
        events = [
            LogEvent(datetime.now(), "api", "stdout", f"line {i}")
            for i in range(120)
        ]
        panel.load_events(events)
        assert panel.log_widget.line_count == 50


@pytest.mark.asyncio
async def test_high_throughput_multiservice_streaming(tmp_path: Path) -> None:
    """Ensure App can process thousands of concurrent lines from frontend and backend smoothly."""
    frontend = Service(name="frontend", command=["echo", "front"], directory=tmp_path)
    backend = Service(name="backend", command=["echo", "back"], directory=tmp_path)
    project = Project(name="test_proj", path=tmp_path, services=[frontend, backend])

    app = DevDeskApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.project_manager._current = project
        app.service_manager.attach_project(project)
        app._sync_project_ui()
        await pilot.pause()

        # Simulate 1000 lines from frontend and 1000 lines from backend via service manager output handler
        t0 = time.perf_counter()
        now = datetime.now()
        for i in range(1000):
            app.service_manager._handle_output("frontend", "stdout", f"frontend build chunk {i}", now)
            app.service_manager._handle_output("backend", "stdout", f'127.0.0.1 - "GET /api/data/{i} HTTP/1.1" 200', now)

        # Trigger flush
        app._flush_pending_logs()
        elapsed = time.perf_counter() - t0

        # Processing 2000 lines into pending buffer and flushing should be <250ms
        assert elapsed < 0.25, f"Flushing 2000 lines took too long: {elapsed:.3f}s"

        # Check that visible panels received lines immediately
        top_panel = app.query_one("#panel-top", LogPanel)
        bottom_panel = app.query_one("#panel-bottom", LogPanel)
        assert top_panel.log_widget.line_count > 0
        assert bottom_panel.log_widget.line_count > 0

        # Verify key press responds immediately without hang
        await pilot.press("right_square_bracket")
        await pilot.pause()
        await pilot.press("left_square_bracket")
        await pilot.pause()
        assert top_panel.log_widget.line_count > 0


@pytest.mark.asyncio
async def test_view_switching_loads_logs_instantly(tmp_path: Path) -> None:
    """Ensure switching views reloads visible logs in single-digit milliseconds."""
    frontend = Service(name="frontend", command=["echo", "front"], directory=tmp_path)
    project = Project(name="test_proj", path=tmp_path, services=[frontend])

    app = DevDeskApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.project_manager._current = project
        app.service_manager.attach_project(project)
        app._sync_project_ui()

        # Populate LogManager with 1000 lines
        now = datetime.now()
        for i in range(1000):
            app.log_manager.add("frontend", f"log line {i}", timestamp=now)

        t0 = time.perf_counter()
        app._show_view("frontend")
        await pilot.pause()
        switch_time = time.perf_counter() - t0

        # View switch should be well under 150ms
        assert switch_time < 0.15, f"View switch took too long: {switch_time:.3f}s"
        front_panel = app.query_one("#frontend-panel", LogPanel)
        assert front_panel.log_widget.line_count == 1000
