"""ProcessManager lifecycle with a fake subprocess factory."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from devdesk.core.process_manager import ProcessManager


class FakeStream:
    def __init__(self, lines: list[bytes]) -> None:
        self._lines = list(lines)

    async def readline(self) -> bytes:
        if not self._lines:
            return b""
        await asyncio.sleep(0)
        return self._lines.pop(0)


class FakeProcess:
    def __init__(self, stdout: list[bytes], stderr: list[bytes], pid: int, exit_code: int) -> None:
        self.pid = pid
        self.stdout = FakeStream(stdout)
        self.stderr = FakeStream(stderr)
        self.returncode: int | None = None
        self._exit_code = exit_code
        self._done = asyncio.Event()
        self.signals: list[str] = []

    async def wait(self) -> int:
        await self._done.wait()
        self.returncode = self._exit_code
        return self._exit_code

    def terminate(self) -> None:
        self.signals.append("terminate")
        self._done.set()

    def kill(self) -> None:
        self.signals.append("kill")
        self._done.set()

    def finish(self) -> None:
        self._done.set()


@pytest.fixture
def manager(tmp_path: Path) -> tuple[ProcessManager, list[FakeProcess], Path]:
    spawned: list[FakeProcess] = []

    async def factory(*_args, **_kwargs):
        process = FakeProcess([b"hello\n", b"world\n"], [b"warn\n"], pid=4242, exit_code=0)
        spawned.append(process)
        return process

    return ProcessManager(subprocess_factory=factory, stop_timeout=0.2), spawned, tmp_path


@pytest.mark.asyncio
async def test_start_streams_output_and_pid(manager: tuple[ProcessManager, list[FakeProcess], Path]) -> None:
    pm, spawned, cwd = manager
    output: list[tuple[str, str, str]] = []
    started: list[int] = []
    pm.set_listeners(
        on_output=lambda name, stream, line, _ts: output.append((name, stream, line)),
        on_started=lambda _name, pid: started.append(pid),
        on_exit=lambda *_args: None,
    )
    pid = await pm.start("web", ["echo", "hello"], cwd)
    assert pid == 4242
    assert started == [4242]
    await asyncio.sleep(0.05)
    assert ("web", "stdout", "hello") in output
    assert ("web", "stderr", "warn") in output
    spawned[0].finish()
    await asyncio.sleep(0.05)
    assert not pm.is_running("web")
    assert pm.info("web") is not None
    assert pm.info("web").returncode == 0


@pytest.mark.asyncio
async def test_stop_terminates_process(manager: tuple[ProcessManager, list[FakeProcess], Path]) -> None:
    pm, spawned, cwd = manager
    await pm.start("api", ["sleep", "10"], cwd)
    code = await pm.stop("api")
    assert code == 0
    assert "terminate" in spawned[0].signals


@pytest.mark.asyncio
async def test_missing_working_directory(tmp_path: Path) -> None:
    pm = ProcessManager()
    failed: list[str] = []
    pm.set_listeners(on_failed=lambda name, message: failed.append(f"{name}:{message}"))
    with pytest.raises(FileNotFoundError):
        await pm.start("api", ["true"], tmp_path / "missing")
    assert failed and "api" in failed[0]


@pytest.mark.asyncio
async def test_process_failure_exit_code(tmp_path: Path) -> None:
    async def factory(*_args, **_kwargs):
        process = FakeProcess([], [], pid=7, exit_code=1)
        process.finish()
        return process

    seen: list[int] = []
    pm = ProcessManager(subprocess_factory=factory)
    pm.set_listeners(on_exit=lambda _name, code: seen.append(code))
    await pm.start("worker", ["false"], tmp_path)
    await asyncio.sleep(0.05)
    assert seen == [1]


@pytest.mark.asyncio
async def test_restart_after_exit(tmp_path: Path) -> None:
    spawned: list[FakeProcess] = []

    async def factory(*_args, **_kwargs):
        process = FakeProcess([], [], pid=100 + len(spawned), exit_code=0)
        process.finish()
        spawned.append(process)
        return process

    pm = ProcessManager(subprocess_factory=factory)
    await pm.start("web", ["true"], tmp_path)
    await asyncio.sleep(0.05)
    assert not pm.is_running("web")
    pid = await pm.start("web", ["true"], tmp_path)
    assert pid == 101
    assert len(spawned) == 2
