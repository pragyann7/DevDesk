"""Tests for Sidebar navigation, focus switching, and Esc back keybindings."""

from __future__ import annotations

from pathlib import Path

import pytest
from textual.widgets import TextArea

from devdesk.app import DevDeskApp
from devdesk.models.project import Project
from devdesk.models.service import Service
from devdesk.ui.screens.api_monitor import ApiMonitorView
from devdesk.ui.screens.project_switcher import ProjectConfigScreen
from devdesk.ui.widgets.log_panel import LogPanel
from devdesk.ui.widgets.sidebar import Sidebar


@pytest.mark.asyncio
async def test_esc_focuses_sidebar_and_toggles_back(tmp_path: Path) -> None:
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

        sidebar = app.query_one(Sidebar)
        top_panel = app.query_one("#panel-top", LogPanel)

        # 1. Focus log panel initially
        top_panel.focus()
        await pilot.pause()
        assert app.focused is top_panel

        # 2. Press Esc: moves focus to Sidebar
        await pilot.press("escape")
        await pilot.pause()
        assert app.focused is sidebar

        # 3. Press Esc again: toggles focus back to LogPanel
        await pilot.press("escape")
        await pilot.pause()
        assert app.focused is top_panel


@pytest.mark.asyncio
async def test_esc_from_subview_returns_to_dashboard_and_focuses_sidebar(tmp_path: Path) -> None:
    frontend = Service(name="frontend", command=["echo", "front"], directory=tmp_path)
    project = Project(name="test_proj", path=tmp_path, services=[frontend])

    app = DevDeskApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.project_manager._current = project
        app.service_manager.attach_project(project)
        app._sync_project_ui()
        await pilot.pause()

        sidebar = app.query_one(Sidebar)

        # Switch to api_monitor
        app._show_view("api_monitor")
        await pilot.pause()
        assert app.current_view == "api_monitor"

        # Press Esc: should return to dashboard and focus sidebar
        await pilot.press("escape")
        await pilot.pause()
        assert app.current_view == "dashboard"
        assert app.focused is sidebar


@pytest.mark.asyncio
async def test_sidebar_enter_focuses_view(tmp_path: Path) -> None:
    frontend = Service(name="frontend", command=["echo", "front"], directory=tmp_path)
    project = Project(name="test_proj", path=tmp_path, services=[frontend])

    app = DevDeskApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.project_manager._current = project
        app.service_manager.attach_project(project)
        app._sync_project_ui()
        await pilot.pause()

        sidebar = app.query_one(Sidebar)
        sidebar.focus()
        await pilot.pause()
        assert app.focused is sidebar

        # Highlight api_monitor and press Enter
        sidebar.highlight("api_monitor")
        await pilot.press("enter")
        await pilot.pause()

        assert app.current_view == "api_monitor"
        api_view = app.query_one(ApiMonitorView)
        assert app.focused is api_view.table_widget


@pytest.mark.asyncio
async def test_esc_closes_modal_screen(tmp_path: Path) -> None:
    project = Project(name="test_proj", path=tmp_path, services=[])

    app = DevDeskApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.project_manager._current = project

        modal = ProjectConfigScreen(project)
        await app.push_screen(modal)
        await pilot.pause()
        assert app.screen is modal

        # Press Esc should dismiss modal screen
        await pilot.press("escape")
        await pilot.pause()
        assert app.screen is not modal


@pytest.mark.asyncio
async def test_api_detail_modal_shows_and_fetches() -> None:
    from datetime import datetime
    from devdesk.api.monitor import ApiRequest
    from devdesk.ui.screens.api_monitor import ApiRequestDetailScreen

    req = ApiRequest(
        timestamp=datetime.now(),
        service="backend",
        method="GET",
        endpoint="/api/menu/restaurant/qwerty/",
        status=200,
        duration_ms=15.0,
        raw="GET /api/menu/restaurant/qwerty/ 200",
    )

    screen = ApiRequestDetailScreen(req, service_port=8000)
    app = DevDeskApp()
    async with app.run_test() as pilot:
        await app.push_screen(screen)
        await pilot.pause()

        # Check screen rendered properly
        assert app.screen is screen
        # Check fetch button exists for GET requests
        btn = screen.query_one("#btn-fetch-response")
        assert btn is not None

        # Esc closes modal
        await pilot.press("escape")
        await pilot.pause()
        assert app.screen is not screen
