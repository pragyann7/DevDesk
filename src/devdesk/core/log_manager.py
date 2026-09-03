"""Bounded per-service log buffers."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

StreamName = Literal["stdout", "stderr"]

DEFAULT_BUFFER_SIZE = 2000


@dataclass(frozen=True)
class LogEvent:
    timestamp: datetime
    service: str
    stream: StreamName
    message: str


class LogManager:
    """Keep a bounded, independent buffer for every service."""

    def __init__(self, limit: int = DEFAULT_BUFFER_SIZE) -> None:
        if limit < 1:
            raise ValueError("Log buffer limit must be at least 1.")
        self._limit = limit
        self._buffers: dict[str, deque[LogEvent]] = {}

    @property
    def limit(self) -> int:
        return self._limit

    def set_limit(self, limit: int) -> None:
        if limit < 1:
            raise ValueError("Log buffer limit must be at least 1.")
        self._limit = limit
        rebuilt: dict[str, deque[LogEvent]] = {}
        for name, buffer in self._buffers.items():
            rebuilt[name] = deque(buffer, maxlen=limit)
        self._buffers = rebuilt

    def append(self, event: LogEvent) -> LogEvent:
        buffer = self._buffers.get(event.service)
        if buffer is None or buffer.maxlen != self._limit:
            existing = list(buffer) if buffer is not None else []
            buffer = deque(existing, maxlen=self._limit)
            self._buffers[event.service] = buffer
        buffer.append(event)
        return event

    def add(
        self,
        service: str,
        message: str,
        stream: StreamName = "stdout",
        timestamp: datetime | None = None,
    ) -> LogEvent:
        return self.append(
            LogEvent(
                timestamp=timestamp or datetime.now(),
                service=service,
                stream=stream,
                message=message,
            )
        )

    def get(self, service: str) -> list[LogEvent]:
        buffer = self._buffers.get(service)
        return list(buffer) if buffer is not None else []

    def clear(self, service: str) -> None:
        self._buffers.pop(service, None)

    def clear_all(self) -> None:
        self._buffers.clear()
