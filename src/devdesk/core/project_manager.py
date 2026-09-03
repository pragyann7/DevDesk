"""Discover, load, and switch projects."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from devdesk.config.loader import load_project, load_recent_projects, save_recent_projects
from devdesk.config.schema import ConfigError
from devdesk.models.project import Project
from devdesk.utils.paths import project_config_path


class ProjectManager:
    """Owns the current project and the recent-project list."""

    def __init__(
        self,
        *,
        loader: Callable[[Path], Project] = load_project,
        recent_loader: Callable[[], list[Path]] = load_recent_projects,
        recent_saver: Callable[[list[Path]], None] = save_recent_projects,
    ) -> None:
        self._loader = loader
        self._recent_loader = recent_loader
        self._recent_saver = recent_saver
        self._current: Project | None = None
        self._recent: list[Path] = [path.expanduser() for path in self._recent_loader()]

    @property
    def current(self) -> Project | None:
        return self._current

    @property
    def recent(self) -> list[Path]:
        return list(self._recent)

    def open(self, path: str | Path) -> Project:
        project = self._loader(Path(path))
        self._current = project
        self._remember(project.path)
        return project

    def close(self) -> None:
        self._current = None

    def discover(self, root: str | Path) -> list[Path]:
        base = Path(root).expanduser().resolve()
        found: list[Path] = []
        if not base.exists():
            return found
        if base.is_dir() and project_config_path(base).is_file():
            found.append(base)
        if not base.is_dir():
            return found
        try:
            children = list(base.iterdir())
        except OSError:
            return found
        for child in children:
            try:
                if child.is_dir() and project_config_path(child).is_file():
                    resolved = child.resolve()
                    if resolved not in found:
                        found.append(resolved)
            except OSError:
                continue
        return found

    def has_config(self, path: str | Path) -> bool:
        return project_config_path(Path(path)).is_file()

    def _remember(self, path: Path) -> None:
        resolved = path.expanduser().resolve()
        self._recent = [resolved, *[item for item in self._recent if item.resolve() != resolved]]
        try:
            self._recent_saver(self._recent)
        except OSError:
            # Recent-project persistence must never block opening a project.
            pass


def describe_open_error(exc: Exception) -> str:
    if isinstance(exc, ConfigError):
        return str(exc)
    return f"Unable to open project: {exc}"
