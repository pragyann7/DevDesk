"""Small terminal/display helpers."""

from __future__ import annotations

from datetime import datetime

from devdesk.models.service import ServiceState


STATUS_GLYPHS: dict[ServiceState, str] = {
    ServiceState.STARTING: "◌",
    ServiceState.RUNNING: "●",
    ServiceState.STOPPING: "◐",
    ServiceState.STOPPED: "○",
    ServiceState.FAILED: "✕",
    ServiceState.UNKNOWN: "?",
}


def format_duration(seconds: float) -> str:
    total = max(0, int(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def format_uptime(started_at: datetime | None, now: datetime | None = None) -> str:
    if started_at is None:
        return "00:00:00"
    current = now or datetime.now()
    return format_duration((current - started_at).total_seconds())


def format_port(port: int | None) -> str:
    return f":{port}" if port is not None else ""


def status_label(state: ServiceState) -> str:
    return f"{STATUS_GLYPHS[state]} {state.value}"
