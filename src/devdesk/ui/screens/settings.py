"""Application settings. Kept small and easy to extend."""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Switch

from devdesk.config.schema import AppSettings


class SettingsScreen(ModalScreen[AppSettings | None]):
    BINDINGS = [("escape", "cancel", "Close")]

    def __init__(self, settings: AppSettings) -> None:
        super().__init__()
        self.original = settings

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("Settings")
            yield Label("Log buffer size")
            yield Input(str(self.original.log_buffer_size), id="buffer")
            with Horizontal():
                yield Label("Auto-follow logs")
                yield Switch(self.original.auto_follow_logs, id="follow")
            with Horizontal():
                yield Label("Confirm before stopping services")
                yield Switch(self.original.confirm_before_stop, id="confirm")
            with Horizontal():
                yield Label("Auto-start services when opening a project")
                yield Switch(self.original.auto_start_on_open, id="autostart")
            yield Label("Default project directory")
            yield Input(str(self.original.default_project_directory), id="default-dir")
            with Horizontal():
                yield Button("Save", id="save", variant="primary")
                yield Button("Cancel", id="cancel")

    def action_cancel(self) -> None:
        self.dismiss(None)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel":
            self.dismiss(None)
            return
        if event.button.id != "save":
            return
        try:
            size = int(self.query_one("#buffer", Input).value.strip())
        except ValueError:
            self.notify("Log buffer size must be an integer.")
            return
        directory = self.query_one("#default-dir", Input).value.strip()
        self.dismiss(
            AppSettings(
                log_buffer_size=max(50, size),
                auto_follow_logs=self.query_one("#follow", Switch).value,
                confirm_before_stop=self.query_one("#confirm", Switch).value,
                auto_start_on_open=self.query_one("#autostart", Switch).value,
                default_project_directory=Path(directory).expanduser() if directory else Path.home(),
            )
        )
