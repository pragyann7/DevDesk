"""Service lifecycle, failures, and bounded log buffers."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from devdesk.core.log_manager import LogManager
from devdesk.core.process_manager import ProcessManager
from devdesk.core.service_manager import ServiceManager
from devdesk.models.project import Project
from devdesk.models.service import Service, ServiceState
from tests.test_process_manager import FakeProcess


def _project(tmp_path: Path, *names: str) -> Project:
    services = [
        Service(name=name, command=["demo", name], directory=tmp_path) for name in names
    ]
    return Project(name="demo", path=tmp_path, services=services)


@pytest.mark.asyncio
async def test_start_and_stop_service(tmp_path: Path) -> None:
    spawned: list[FakeProcess] = []

    async def factory(*_args, **_kwargs):
        process = FakeProcess([b"ready\n"], [], pid=99, exit_code=0)
        spawned.append(process)
        return process

    manager = ServiceManager(ProcessManager(subprocess_factory=factory))
    project = _project(tmp_path, "api")
    manager.attach_project(project)
    await manager.start("api")
    await asyncio.sleep(0.05)
    service = manager.get("api")
    assert service is not None
    assert service.state == ServiceState.RUNNING
    assert service.pid == 99
    await manager.stop("api")
    assert service.state == ServiceState.STOPPED
    assert manager.logs.get("api")[0].message == "ready"


@pytest.mark.asyncio
async def test_unexpected_exit_marks_failed(tmp_path: Path) -> None:
    async def factory(*_args, **_kwargs):
        process = FakeProcess([], [], pid=3, exit_code=1)
        process.finish()
        return process

    manager = ServiceManager(ProcessManager(subprocess_factory=factory))
    manager.attach_project(_project(tmp_path, "web"))
    await manager.start("web")
    await asyncio.sleep(0.05)
    service = manager.get("web")
    assert service is not None
    assert service.state == ServiceState.FAILED
    assert service.exit_code == 1


@pytest.mark.asyncio
async def test_start_all_and_restart(tmp_path: Path) -> None:
    spawned: list[FakeProcess] = []

    async def factory(*_args, **_kwargs):
        process = FakeProcess([], [], pid=10 + len(spawned), exit_code=0)
        spawned.append(process)
        return process

    manager = ServiceManager(ProcessManager(subprocess_factory=factory))
    manager.attach_project(_project(tmp_path, "a", "b"))
    await manager.start_all()
    await asyncio.sleep(0.05)
    assert [item.state for item in manager.services()] == [ServiceState.RUNNING, ServiceState.RUNNING]
    await manager.restart("a")
    assert len(spawned) == 3


def test_bounded_log_buffer() -> None:
    logs = LogManager(limit=3)
    for index in range(5):
        logs.add("api", f"line-{index}")
    messages = [event.message for event in logs.get("api")]
    assert messages == ["line-2", "line-3", "line-4"]
    logs.set_limit(2)
    assert [event.message for event in logs.get("api")] == ["line-3", "line-4"]
    logs.clear("api")
    assert logs.get("api") == []


def test_logs_are_not_merged_across_services() -> None:
    logs = LogManager(limit=10)
    logs.add("frontend", "ui ready")
    logs.add("backend", "listening")
    assert [event.message for event in logs.get("frontend")] == ["ui ready"]
    assert [event.message for event in logs.get("backend")] == ["listening"]


def test_api_monitor_parses_without_inventing() -> None:
    from devdesk.api.monitor import ApiMonitor, parse_api_line

    assert parse_api_line("not a request") is None
    assert parse_api_line('127.0.0.1:1 - "GET /api/restaurants/ HTTP/1.1" 200')["endpoint"] == "/api/restaurants/"
    django = parse_api_line('[03/Sep/2026 11:47:00] "GET /api/menu/12/ HTTP/1.1" 200 31')
    assert django is not None
    assert django["method"] == "GET"
    assert django["endpoint"] == "/api/menu/12/"
    assert django["status"] == 200
    monitor = ApiMonitor()
    assert monitor.ingest_line("api", "hello") is None
    record = monitor.ingest_line("api", "GET /login 401 76ms")
    assert record is not None
    assert record.method == "GET"
    assert record.status == 401
    assert record.duration_ms == 76

    def custom(line: str):
        if "GRAPHQL" in line:
            return {"method": "POST", "endpoint": "/graphql", "status": 200, "duration_ms": 12.0}
        return None

    monitor.add_parser(custom)
    custom_record = monitor.ingest_line("api", "GRAPHQL ok")
    assert custom_record is not None
    assert custom_record.endpoint == "/graphql"
