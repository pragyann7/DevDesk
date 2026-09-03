"""Service-level lifecycle on top of ProcessManager."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime

from devdesk.core.log_manager import LogManager
from devdesk.core.process_manager import ProcessManager, StreamName
from devdesk.models.project import Project
from devdesk.models.service import Service, ServiceState

StateCallback = Callable[[Service], None]
LogCallback = Callable[[str, StreamName, str, datetime], None]
ErrorCallback = Callable[[Service, str], None]


class ServiceManager:
    """Operate on named services rather than raw processes."""

    def __init__(
        self,
        process_manager: ProcessManager | None = None,
        log_manager: LogManager | None = None,
    ) -> None:
        self.processes = process_manager or ProcessManager()
        self.logs = log_manager or LogManager()
        self._project: Project | None = None
        self._on_state: StateCallback | None = None
        self._on_log: LogCallback | None = None
        self._on_error: ErrorCallback | None = None
        self._expected_stops: set[str] = set()
        self.processes.set_listeners(
            on_output=self._handle_output,
            on_exit=self._handle_exit,
            on_started=self._handle_started,
            on_failed=self._handle_failed,
        )

    def set_listeners(
        self,
        *,
        on_state: StateCallback | None = None,
        on_log: LogCallback | None = None,
        on_error: ErrorCallback | None = None,
    ) -> None:
        self._on_state = on_state
        self._on_log = on_log
        self._on_error = on_error

    @property
    def project(self) -> Project | None:
        return self._project

    def attach_project(self, project: Project | None) -> None:
        self._project = project
        self._expected_stops.clear()

    def get(self, name: str) -> Service | None:
        if self._project is None:
            return None
        return self._project.service(name)

    def services(self) -> list[Service]:
        if self._project is None:
            return []
        return list(self._project.services)

    async def start(self, service: Service | str) -> None:
        target = self._resolve(service)
        if target.is_active:
            return
        if not target.directory.is_dir():
            reason = f"Invalid working directory: {target.directory}"
            target.mark_failed(reason)
            self._emit_state(target)
            self._emit_error(target, reason)
            return
        target.mark_starting()
        self._emit_state(target)
        try:
            await self.processes.start(target.name, target.command, target.directory)
        except Exception as exc:  # noqa: BLE001 — surface startup failures to the UI
            if target.state != ServiceState.FAILED:
                target.mark_failed(str(exc))
                self._emit_state(target)
                self._emit_error(target, str(exc))

    async def stop(self, service: Service | str) -> None:
        target = self._resolve(service)
        if not self.processes.is_running(target.name) and target.state == ServiceState.STOPPED:
            return
        self._expected_stops.add(target.name)
        target.mark_stopping()
        self._emit_state(target)
        try:
            code = await self.processes.stop(target.name)
        except Exception as exc:  # noqa: BLE001
            self._expected_stops.discard(target.name)
            target.mark_failed(f"Failed to stop process: {exc}")
            self._emit_state(target)
            self._emit_error(target, str(exc))
            return
        if target.state == ServiceState.STOPPING:
            target.mark_stopped(code if code is not None else 0)
            self._emit_state(target)

    async def restart(self, service: Service | str) -> None:
        target = self._resolve(service)
        if self.processes.is_running(target.name) or target.is_active:
            await self.stop(target)
        await self.start(target)

    async def start_all(self) -> None:
        await asyncio.gather(*(self.start(service) for service in self.services()))

    async def stop_all(self) -> None:
        await asyncio.gather(*(self.stop(service) for service in self.services()))

    async def restart_all(self) -> None:
        await self.stop_all()
        await self.start_all()

    async def start_configured(self) -> None:
        auto = [service for service in self.services() if service.auto_start]
        if auto:
            await asyncio.gather(*(self.start(service) for service in auto))

    def _resolve(self, service: Service | str) -> Service:
        if isinstance(service, Service):
            return service
        found = self.get(service)
        if found is None:
            raise KeyError(f"Unknown service: {service}")
        return found

    def _handle_output(
        self,
        name: str,
        stream: StreamName,
        line: str,
        timestamp: datetime,
    ) -> None:
        self.logs.add(name, line, stream=stream, timestamp=timestamp)
        if self._on_log:
            self._on_log(name, stream, line, timestamp)
        service = self.get(name)
        if service and service.state == ServiceState.FAILED:
            return
        lowered = line.lower()
        if service and ("address already in use" in lowered or "port is already allocated" in lowered):
            service.last_error = f"Port appears to be already in use ({line.strip()})"

    def _handle_started(self, name: str, pid: int) -> None:
        service = self.get(name)
        if service is None:
            return
        service.mark_running(pid)
        self._emit_state(service)

    def _handle_exit(self, name: str, returncode: int) -> None:
        service = self.get(name)
        if service is None:
            return
        expected = name in self._expected_stops
        self._expected_stops.discard(name)
        if expected or returncode == 0:
            service.mark_stopped(returncode)
        else:
            reason = f"Process exited unexpectedly with code {returncode}."
            service.mark_failed(reason, exit_code=returncode)
            self._emit_error(service, reason)
        self._emit_state(service)

    def _handle_failed(self, name: str, message: str) -> None:
        service = self.get(name)
        if service is None:
            return
        service.mark_failed(message)
        self._emit_state(service)
        self._emit_error(service, message)

    def _emit_state(self, service: Service) -> None:
        if self._on_state:
            self._on_state(service)

    def _emit_error(self, service: Service, message: str) -> None:
        if self._on_error:
            self._on_error(service, message)
