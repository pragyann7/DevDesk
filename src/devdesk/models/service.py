"""Service configuration plus mutable runtime status."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path


class ServiceState(str, Enum):
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    STOPPING = "STOPPING"
    STOPPED = "STOPPED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


ACTIVE_STATES = frozenset(
    {ServiceState.STARTING, ServiceState.RUNNING, ServiceState.STOPPING}
)


@dataclass
class Service:
    name: str
    command: list[str]
    directory: Path
    port: int | None = None
    auto_start: bool = False
    state: ServiceState = ServiceState.STOPPED
    pid: int | None = None
    started_at: datetime | None = None
    exit_code: int | None = None
    last_error: str | None = None
    extra: dict[str, object] = field(default_factory=dict)

    def mark_starting(self) -> None:
        self.state = ServiceState.STARTING
        self.exit_code = None
        self.last_error = None

    def mark_running(self, pid: int) -> None:
        self.state = ServiceState.RUNNING
        self.pid = pid
        self.started_at = datetime.now()
        self.exit_code = None
        self.last_error = None

    def mark_stopping(self) -> None:
        self.state = ServiceState.STOPPING

    def mark_stopped(self, exit_code: int | None = 0) -> None:
        self.state = ServiceState.STOPPED
        self.pid = None
        self.started_at = None
        self.exit_code = exit_code

    def mark_failed(self, reason: str, exit_code: int | None = None) -> None:
        self.state = ServiceState.FAILED
        self.pid = None
        self.started_at = None
        self.last_error = reason
        self.exit_code = exit_code

    @property
    def is_active(self) -> bool:
        return self.state in ACTIVE_STATES
