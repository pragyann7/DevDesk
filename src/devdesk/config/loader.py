"""Load project configuration and application settings from TOML."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from devdesk.config.schema import (
    AppSettings,
    ConfigError,
    settings_from_mapping,
    validate_project_config,
)
from devdesk.models.project import Project
from devdesk.models.service import Service
from devdesk.utils.paths import (
    ensure_app_config_dir,
    project_config_path,
    recent_projects_path,
    settings_path,
)


def _read_toml(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except FileNotFoundError as exc:
        raise ConfigError(f"Configuration file not found: {path}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"Invalid TOML in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"Configuration in {path} must be a TOML table.")
    return data


def load_project(project_root: str | Path) -> Project:
    root = Path(project_root).expanduser().resolve()
    config_file = project_config_path(root)
    if not config_file.is_file():
        raise ConfigError(
            f"No DevDesk configuration found at {config_file}. "
            "Create .devdesk/config.toml in the project root."
        )
    data = validate_project_config(_read_toml(config_file))
    project_name = str(data["project"]["name"]).strip()
    services: list[Service] = []
    for name, spec in data["services"].items():
        relative = Path(str(spec.get("directory", ".")))
        working_dir = relative if relative.is_absolute() else (root / relative)
        services.append(
            Service(
                name=name,
                command=list(spec["command"]),
                directory=working_dir.resolve(),
                port=spec.get("port"),
                auto_start=bool(spec.get("auto_start", False)),
            )
        )
    return Project(name=project_name, path=root, services=services)


def load_settings() -> AppSettings:
    path = settings_path()
    if not path.is_file():
        return AppSettings()
    return settings_from_mapping(_read_toml(path))


def save_settings(settings: AppSettings) -> None:
    ensure_app_config_dir()
    path = settings_path()
    body = (
        f"log_buffer_size = {settings.log_buffer_size}\n"
        f"auto_follow_logs = {'true' if settings.auto_follow_logs else 'false'}\n"
        f"confirm_before_stop = {'true' if settings.confirm_before_stop else 'false'}\n"
        f"auto_start_on_open = {'true' if settings.auto_start_on_open else 'false'}\n"
        f'default_project_directory = "{_escape(str(settings.default_project_directory))}"\n'
    )
    path.write_text(body, encoding="utf-8")


def load_recent_projects() -> list[Path]:
    path = recent_projects_path()
    if not path.is_file():
        return []
    data = _read_toml(path)
    raw = data.get("paths", [])
    if not isinstance(raw, list):
        return []
    result: list[Path] = []
    for item in raw:
        if isinstance(item, str) and item.strip():
            result.append(Path(item).expanduser())
    return result


def save_recent_projects(paths: list[Path], *, limit: int = 12) -> None:
    ensure_app_config_dir()
    unique: list[Path] = []
    seen: set[Path] = set()
    for item in paths:
        resolved = item.expanduser().resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(resolved)
        if len(unique) >= limit:
            break
    lines = ["paths = ["]
    for item in unique:
        lines.append(f'    "{_escape(str(item))}",')
    lines.append("]\n")
    recent_projects_path().write_text("\n".join(lines), encoding="utf-8")


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')
