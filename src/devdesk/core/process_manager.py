"""Low-level asynchronous process control.

The UI must never call this module directly; use ServiceManager instead.
"""

from __future__ import annotations

import asyncio
import os
import signal
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

from devdesk.models.process import ProcessInfo

StreamName = Literal["stdout", "stderr"]

OutputCallback = Callable[[str, StreamName, str, datetime], None]
ExitCallback = Callable[[str, int], None]
StartedCallback = Callable[[str, int], None]
FailedCallback = Callable[[str, str], None]


@dataclass
class ManagedProcess:
    info: ProcessInfo
    process: asyncio.subprocess.Process
    tasks: list[asyncio.Task[None]]


class ProcessManager:
    """Start, stop, and stream output from child processes."""

    def __init__(
        self,
        *,
        subprocess_factory: Callable[..., Awaitable[asyncio.subprocess.Process]] | None = None,
        stop_timeout: float = 8.0,
    ) -> None:
        self._factory = subprocess_factory or asyncio.create_subprocess_exec
        self._stop_timeout = stop_timeout
        self._managed: dict[str, ManagedProcess] = {}
        self._last_info: dict[str, ProcessInfo] = {}
        self._on_output: OutputCallback | None = None
        self._on_exit: ExitCallback | None = None
        self._on_started: StartedCallback | None = None
        self._on_failed: FailedCallback | None = None

    def set_listeners(
        self,
        *,
        on_output: OutputCallback | None = None,
        on_exit: ExitCallback | None = None,
        on_started: StartedCallback | None = None,
        on_failed: FailedCallback | None = None,
    ) -> None:
        self._on_output = on_output
        self._on_exit = on_exit
        self._on_started = on_started
        self._on_failed = on_failed

    def is_running(self, name: str) -> bool:
        managed = self._managed.get(name)
        return managed is not None and managed.process.returncode is None

    def info(self, name: str) -> ProcessInfo | None:
        managed = self._managed.get(name)
        if managed is not None:
            return managed.info
        return self._last_info.get(name)

    async def start(
        self,
        name: str,
        command: list[str],
        cwd: Path,
        env: dict[str, str] | None = None,
    ) -> int:
        if self.is_running(name):
            raise RuntimeError(f"Service {name!r} is already running.")
        leftover = self._managed.get(name)
        if leftover is not None:
            wait_tasks = [
                task
                for task in leftover.tasks
                if task.get_name() == f"{name}-wait" and not task.done()
            ]
            if wait_tasks:
                await asyncio.gather(*wait_tasks, return_exceptions=True)
            if name in self._managed:
                await self._reap(name)
        if not command:
            raise ValueError("Command must not be empty.")
        if not cwd.is_dir():
            message = f"Working directory does not exist: {cwd}"
            self._emit_failed(name, message)
            raise FileNotFoundError(message)

        try:
            process = await self._factory(
                *command,
                cwd=str(cwd),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                start_new_session=True,
            )
        except FileNotFoundError:
            message = f"Command not found: {command[0]}"
            self._emit_failed(name, message)
            raise
        except PermissionError:
            message = f"Permission denied when starting {command[0]}"
            self._emit_failed(name, message)
            raise
        except OSError as exc:
            message = f"Failed to start process: {exc}"
            self._emit_failed(name, message)
            raise RuntimeError(message) from exc

        pid = int(process.pid or 0)
        info = ProcessInfo(service_name=name, pid=pid, command=list(command), cwd=cwd)
        tasks = [
            asyncio.create_task(self._pump(name, process.stdout, "stdout"), name=f"{name}-stdout"),
            asyncio.create_task(self._pump(name, process.stderr, "stderr"), name=f"{name}-stderr"),
            asyncio.create_task(self._watch_exit(name, process), name=f"{name}-wait"),
        ]
        self._managed[name] = ManagedProcess(info=info, process=process, tasks=tasks)
        if self._on_started:
            self._on_started(name, pid)
        return pid

    async def stop(self, name: str, timeout: float | None = None) -> int | None:
        managed = self._managed.get(name)
        if managed is None:
            return None
        process = managed.process
        if process.returncode is not None:
            return process.returncode

        wait_for = self._stop_timeout if timeout is None else timeout
        self._signal_process_group(process, signal.SIGTERM)
        try:
            return await asyncio.wait_for(process.wait(), timeout=wait_for)
        except TimeoutError:
            self._signal_process_group(process, signal.SIGKILL)
            return await process.wait()

    async def restart(
        self,
        name: str,
        command: list[str],
        cwd: Path,
        env: dict[str, str] | None = None,
    ) -> int:
        await self.stop(name)
        return await self.start(name, command, cwd, env)

    async def stop_all(self) -> None:
        names = list(self._managed)
        await asyncio.gather(*(self.stop(name) for name in names), return_exceptions=True)

    def _signal_process_group(self, process: asyncio.subprocess.Process, sig: signal.Signals) -> None:
        if process.returncode is not None or process.pid is None:
            return
        if isinstance(process, asyncio.subprocess.Process):
            try:
                os.killpg(os.getpgid(process.pid), sig)
                return
            except (ProcessLookupError, PermissionError, OSError):
                pass
        try:
            if sig == signal.SIGKILL:
                process.kill()
            else:
                process.terminate()
        except ProcessLookupError:
            pass

    async def _pump(
        self,
        name: str,
        stream: asyncio.StreamReader | None,
        stream_name: StreamName,
    ) -> None:
        if stream is None:
            return
        while True:
            chunk = await stream.readline()
            if not chunk:
                break
            line = chunk.decode("utf-8", errors="replace").rstrip("\r\n")
            if self._on_output:
                self._on_output(name, stream_name, line, datetime.now())

    async def _watch_exit(self, name: str, process: asyncio.subprocess.Process) -> None:
        returncode = await process.wait()
        managed = self._managed.get(name)
        if managed:
            managed.info.returncode = returncode
        if self._on_exit:
            self._on_exit(name, int(returncode))
        await self._reap(name)

    async def _reap(self, name: str) -> None:
        managed = self._managed.pop(name, None)
        if managed is None:
            return
        managed.info.returncode = managed.process.returncode
        self._last_info[name] = managed.info
        current = asyncio.current_task()
        pending = [task for task in managed.tasks if task is not current and not task.done()]
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

    def _emit_failed(self, name: str, message: str) -> None:
        if self._on_failed:
            self._on_failed(name, message)
