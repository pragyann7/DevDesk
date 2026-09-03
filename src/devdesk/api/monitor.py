"""Parse API request lines from generic service output."""

from __future__ import annotations

import re
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from devdesk.core.log_manager import LogEvent

_METHODS = r"GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS"
Parser = Callable[[str], dict[str, Any] | None]

# Uvicorn / Hypercorn / Django: "GET /path HTTP/1.1" 200
_QUOTED_HTTP = re.compile(
    rf'"(?P<method>{_METHODS})\s+(?P<path>\S+)\s+HTTP/[\d.]+"\s+(?P<status>\d{{3}})'
    rf"(?:\s+(?P<bytes>\d+))?(?:\s+(?P<duration>[\d.]+)\s*(?P<unit>ms|s))?",
    re.IGNORECASE,
)

# Common access log: GET /path HTTP/1.1 200
_HTTP_LINE = re.compile(
    rf"(?P<method>{_METHODS})\s+(?P<path>/\S*)\s+HTTP/[\d.]+\s+(?P<status>\d{{3}})",
    re.IGNORECASE,
)

# Express / compact: GET /path 200 42ms
_COMPACT = re.compile(
    rf"\b(?P<method>{_METHODS})\s+(?P<path>/\S*)\s+(?P<status>\d{{3}})"
    rf"(?:\s+(?P<duration>[\d.]+)\s*(?P<unit>ms|s))?",
    re.IGNORECASE,
)


def _from_match(match: re.Match[str]) -> dict[str, Any] | None:
    path = match.group("path")
    if not path.startswith("/"):
        return None
    status_raw = match.groupdict().get("status")
    return {
        "method": match.group("method").upper(),
        "endpoint": path,
        "status": int(status_raw) if status_raw else None,
        "duration_ms": _duration_ms(match.groupdict()),
    }


def _quoted_http(line: str) -> dict[str, Any] | None:
    match = _QUOTED_HTTP.search(line)
    return _from_match(match) if match else None


def _http_line(line: str) -> dict[str, Any] | None:
    match = _HTTP_LINE.search(line)
    return _from_match(match) if match else None


def _compact(line: str) -> dict[str, Any] | None:
    match = _COMPACT.search(line)
    return _from_match(match) if match else None


DEFAULT_PARSERS: tuple[Parser, ...] = (_quoted_http, _http_line, _compact)


@dataclass(frozen=True)
class ApiRequest:
    timestamp: datetime
    service: str
    method: str
    endpoint: str
    status: int | None
    duration_ms: float | None
    raw: str


class ApiMonitor:
    """Extract request records from service logs. Never invents traffic."""

    def __init__(self, limit: int = 500, parsers: list[Parser] | None = None) -> None:
        self._limit = limit
        self._events: deque[ApiRequest] = deque(maxlen=limit)
        self._parsers: list[Parser] = list(parsers) if parsers is not None else list(DEFAULT_PARSERS)

    def add_parser(self, parser: Parser, *, prepend: bool = True) -> None:
        """Register a pluggable line parser. Custom parsers run first by default."""
        if prepend:
            self._parsers.insert(0, parser)
        else:
            self._parsers.append(parser)

    def ingest_log(self, event: LogEvent) -> ApiRequest | None:
        parsed = parse_api_line(event.message, parsers=self._parsers)
        if parsed is None:
            return None
        duration = parsed.get("duration_ms")
        record = ApiRequest(
            timestamp=event.timestamp,
            service=event.service,
            method=str(parsed["method"]),
            endpoint=str(parsed["endpoint"]),
            status=parsed["status"] if isinstance(parsed["status"], int) else None,
            duration_ms=float(duration) if isinstance(duration, (int, float)) else None,
            raw=event.message,
        )
        self._events.append(record)
        return record

    def ingest_line(
        self,
        service: str,
        line: str,
        timestamp: datetime | None = None,
    ) -> ApiRequest | None:
        return self.ingest_log(
            LogEvent(
                timestamp=timestamp or datetime.now(),
                service=service,
                stream="stdout",
                message=line,
            )
        )

    def requests(self) -> list[ApiRequest]:
        return list(self._events)

    def clear(self) -> None:
        self._events.clear()


def parse_api_line(line: str, parsers: list[Parser] | None = None) -> dict[str, Any] | None:
    text = line.strip()
    if not text:
        return None
    for parser in parsers if parsers is not None else DEFAULT_PARSERS:
        parsed = parser(text)
        if parsed is not None:
            return parsed
    return None


def _duration_ms(groups: dict[str, str | None]) -> float | None:
    raw = groups.get("duration")
    if not raw:
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    unit = (groups.get("unit") or "ms").lower()
    if unit == "s":
        return value * 1000.0
    return value
