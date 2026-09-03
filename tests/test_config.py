"""Configuration loading and validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from devdesk.config.loader import load_project
from devdesk.config.schema import ConfigError, validate_project_config


def _write_config(root: Path, body: str) -> Path:
    config_dir = root / ".devdesk"
    config_dir.mkdir(parents=True)
    path = config_dir / "config.toml"
    path.write_text(body, encoding="utf-8")
    return root


def test_load_valid_project(tmp_path: Path) -> None:
    _write_config(
        tmp_path,
        """
[project]
name = "Demo"

[services.api]
command = ["uvicorn", "main:app"]
directory = "./api"
port = 8000

[services.web]
command = ["npm", "run", "dev"]
directory = "./web"
port = 3000
""",
    )
    (tmp_path / "api").mkdir()
    (tmp_path / "web").mkdir()
    project = load_project(tmp_path)
    assert project.name == "Demo"
    assert project.path == tmp_path.resolve()
    assert project.service_names() == ["api", "web"]
    api = project.service("api")
    assert api is not None
    assert api.command == ["uvicorn", "main:app"]
    assert api.port == 8000
    assert api.directory == (tmp_path / "api").resolve()


def test_missing_config(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="No DevDesk configuration"):
        load_project(tmp_path)


def test_invalid_toml(tmp_path: Path) -> None:
    _write_config(tmp_path, "[project\nname = ")
    with pytest.raises(ConfigError, match="Invalid TOML"):
        load_project(tmp_path)


def test_missing_project_name() -> None:
    with pytest.raises(ConfigError, match=r"\[project\]\.name"):
        validate_project_config({"project": {}, "services": {"api": {"command": ["true"]}}})


def test_command_must_be_string_array() -> None:
    with pytest.raises(ConfigError, match="command"):
        validate_project_config(
            {
                "project": {"name": "x"},
                "services": {"api": {"command": "uvicorn main:app"}},
            }
        )


def test_invalid_port() -> None:
    with pytest.raises(ConfigError, match="port"):
        validate_project_config(
            {
                "project": {"name": "x"},
                "services": {"api": {"command": ["true"], "port": 99999}},
            }
        )


def test_requires_at_least_one_service() -> None:
    with pytest.raises(ConfigError, match="At least one"):
        validate_project_config({"project": {"name": "x"}, "services": {}})
