"""Filesystem locations used by DevDesk."""

from __future__ import annotations

import os
from pathlib import Path

CONFIG_DIR_NAME = ".devdesk"
CONFIG_FILE_NAME = "config.toml"


def project_config_path(project_root: Path) -> Path:
    return Path(project_root).expanduser().resolve() / CONFIG_DIR_NAME / CONFIG_FILE_NAME


def app_config_dir() -> Path:
    override = os.environ.get("DEVDESK_HOME")
    if override:
        return Path(override).expanduser().resolve()
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg).expanduser().resolve() / "devdesk"
    return Path.home() / ".config" / "devdesk"


def settings_path() -> Path:
    return app_config_dir() / "settings.toml"


def recent_projects_path() -> Path:
    return app_config_dir() / "recent.toml"


def ensure_app_config_dir() -> Path:
    directory = app_config_dir()
    directory.mkdir(parents=True, exist_ok=True)
    return directory
