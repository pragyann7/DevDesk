"""Parse API request lines from generic service output."""

from __future__ import annotations

import json
import re
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from devdesk.core.log_manager import LogEvent

_METHODS = r"GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS"
Parser = Callable[[str], dict[str, Any] | None]

# Uvicorn / Hypercorn / Django: "GET /path HTTP/1.1" 200
_QUOTED_HTTP = re.compile(
    rf'"(?P<method>{_METHODS})\s+(?P<path>\S+)\s+HTTP/[\d.]+"'\
    rf'\s+(?P<status>\d{{3}})'
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


# ---------------------------------------------------------------------------
# Body extraction helpers
# ---------------------------------------------------------------------------

_BODY_WINDOW = 20  # lines to buffer per service for backward lookup
_MAX_CAPTURE_LINES = 30  # max lines to capture for response body

_BODY_KW_RE = re.compile(
    r"\b(?:body|payload|data|json)\s*[:=]\s*", re.IGNORECASE
)


def _parse_data_string(text: str) -> str | None:
    """Parse JSON or Python dict string into a formatted JSON string."""
    text = text.strip()
    if not text or text[0] not in ("{", "["):
        return None
    try:
        obj = json.loads(text)
        return json.dumps(obj, indent=2)
    except (json.JSONDecodeError, ValueError):
        pass
    try:
        import ast
        obj = ast.literal_eval(text)
        if isinstance(obj, (dict, list)):
            return json.dumps(obj, indent=2, default=str)
    except Exception:
        pass
    return None


def _find_json_in_lines(lines: list[str]) -> str | None:
    """Extract the first valid JSON or dict object/array from a list of log lines."""
    if not lines:
        return None

    # Strategy 1: keyword-prefixed inline JSON (e.g. "Request body: {...}")
    for line in lines:
        match = _BODY_KW_RE.search(line)
        if match:
            rest = line[match.end():].strip()
            parsed = _parse_data_string(rest)
            if parsed is not None:
                return parsed

    # Strategy 2: standalone single-line JSON or dict
    for line in lines:
        parsed = _parse_data_string(line)
        if parsed is not None:
            return parsed

    # Strategy 3: multi-line block
    collecting = False
    collected: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not collecting:
            if stripped and stripped[0] in ("{", "["):
                collecting = True
                collected = [stripped]
        else:
            collected.append(stripped)
            combined = "\n".join(collected)
            parsed = _parse_data_string(combined)
            if parsed is not None:
                return parsed
            if len(collected) > _MAX_CAPTURE_LINES:
                collecting = False
                collected = []

    return None


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class ApiRequest:
    timestamp: datetime
    service: str
    method: str
    endpoint: str
    status: int | None
    duration_ms: float | None
    raw: str
    request_body: str | None = field(default=None, repr=False)
    response_body: str | None = field(default=None, repr=False)

    @property
    def query_params(self) -> dict[str, Any]:
        """Extract query parameters from the request endpoint URL."""
        from urllib.parse import parse_qs, urlparse
        try:
            parsed = urlparse(self.endpoint)
            if not parsed.query:
                return {}
            qs = parse_qs(parsed.query)
            return {k: v[0] if len(v) == 1 else v for k, v in qs.items()}
        except Exception:
            return {}


class ApiMonitor:
    """Extract request records from service logs. Never invents traffic."""

    def __init__(self, limit: int = 500, parsers: list[Parser] | None = None) -> None:
        self._limit = limit
        self._events: deque[ApiRequest] = deque(maxlen=limit)
        self._parsers: list[Parser] = list(parsers) if parsers is not None else list(DEFAULT_PARSERS)
        # Body capture state
        self._line_buffer: dict[str, deque[str]] = {}
        self._pending: dict[str, ApiRequest] = {}
        self._capture_buf: dict[str, list[str]] = {}

    def add_parser(self, parser: Parser, *, prepend: bool = True) -> None:
        """Register a pluggable line parser. Custom parsers run first by default."""
        if prepend:
            self._parsers.insert(0, parser)
        else:
            self._parsers.append(parser)

    def ingest_log(self, event: LogEvent) -> ApiRequest | None:
        service = event.service
        line = event.message

        # Accumulate line for pending response-body capture
        if service in self._pending:
            cap = self._capture_buf.setdefault(service, [])
            cap.append(line)
            if len(cap) >= _MAX_CAPTURE_LINES:
                self._finalize_capture(service)

        buf = self._line_buffer.setdefault(service, deque(maxlen=_BODY_WINDOW))

        # Try to parse as API request
        parsed = parse_api_line(line, parsers=self._parsers)
        if parsed is None:
            buf.append(line)
            return None

        # New API request detected — finalize any previous capture first
        self._finalize_capture(service)

        # Extract request body from buffered lines *before* this API line
        request_body = _find_json_in_lines(list(buf))

        duration = parsed.get("duration_ms")
        record = ApiRequest(
            timestamp=event.timestamp,
            service=service,
            method=str(parsed["method"]),
            endpoint=str(parsed["endpoint"]),
            status=parsed["status"] if isinstance(parsed["status"], int) else None,
            duration_ms=float(duration) if isinstance(duration, (int, float)) else None,
            raw=line,
            request_body=request_body,
        )
        self._events.append(record)

        # Start capturing subsequent lines for response body
        self._pending[service] = record
        self._capture_buf[service] = []

        buf.append(line)
        return record

    def _finalize_capture(self, service: str) -> None:
        """Attach captured response body JSON to the pending request."""
        request = self._pending.pop(service, None)
        lines = self._capture_buf.pop(service, [])
        if request is not None and lines:
            body = _find_json_in_lines(lines)
            if body:
                request.response_body = body

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
        # Finalize any in-flight captures before returning
        for service in list(self._pending):
            self._finalize_capture(service)
        return list(self._events)

    def clear(self) -> None:
        self._events.clear()
        self._line_buffer.clear()
        self._pending.clear()
        self._capture_buf.clear()


_HTTP_METHOD_TOKENS = ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS")


def parse_api_line(line: str, parsers: list[Parser] | None = None) -> dict[str, Any] | None:
    text = line.strip()
    if not text:
        return None
    if parsers is None:
        upper = text.upper()
        if not any(method in upper for method in _HTTP_METHOD_TOKENS):
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
