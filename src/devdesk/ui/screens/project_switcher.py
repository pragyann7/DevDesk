"""Open, recall, and discover projects. Also shows current project configuration."""

from __future__ import annotations

import tomllib
from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, DirectoryTree, Input, Label, Static, TextArea

from devdesk.config.schema import ConfigError, validate_project_config
from devdesk.core.project_manager import ProjectManager
from devdesk.models.project import Project
from devdesk.utils.paths import project_config_path


class ProjectSwitcherScreen(ModalScreen[str | None]):
    BINDINGS = [("escape", "cancel", "Close")]

    def __init__(self, manager: ProjectManager, start: Path) -> None:
        super().__init__()
        self.manager = manager
        self.start = start if start.exists() else Path.home()
        self._recent_index: dict[str, Path] = {}
        self._discovered: dict[str, Path] = {}

    def compose(self) -> ComposeResult:
        with Vertical(id="switcher"):
            yield Label("Open Project")
            yield Input(str(self.start), placeholder="Path to a project directory", id="project-path")
            with Horizontal():
                yield Button("Open", id="open", variant="primary")
                yield Button("Discover here", id="discover")
                yield Button("Cancel", id="cancel")
            yield Label("Recent Projects")
            recent = self.manager.recent
            if recent:
                for index, path in enumerate(recent):
                    key = f"recent-{index}"
                    self._recent_index[key] = path
                    yield Button(str(path), id=key, classes="recent-path")
            else:
                yield Static("No recent projects.", classes="muted")
            yield Label("Browse")
            yield DirectoryTree(str(self.start), id="tree")
            yield Label("Discovered", id="discovered-label")
            yield Static("Use Discover here to list projects under the path.", id="discovered", classes="muted")

    def action_cancel(self) -> None:
        self.dismiss(None)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id or ""
        if button_id == "cancel":
            self.dismiss(None)
            return
        if button_id == "open":
            self.dismiss(self.query_one("#project-path", Input).value.strip() or None)
            return
        if button_id == "discover":
            root = Path(self.query_one("#project-path", Input).value.strip() or str(self.start))
            found = self.manager.discover(root)
            box = self.query_one("#discovered", Static)
            if not found:
                self._discovered.clear()
                box.update(f"No .devdesk/config.toml under {root}")
                self.notify(f"No .devdesk/config.toml under {root}")
                return
            if len(found) == 1:
                self.dismiss(str(found[0]))
                return
            self._discovered = {f"found-{index}": path for index, path in enumerate(found)}
            listing = "\n".join(f"  {index + 1}. {path}" for index, path in enumerate(found))
            box.update(f"{len(found)} projects found. Open one by number in the path field, or click Open after pasting a path.\n{listing}")
            self.query_one("#project-path", Input).value = str(found[0])
            self.notify(f"Found {len(found)} projects. Path set to the first; edit or Open.")
            return
        if button_id in self._recent_index:
            self.dismiss(str(self._recent_index[button_id]))
            return
        if button_id in self._discovered:
            self.dismiss(str(self._discovered[button_id]))

    def on_directory_tree_directory_selected(self, event: DirectoryTree.DirectorySelected) -> None:
        path = Path(event.path)
        self.query_one("#project-path", Input).value = str(path)
        if project_config_path(path).is_file():
            self.notify(f"DevDesk config found in {path.name}")

    def on_directory_tree_file_selected(self, event: DirectoryTree.FileSelected) -> None:
        path = Path(event.path)
        if path.name == "config.toml" and path.parent.name == ".devdesk":
            self.dismiss(str(path.parent.parent))
            return
        self.query_one("#project-path", Input).value = str(path.parent)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value.strip() or None)



class ProjectConfigScreen(ModalScreen[bool]):
    BINDINGS = [
        ("escape", "cancel", "Cancel"),
        ("ctrl+s", "save", "Save"),
    ]

    def __init__(self, project: Project | None) -> None:
        super().__init__()
        self.project = project
        self._config_path: Path | None = None
        self._initial_content: str = ""

    def compose(self) -> ComposeResult:
        with Vertical(id="project-config-modal"):
            yield Label("Configure Project (.devdesk/config.toml)", classes="modal-title")
            if self.project is None:
                yield Static("No project loaded. Open a project first.", classes="muted")
                yield Button("Close", id="cancel", variant="primary")
                return

            self._config_path = project_config_path(self.project.path)
            yield Static(f"Project: {self.project.name}  ·  {self._config_path}", classes="muted")

            if self._config_path.is_file():
                try:
                    self._initial_content = self._config_path.read_text(encoding="utf-8")
                except Exception as exc:
                    self._initial_content = f"# Error reading {self._config_path}: {exc}"
            else:
                self._initial_content = (
                    f'[project]\nname = "{self.project.name}"\n\n'
                    "# Example services:\n"
                    '# [services.backend]\n# command = ["python", "app.py"]\n# directory = "."\n# port = 8000\n'
                )

            yield TextArea(self._initial_content, language="toml", id="config-editor")
            with Horizontal(id="config-actions"):
                yield Button("Save & Reload", id="save", variant="primary")
                yield Button("Cancel", id="cancel")

    def action_cancel(self) -> None:
        self.dismiss(False)

    def action_save(self) -> None:
        self._do_save()

    def _do_save(self) -> None:
        if self.project is None or self._config_path is None:
            self.dismiss(False)
            return

        editor = self.query_one("#config-editor", TextArea)
        new_content = editor.text

        # 1. Validate TOML syntax
        try:
            raw_data = tomllib.loads(new_content)
        except tomllib.TOMLDecodeError as exc:
            self.notify(f"Invalid TOML: {exc}", severity="error")
            return

        # 2. Validate DevDesk schema
        try:
            validate_project_config(raw_data)
        except Exception as exc:
            self.notify(f"Config error: {exc}", severity="error")
            return

        # 3. Save to disk
        try:
            self._config_path.parent.mkdir(parents=True, exist_ok=True)
            self._config_path.write_text(new_content, encoding="utf-8")
        except Exception as exc:
            self.notify(f"Failed to save file: {exc}", severity="error")
            return

        self.dismiss(True)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save":
            self._do_save()
        elif event.button.id == "cancel":
            self.dismiss(False)
