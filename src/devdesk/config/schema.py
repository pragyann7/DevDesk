"""Validation for `.devdesk/config.toml` and application settings."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class ConfigError(Exception):
    """Raised when a configuration file is missing or invalid."""


@dataclass
class AppSettings:
    log_buffer_size: int = 2000
    auto_follow_logs: bool = True
    confirm_before_stop: bool = True
    default_project_directory: Path = field(default_factory=Path.home)
    auto_start_on_open: bool = False


def validate_project_config(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ConfigError("Configuration must be a TOML table.")

    project = data.get("project")
    if not isinstance(project, dict):
        raise ConfigError("Missing [project] table.")
    name = project.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ConfigError("[project].name is required and must be a non-empty string.")

    services = data.get("services")
    if not isinstance(services, dict) or not services:
        raise ConfigError("At least one [services.<name>] table is required.")

    for service_name, spec in services.items():
        prefix = f"[services.{service_name}]"
        if not isinstance(service_name, str) or not service_name.strip():
            raise ConfigError("Service names must be non-empty strings.")
        if not isinstance(spec, dict):
            raise ConfigError(f"{prefix} must be a table.")

        command = spec.get("command")
        if not isinstance(command, list) or not command:
            raise ConfigError(f"{prefix}.command must be a non-empty array of strings.")
        if not all(isinstance(part, str) and part for part in command):
            raise ConfigError(f"{prefix}.command entries must be non-empty strings.")

        directory = spec.get("directory", ".")
        if not isinstance(directory, str) or not directory.strip():
            raise ConfigError(f"{prefix}.directory must be a string path.")

        if "port" in spec and spec["port"] is not None:
            port = spec["port"]
            if not isinstance(port, int) or isinstance(port, bool) or not (1 <= port <= 65535):
                raise ConfigError(f"{prefix}.port must be an integer between 1 and 65535.")

        if "auto_start" in spec and not isinstance(spec["auto_start"], bool):
            raise ConfigError(f"{prefix}.auto_start must be a boolean.")

    return data


def settings_from_mapping(data: dict[str, Any] | None) -> AppSettings:
    raw = data or {}
    settings = AppSettings()

    size = raw.get("log_buffer_size", settings.log_buffer_size)
    if not isinstance(size, int) or isinstance(size, bool) or size < 50:
        raise ConfigError("log_buffer_size must be an integer >= 50.")
    settings.log_buffer_size = size

    for field_name in ("auto_follow_logs", "confirm_before_stop", "auto_start_on_open"):
        if field_name in raw and not isinstance(raw[field_name], bool):
            raise ConfigError(f"{field_name} must be a boolean.")
        if field_name in raw:
            setattr(settings, field_name, raw[field_name])

    directory = raw.get("default_project_directory")
    if directory is not None:
        if not isinstance(directory, str) or not directory.strip():
            raise ConfigError("default_project_directory must be a string path.")
        settings.default_project_directory = Path(directory).expanduser()

    return settings
