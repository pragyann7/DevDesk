"""Textual application: screens, managers, and global key bindings."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, ContentSwitcher, Static

from devdesk.api.monitor import ApiMonitor
from devdesk.config.loader import load_settings, save_settings
from devdesk.config.schema import AppSettings
from devdesk.core.log_manager import LogEvent, LogManager
from devdesk.core.process_manager import StreamName
from devdesk.core.project_manager import ProjectManager, describe_open_error
from devdesk.core.service_manager import ServiceManager
from devdesk.models.service import Service, ServiceState
from devdesk.ui import (
    LogArrived,
    ServiceAction,
    ServiceFailed,
    ServiceStateChanged,
    SidebarCommand,
)
from devdesk.ui.screens.api_monitor import ApiMonitorView
from devdesk.ui.screens.backend import BackendView
from devdesk.ui.screens.dashboard import DashboardView
from devdesk.ui.screens.frontend import FrontendView
from devdesk.ui.screens.project_switcher import ProjectConfigScreen, ProjectSwitcherScreen
from devdesk.ui.screens.service_view import ServiceView
from devdesk.ui.screens.settings import SettingsScreen
from devdesk.ui.widgets.log_panel import LogPanel
from devdesk.ui.widgets.sidebar import Sidebar
from devdesk.ui.widgets.status_bar import StatusBar


class ConfirmModal(ModalScreen[bool]):
    BINDINGS = [("escape", "no", "Cancel"), ("enter", "yes", "Confirm")]

    def __init__(self, title: str, body: str) -> None:
        super().__init__()
        self._title = title
        self._body = body

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(self._title, classes="error-title")
            yield Static(self._body)
            with Horizontal():
                yield Button("Confirm", id="yes", variant="error")
                yield Button("Cancel", id="no")

    def action_yes(self) -> None:
        self.dismiss(True)

    def action_no(self) -> None:
        self.dismiss(False)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "yes")


class ErrorModal(ModalScreen[None]):
    BINDINGS = [("escape", "close", "Dismiss")]

    def __init__(self, service: Service, reason: str, details: str = "") -> None:
        super().__init__()
        self.service = service
        self.reason = reason
        self.details = details
        self._showing_details = False

    def compose(self) -> ComposeResult:
        command = " ".join(self.service.command)
        with Vertical():
            yield Static(f"✕ Failed to start {self.service.name}", classes="error-title")
            yield Static(f"Command:\n{command}")
            yield Static(f"Reason:\n{self.reason}")
            if self.service.exit_code is not None:
                yield Static(f"Exit code: {self.service.exit_code}")
            yield Static("", id="error-details", classes="muted")
            with Horizontal():
                yield Button("View Details", id="details")
                yield Button("Dismiss", id="dismiss", variant="primary")

    def action_close(self) -> None:
        self.dismiss(None)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "dismiss":
            self.dismiss(None)
            return
        if event.button.id == "details":
            self._showing_details = not self._showing_details
            extra = self.query_one("#error-details", Static)
            if not self._showing_details:
                extra.update("")
                return
            lines = [
                f"Working directory: {self.service.directory}",
                f"State: {self.service.state.value}",
            ]
            if self.details:
                lines.append("Recent output:")
                lines.append(self.details)
            extra.update("\n".join(lines))


class DevDeskApp(App[None]):
    CSS_PATH = Path(__file__).parent / "ui" / "styles" / "app.tcss"
    TITLE = "DevDesk"
    BINDINGS = [
        Binding("q", "request_quit", "Quit"),
        Binding("a", "start_all", "Start all"),
        Binding("r", "restart_selected", "Restart"),
        Binding("s", "stop_selected", "Stop"),
        Binding("c", "clear_logs", "Clear"),
        Binding("p", "toggle_pause", "Pause"),
        Binding("l", "follow_logs", "Follow"),
        Binding("left_square_bracket", "cycle_dashboard(-1)", "Prev service"),
        Binding("right_square_bracket", "cycle_dashboard(1)", "Next service"),
        Binding("escape", "back", "Back / Sidebar"),
        Binding("tab", "focus_next", "Focus", show=False),
    ]

    def __init__(self, initial_project: str | Path | None = None) -> None:
        super().__init__()
        self.initial_project = Path(initial_project).expanduser() if initial_project else None
        self.settings: AppSettings = load_settings()
        self.project_manager = ProjectManager()
        self.log_manager = LogManager(self.settings.log_buffer_size)
        self.service_manager = ServiceManager(log_manager=self.log_manager)
        self.api_monitor = ApiMonitor()
        self.current_view = "dashboard"
        self._dashboard_offset = 0
        self._pending_log_events: list[LogEvent] = []

    def compose(self) -> ComposeResult:
        with Horizontal(id="chrome"):
            with Vertical():
                yield Static("DEV DESK", id="chrome-title")
                yield Static("Universal Development Control Center", classes="muted")
            yield Static("○ NO PROJECT", id="chrome-status")
        with Horizontal(id="body"):
            yield Sidebar()
            with ContentSwitcher(initial="dashboard", id="main"):
                yield DashboardView(id="dashboard")
                yield BackendView(id="backend")
                yield FrontendView(id="frontend")
                yield ServiceView(id="service_view")
                yield ApiMonitorView(id="api_monitor")
        yield StatusBar()

    def on_mount(self) -> None:
        self.service_manager.set_listeners(
            on_state=self._on_service_state,
            on_log=self._on_service_log,
            on_error=self._on_service_error,
        )
        self.set_interval(1.0, self._refresh_status)
        self.set_interval(0.04, self._flush_pending_logs)
        self._open_initial_project()
        self._sync_project_ui()

    def _open_initial_project(self) -> None:
        candidates: list[Path] = []
        if self.initial_project is not None:
            candidates.append(self.initial_project)
        candidates.extend(self.project_manager.recent)
        for path in candidates:
            try:
                project = self.project_manager.open(path)
            except Exception:  # noqa: BLE001
                continue
            self.service_manager.attach_project(project)
            if self.settings.auto_start_on_open:
                self.run_worker(self.service_manager.start_all(), exclusive=False)
            else:
                self.run_worker(self.service_manager.start_configured(), exclusive=False)
            return

    def _on_service_log(
        self,
        name: str,
        stream: StreamName,
        line: str,
        timestamp: datetime,
    ) -> None:
        event = LogEvent(timestamp=timestamp, service=name, stream=stream, message=line)
        self._pending_log_events.append(event)

    def _flush_pending_logs(self) -> None:
        if not self._pending_log_events:
            return
        events = self._pending_log_events
        self._pending_log_events = []

        new_api_request = False
        events_by_service: dict[str, list[LogEvent]] = {}
        for event in events:
            if self.api_monitor.ingest_log(event) is not None:
                new_api_request = True
            events_by_service.setdefault(event.service, []).append(event)

        visible_panels = self._get_visible_log_panels()
        for panel in visible_panels:
            if panel.service_name and panel.service_name in events_by_service:
                panel.append_events(events_by_service[panel.service_name])

        if self.current_view == "api_monitor" and new_api_request:
            self.query_one(ApiMonitorView).replace_rows(self.api_monitor.requests())

    def _on_service_state(self, service: Service) -> None:
        self.post_message(ServiceStateChanged(service))

    def _on_service_error(self, service: Service, reason: str) -> None:
        self.post_message(ServiceFailed(service, reason))

    def on_log_arrived(self, message: LogArrived) -> None:
        self._pending_log_events.append(message.event)

    def on_service_state_changed(self, message: ServiceStateChanged) -> None:
        self._refresh_headers()
        self._refresh_status()

    def on_service_failed(self, message: ServiceFailed) -> None:
        recent = self.log_manager.get(message.service.name)[-8:]
        details = "\n".join(
            f"{event.timestamp.strftime('%H:%M:%S')} {event.stream}: {event.message}"
            for event in recent
        )
        self.push_screen(ErrorModal(message.service, message.reason, details))

    def on_service_action(self, message: ServiceAction) -> None:
        service = self.service_manager.get(message.service_name)
        if not service:
            return
        if message.action == "start":
            self.run_worker(self.service_manager.start(service))
        elif message.action == "stop":
            self.run_worker(self.service_manager.stop(service))
        elif message.action == "restart":
            self.run_worker(self.service_manager.restart(service))

    def on_sidebar_command(self, message: SidebarCommand) -> None:
        command = message.command
        if command in {"dashboard", "backend", "frontend", "api_monitor"}:
            self._show_view(command)
            self._focus_active_view()
            return
        if command.startswith("svc-"):
            service_name = command.removeprefix("svc-")
            self._show_service(service_name)
            self._focus_active_view()
            return
        if command == "start_all":
            self.action_start_all()
        elif command == "stop_all":
            self.run_worker(self._stop_all(), exclusive=True)
        elif command == "restart_all":
            self.run_worker(self.service_manager.restart_all(), exclusive=True)
        elif command == "switch_project":
            self._open_switcher()
        elif command == "configure_project":
            if self.project_manager.current:
                self.push_screen(
                    ProjectConfigScreen(self.project_manager.current),
                    self._after_project_configured,
                )
            else:
                self.notify("Open a project first.")
        elif command == "settings":
            self._open_settings()
        elif command == "exit":
            self.action_request_quit()

    def _show_view(self, name: str) -> None:
        self.current_view = name
        self.query_one("#main", ContentSwitcher).current = name
        self.query_one(Sidebar).highlight(name)
        if name == "api_monitor":
            self.query_one(ApiMonitorView).replace_rows(self.api_monitor.requests())
        self._reload_visible_logs()
        self._focus_active_view()

    def _show_service(self, name: str) -> None:
        service = self.service_manager.get(name)
        if not service:
            return

        # If it's the primary frontend/backend, show that view for legacy support
        project = self.project_manager.current
        top_name, bottom_name = (None, None)
        if project:
            top_svc, bottom_svc = project.display_pair(self._dashboard_offset)
            top_name = top_svc.name if top_svc else None
            bottom_name = bottom_svc.name if bottom_svc else None

        if name == top_name:
            self._show_view("frontend")
            return
        if name == bottom_name:
            self._show_view("backend")
            return

        self.current_view = f"svc-{name}"
        self.query_one(ServiceView).bind_service(service)
        self.query_one("#main", ContentSwitcher).current = "service_view"
        self.query_one(Sidebar).highlight(f"svc-{name}")
        self._reload_visible_logs()
        self._focus_active_view()

    def _open_switcher(self) -> None:
        start = self.settings.default_project_directory
        if self.project_manager.current:
            start = self.project_manager.current.path
        self.push_screen(ProjectSwitcherScreen(self.project_manager, start), self._after_switch)

    def _after_switch(self, path: str | None) -> None:
        if not path:
            return
        self.run_worker(self._switch_project(Path(path)), exclusive=True)

    async def _switch_project(self, path: Path) -> None:
        try:
            await self.service_manager.stop_all()
            self.log_manager.clear_all()
            self.api_monitor.clear()
            self._dashboard_offset = 0
            project = self.project_manager.open(path)
            self.service_manager.attach_project(project)
            self.query_one(StatusBar).reset_uptime()
            self._sync_project_ui()
            if self.settings.auto_start_on_open:
                await self.service_manager.start_all()
            else:
                await self.service_manager.start_configured()
            self.notify(f"Loaded {project.name}")
        except Exception as exc:  # noqa: BLE001
            self.notify(describe_open_error(exc), severity="error")

    def _after_project_configured(self, reloaded: bool | None) -> None:
        if not reloaded:
            return
        self._reload_current_project()

    def _reload_current_project(self) -> None:
        current = self.project_manager.current
        if current is None:
            return
        try:
            old_services = {s.name: s for s in self.service_manager.services()}
            project = self.project_manager.open(current.path)
            for s in project.services:
                old = old_services.get(s.name)
                if old and (old.is_active or self.service_manager.processes.is_running(s.name)):
                    s.state = old.state
                    s.pid = old.pid
                    s.started_at = old.started_at
            self.service_manager.attach_project(project)
            self._sync_project_ui()
            self.notify(f"Reloaded {project.name} configuration")
        except Exception as exc:  # noqa: BLE001
            self.notify(describe_open_error(exc), severity="error")

    def _open_settings(self) -> None:
        self.push_screen(SettingsScreen(self.settings), self._after_settings)

    def _after_settings(self, settings: AppSettings | None) -> None:
        if settings is None:
            return
        self.settings = settings
        self.log_manager.set_limit(settings.log_buffer_size)
        save_settings(settings)
        for panel in self.query(LogPanel):
            panel.set_follow(settings.auto_follow_logs)
            panel.set_max_lines(settings.log_buffer_size)
        self.notify("Settings saved")

    def _sync_project_ui(self) -> None:
        project = self.project_manager.current
        self.query_one(Sidebar).bind_project(project)
        dashboard = self.query_one(DashboardView)
        dashboard.bind_project(project, offset=self._dashboard_offset)
        top, bottom = (None, None) if project is None else project.display_pair(self._dashboard_offset)
        self.query_one(FrontendView).bind_service(top)
        self.query_one(BackendView).bind_service(bottom)

        # Update ServiceView if active
        if self.current_view.startswith("svc-"):
            svc_name = self.current_view.removeprefix("svc-")
            services = {s.name: s for s in self.service_manager.services()}
            self.query_one(ServiceView).bind_service(services.get(svc_name))

        for panel in self.query(LogPanel):
            panel.set_follow(self.settings.auto_follow_logs)
            panel.set_max_lines(self.settings.log_buffer_size)
            panel.clear_view()

        self._reload_visible_logs()
        self._refresh_headers()
        self._refresh_status()

    def _get_visible_log_panels(self) -> list[LogPanel]:
        try:
            switcher = self.query_one("#main", ContentSwitcher)
            current_id = switcher.current
            if not current_id:
                return []
            current_view = self.query_one(f"#{current_id}")
            return [panel for panel in current_view.query(LogPanel) if panel.display]
        except Exception:
            return []

    def _reload_visible_logs(self) -> None:
        for panel in self._get_visible_log_panels():
            if panel.service_name:
                panel.load_events(self.log_manager.get(panel.service_name))

    def _refresh_headers(self) -> None:
        project = self.project_manager.current
        services = {item.name: item for item in self.service_manager.services()}
        for panel in self._get_visible_log_panels():
            if panel.service_name and panel.service_name in services:
                panel.set_service(services[panel.service_name])
        top, bottom = (None, None) if project is None else project.display_pair(self._dashboard_offset)
        self.query_one(FrontendView).bind_service(top)
        self.query_one(BackendView).bind_service(bottom)

        # Update ServiceView if active
        if self.current_view.startswith("svc-"):
            svc_name = self.current_view.removeprefix("svc-")
            services = {s.name: s for s in self.service_manager.services()}
            self.query_one(ServiceView).bind_service(services.get(svc_name))

    def _refresh_status(self) -> None:
        services = self.service_manager.services()
        label, css = _overall_status(services)
        status = self.query_one("#chrome-status", Static)
        if label != getattr(self, "_last_status_label", None):
            self._last_status_label = label
            status.update(label, layout=False)
        if css != getattr(self, "_last_status_css", None):
            self._last_status_css = css
            status.set_classes(css)
        project = self.project_manager.current
        hint = project.name if project else "Switch Project to begin"
        self.query_one(StatusBar).show(services, hint=hint)

    def _selected_panel(self) -> LogPanel | None:
        focused = self.focused
        if isinstance(focused, LogPanel):
            return focused
        visible = self._get_visible_log_panels()
        return visible[0] if visible else None

    def _selected_service(self) -> Service | None:
        panel = self._selected_panel()
        if panel and panel.service_name:
            return self.service_manager.get(panel.service_name)
        services = self.service_manager.services()
        return services[0] if services else None

    def action_start_all(self) -> None:
        if not self.service_manager.services():
            self.notify("Open a project first.")
            return
        self.run_worker(self.service_manager.start_all(), exclusive=False)

    def action_restart_selected(self) -> None:
        service = self._selected_service()
        if service is None:
            self.notify("No service selected.")
            return
        self.run_worker(self.service_manager.restart(service), exclusive=False)

    def action_stop_selected(self) -> None:
        service = self._selected_service()
        if service is None:
            self.notify("No service selected.")
            return
        self.run_worker(self.service_manager.stop(service), exclusive=False)

    def action_clear_logs(self) -> None:
        panel = self._selected_panel()
        if panel is None or panel.service_name is None:
            return
        self.log_manager.clear(panel.service_name)
        panel.clear_view()

    def action_toggle_pause(self) -> None:
        panel = self._selected_panel()
        if panel is None:
            return
        paused = panel.toggle_pause()
        self.notify("Logs paused" if paused else "Logs resumed")

    def action_follow_logs(self) -> None:
        panel = self._selected_panel()
        if panel is None:
            return
        panel.set_follow(True)
        panel.log_widget.scroll_end(animate=False)
        self.notify("Following latest output")

    def action_cycle_dashboard(self, delta: int) -> None:
        project = self.project_manager.current
        if project is None or len(project.services) < 2:
            return
        self._dashboard_offset = (self._dashboard_offset + delta) % len(project.services)
        self._sync_project_ui()
        top, bottom = project.display_pair(self._dashboard_offset)
        names = " / ".join(item.name for item in (top, bottom) if item)
        self.notify(f"Dashboard panels: {names}")

    def _focus_active_view(self) -> None:
        if self.current_view == "api_monitor":
            self.query_one(ApiMonitorView).table_widget.focus()
            return
        panels = self._get_visible_log_panels()
        if panels:
            panels[0].focus()
        else:
            self.query_one("#main").focus()

    def action_back(self) -> None:
        if self.screen is not self.screen_stack[0]:
            self.pop_screen()
            return

        sidebar = self.query_one(Sidebar)
        is_sidebar_focused = self.focused is sidebar or (
            self.focused is not None and sidebar in self.focused.ancestors
        )

        if self.current_view != "dashboard":
            self._show_view("dashboard")
            sidebar.focus()
            return

        if is_sidebar_focused:
            self._focus_active_view()
        else:
            sidebar.focus()

    def action_request_quit(self) -> None:
        running = [item for item in self.service_manager.services() if item.is_active]
        if running and self.settings.confirm_before_stop:
            names = ", ".join(item.name for item in running)
            self.push_screen(
                ConfirmModal("Stop running services?", f"These services are still running:\n{names}"),
                self._after_quit_confirm,
            )
            return
        self.run_worker(self._shutdown(), exclusive=True)

    def _after_quit_confirm(self, confirmed: bool | None) -> None:
        if confirmed:
            self.run_worker(self._shutdown(), exclusive=True)

    async def _stop_all(self) -> None:
        running = [item for item in self.service_manager.services() if item.is_active]
        if running and self.settings.confirm_before_stop:
            # Direct stop-all from the sidebar should still honour the setting.
            names = ", ".join(item.name for item in running)

            async def _ask() -> None:
                confirmed = await self.push_screen_wait(
                    ConfirmModal("Stop all services?", names)
                )
                if confirmed:
                    await self.service_manager.stop_all()

            await _ask()
            return
        await self.service_manager.stop_all()

    async def _shutdown(self) -> None:
        await self.service_manager.stop_all()
        self.exit()


def _overall_status(services: list[Service]) -> tuple[str, str]:
    if not services:
        return "○ NO PROJECT", "status-stopped"
    states = {item.state for item in services}
    if ServiceState.FAILED in states:
        return "⚠ SOME SERVICES FAILED", "status-failed"
    if ServiceState.STARTING in states:
        return "◌ STARTING SERVICES", "status-starting"
    if ServiceState.STOPPING in states:
        return "◐ STOPPING SERVICES", "status-stopping"
    if states == {ServiceState.RUNNING}:
        return "● ALL SYSTEMS OK", "status-running"
    if states == {ServiceState.STOPPED}:
        return "○ ALL STOPPED", "status-stopped"
    if ServiceState.RUNNING in states:
        return "◐ SOME SERVICES IDLE", "status-starting"
    return "? UNKNOWN", "status-unknown"
