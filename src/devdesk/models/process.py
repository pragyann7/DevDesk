"""Runtime process information, kept separate from service configuration."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


@dataclass
class ProcessInfo:
    service_name: str
    pid: int
    command: list[str]
    cwd: Path
    started_at: datetime = field(default_factory=datetime.now)
    returncode: int | None = None

    @property
    def alive(self) -> bool:
        return self.returncode is None
