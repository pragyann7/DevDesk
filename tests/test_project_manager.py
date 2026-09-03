"""Project discovery, switching, and service creation from config."""

from __future__ import annotations

from pathlib import Path

import pytest

from devdesk.config.loader import load_project
from devdesk.core.project_manager import ProjectManager
from devdesk.models.project import Project
from devdesk.models.service import Service


def _project_dir(root: Path, name: str) -> Path:
    path = root / name
    config = path / ".devdesk"
    config.mkdir(parents=True)
    (config / "config.toml").write_text(
        f"""
[project]
name = "{name}"

[services.main]
command = ["true"]
directory = "."
""",
        encoding="utf-8",
    )
    return path


def test_discover_nested_projects(tmp_path: Path) -> None:
    one = _project_dir(tmp_path, "one")
    two = _project_dir(tmp_path, "two")
    (tmp_path / "ignored").mkdir()
    manager = ProjectManager(recent_loader=lambda: [], recent_saver=lambda _paths: None)
    found = {path.name for path in manager.discover(tmp_path)}
    assert found == {"one", "two"}
    assert one in manager.discover(tmp_path) or one.resolve() in manager.discover(tmp_path)
    assert two.resolve() in manager.discover(tmp_path)


def test_open_tracks_current_and_recent(tmp_path: Path) -> None:
    stored: list[Path] = []
    first = _project_dir(tmp_path, "alpha")
    second = _project_dir(tmp_path, "beta")
    manager = ProjectManager(recent_loader=lambda: [], recent_saver=stored.extend)
    project = manager.open(first)
    assert manager.current is not None
    assert project.name == "alpha"
    manager.open(second)
    assert manager.current is not None
    assert manager.current.name == "beta"
    assert manager.recent[0] == second.resolve()


def test_service_creation_from_config(tmp_path: Path) -> None:
    path = _project_dir(tmp_path, "gamma")
    project = load_project(path)
    assert isinstance(project, Project)
    assert len(project.services) == 1
    service = project.services[0]
    assert isinstance(service, Service)
    assert service.name == "main"
    assert service.command == ["true"]
    assert service.state.value == "STOPPED"


def test_display_pair_prefers_named_roles() -> None:
    services = [
        Service(name="api", command=["true"], directory=Path(".")),
        Service(name="web", command=["true"], directory=Path(".")),
        Service(name="worker", command=["true"], directory=Path(".")),
    ]
    project = Project(name="x", path=Path("."), services=services)
    top, bottom = project.display_pair()
    assert top is not None and top.name == "web"
    assert bottom is not None and bottom.name == "api"


def test_display_pair_offset_cycles_services() -> None:
    services = [
        Service(name="web", command=["true"], directory=Path(".")),
        Service(name="api", command=["true"], directory=Path(".")),
        Service(name="worker", command=["true"], directory=Path(".")),
    ]
    project = Project(name="x", path=Path("."), services=services)
    top, bottom = project.display_pair(1)
    assert top is not None and top.name == "api"
    assert bottom is not None and bottom.name == "worker"


def test_display_pair_single_backend() -> None:
    services = [
        Service(name="backend", command=["true"], directory=Path(".")),
    ]
    project = Project(name="x", path=Path("."), services=services)
    top, bottom = project.display_pair()
    assert top is None
    assert bottom is not None and bottom.name == "backend"


def test_open_missing_config(tmp_path: Path) -> None:
    manager = ProjectManager(recent_loader=lambda: [], recent_saver=lambda _paths: None)
    with pytest.raises(Exception):
        manager.open(tmp_path)


@pytest.mark.asyncio
async def test_app_launches() -> None:
    from devdesk.app import DevDeskApp

    app = DevDeskApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        assert "DEV DESK" in str(app.query_one("#chrome-title").render())
