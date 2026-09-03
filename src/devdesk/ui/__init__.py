"""UI package. Screens import widgets; widgets never start processes."""

from __future__ import annotations

from textual.message import Message

from devdesk.core.log_manager import LogEvent
from devdesk.models.service import Service


class SidebarCommand(Message):
    """User selected a sidebar entry. The App maps this to managers/screens."""

    def __init__(self, command: str) -> None:
        super().__init__()
        self.command = command


class LogArrived(Message):
    def __init__(self, event: LogEvent) -> None:
        super().__init__()
        self.event = event


class ServiceStateChanged(Message):
    def __init__(self, service: Service) -> None:
        super().__init__()
        self.service = service


class ServiceFailed(Message):
    def __init__(self, service: Service, reason: str) -> None:
        super().__init__()
        self.service = service
        self.reason = reason


class ServiceAction(Message):
    """A control action (start/stop/restart) for a specific service."""

    def __init__(self, service_name: str, action: str) -> None:
        super().__init__()
        self.service_name = service_name
        self.action = action
