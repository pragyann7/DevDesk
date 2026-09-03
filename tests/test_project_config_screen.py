"""Tests for ProjectConfigScreen editing, validation, saving, and reloading."""

from __future__ import annotations

from pathlib import Path

import pytest
from textual.app import App, ComposeResult
from textual.widgets import TextArea

from devdesk.app import DevDeskApp
from devdesk.core.project_manager import ProjectManager
from devdesk.models.project import Project
from devdesk.models.service import Service, ServiceState
from devdesk.ui.screens.project_switcher import ProjectConfigScreen
from devdesk.utils.paths import project_config_path


def _create_sample_project(path: Path, name: str = "demo") -> Project:
    config_dir = path / ".devdesk"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_file = config_dir / "config.toml"
    config_file.write_text(
        f"""[project]
name = "{name}"

[services.web]
command = ["python", "-m", "http.server"]
directory = "."
port = 8000
""",
        encoding="utf-8",
    )
    web_svc = Service(name="web", command=["python", "-m", "http.server"], directory=path, port=8000)
    return Project(name=name, path=path, services=[web_svc])


@pytest.mark.asyncio
async def test_project_config_screen_loads_and_edits_toml(tmp_path: Path) -> None:
    project = _create_sample_project(tmp_path, "sample_app")

    class TestApp(App[bool | None]):
        def compose(self) -> ComposeResult:
            return []

    app = TestApp()
    async with app.run_test() as pilot:
        screen = ProjectConfigScreen(project)
        await app.push_screen(screen)
        await pilot.pause()

        editor = screen.query_one("#config-editor", TextArea)
        assert 'name = "sample_app"' in editor.text
        assert "[services.web]" in editor.text

        # 1. Test invalid TOML syntax rejection
        editor.text = "this is not valid toml = = ="
        screen.action_save()
        await pilot.pause()
        # File on disk should not have changed
        assert "this is not valid toml" not in project_config_path(tmp_path).read_text()

        # 2. Test valid update
        updated_toml = """[project]
name = "updated_app"

[services.web]
command = ["python", "-m", "http.server"]
directory = "."
port = 8080

[services.worker]
command = ["celery", "worker"]
directory = "."
"""
        editor.text = updated_toml
        screen.action_save()
        await pilot.pause()

        # Check saved to disk
        saved = project_config_path(tmp_path).read_text(encoding="utf-8")
        assert 'name = "updated_app"' in saved
        assert "services.worker" in saved


@pytest.mark.asyncio
async def test_devdesk_app_reloads_project_on_save(tmp_path: Path) -> None:
    project = _create_sample_project(tmp_path, "hotreload_app")

    app = DevDeskApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.project_manager.open(tmp_path)
        app.service_manager.attach_project(app.project_manager.current)
        app._sync_project_ui()

        # Simulate service 'web' was running
        web_service = app.service_manager.get("web")
        assert web_service is not None
        web_service.state = ServiceState.RUNNING
        web_service.pid = 9999

        # Now edit file on disk and call _reload_current_project
        new_toml = """[project]
name = "hotreload_app"

[services.web]
command = ["python", "-m", "http.server"]
directory = "."
port = 8080

[services.api]
command = ["uvicorn", "main:app"]
directory = "."
port = 5000
"""
        project_config_path(tmp_path).write_text(new_toml, encoding="utf-8")

        app._reload_current_project()
        await pilot.pause()

        # Verify services updated
        services = {s.name: s for s in app.service_manager.services()}
        assert "web" in services
        assert "api" in services
        assert services["api"].port == 5000
        # Check running state was preserved for web
        assert services["web"].state == ServiceState.RUNNING
        assert services["web"].pid == 9999
