"""Project model: a named root directory plus its services."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from devdesk.models.service import Service


@dataclass
class Project:
    name: str
    path: Path
    services: list[Service] = field(default_factory=list)

    def service(self, name: str) -> Service | None:
        needle = name.lower()
        for item in self.services:
            if item.name.lower() == needle:
                return item
        return None

    def service_names(self) -> list[str]:
        return [item.name for item in self.services]

    def by_role(self, *hints: str, fallback_index: int | None = None) -> Service | None:
        needles = [hint.lower() for hint in hints]
        for service in self.services:
            name = service.name.lower()
            if name in needles or any(hint in name for hint in needles):
                return service
        if fallback_index is not None and 0 <= fallback_index < len(self.services):
            return self.services[fallback_index]
        return None

    def display_pair(self, offset: int = 0) -> tuple[Service | None, Service | None]:
        """Services for the dashboard's top and bottom live panels."""
        if not self.services:
            return None, None
        count = len(self.services)
        start = offset % count
        if start == 0:
            # Try to find specific roles first
            f_service = self.by_role("frontend", "front", "web", "ui", "client")
            b_service = self.by_role("backend", "back", "api", "server")

            if f_service and b_service and f_service.name != b_service.name:
                return f_service, b_service

            if f_service and not b_service:
                # Put frontend in top, find a generic for bottom
                other = next((s for s in self.services if s.name != f_service.name), None)
                return f_service, other

            if b_service and not f_service:
                # Put backend in bottom, find a generic for top
                other = next((s for s in self.services if s.name != b_service.name), None)
                return other, b_service

            # If no clear roles, just use the first two
            top = self.services[0]
            bottom = self.services[1] if count > 1 else None
            return top, bottom

        top = self.services[start]
        bottom = self.services[(start + 1) % count] if count > 1 else None
        return top, bottom
