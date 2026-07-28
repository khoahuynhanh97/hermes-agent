from __future__ import annotations

import ctypes
import ctypes.wintypes
import json
import math
import msvcrt
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Callable

from hermes.backup import OfflineAccessLease
from hermes.maintenance import RuntimeState


_DISCOVER_COMMAND = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$processes = @(
    Get-CimInstance Win32_Process |
        Where-Object { $_.ExecutablePath -and $_.CommandLine } |
        Select-Object ProcessId, ExecutablePath, CommandLine
)
@{ ok = $true; processes = $processes } |
    ConvertTo-Json -Compress -Depth 4
"""

_STOP_COMMAND = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$ids = @(ConvertFrom-Json $env:HERMES_RUNTIME_PIDS)
if ($ids.Count -gt 0) {
    Stop-Process -Id $ids -ErrorAction Stop
}
@{ ok = $true } | ConvertTo-Json -Compress
"""

_FORCE_STOP_COMMAND = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$ids = @(ConvertFrom-Json $env:HERMES_RUNTIME_PIDS)
if ($ids.Count -gt 0) {
    Stop-Process -Id $ids -Force -ErrorAction Stop
}
@{ ok = $true } | ConvertTo-Json -Compress
"""

_START_COMMAND = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$started = @()
try {
    $botArgument = '"' + $env:HERMES_RUNTIME_BOT + '"'
    $workerArgument = '"' + $env:HERMES_RUNTIME_WORKER + '"'
    $bot = Start-Process `
        -FilePath $env:HERMES_RUNTIME_PYTHON `
        -ArgumentList $botArgument `
        -WorkingDirectory $env:HERMES_RUNTIME_CWD `
        -RedirectStandardOutput $env:HERMES_RUNTIME_BOT_STDOUT `
        -RedirectStandardError $env:HERMES_RUNTIME_BOT_STDERR `
        -WindowStyle Hidden `
        -PassThru
    $started += $bot.Id
    $worker = Start-Process `
        -FilePath $env:HERMES_RUNTIME_PYTHON `
        -ArgumentList $workerArgument `
        -WorkingDirectory $env:HERMES_RUNTIME_CWD `
        -RedirectStandardOutput $env:HERMES_RUNTIME_WORKER_STDOUT `
        -RedirectStandardError $env:HERMES_RUNTIME_WORKER_STDERR `
        -WindowStyle Hidden `
        -PassThru
    $started += $worker.Id
    @{ ok = $true; pids = $started } |
        ConvertTo-Json -Compress -Depth 3
} catch {
    foreach ($processId in $started) {
        Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
    }
    @{ ok = $false; code = 'start_failed' } |
        ConvertTo-Json -Compress
}
"""


def _default_powershell_runner(
    command: str,
    *,
    env: dict[str, str],
    timeout: int,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            command,
        ],
        capture_output=True,
        check=False,
        encoding="utf-8",
        env=env,
        text=True,
        timeout=timeout,
        windows_creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def _normalized_path(value: str | Path) -> str:
    return os.path.normcase(os.path.abspath(os.fspath(value)))


def _split_command_line(command_line: str) -> list[str]:
    if os.name != "nt":
        raise RuntimeError("Windows command-line parsing is unavailable")
    command_line_to_argv = ctypes.windll.shell32.CommandLineToArgvW
    command_line_to_argv.argtypes = [
        ctypes.wintypes.LPCWSTR,
        ctypes.POINTER(ctypes.c_int),
    ]
    command_line_to_argv.restype = ctypes.POINTER(ctypes.wintypes.LPWSTR)
    argc = ctypes.c_int()
    argv = command_line_to_argv(
        command_line,
        ctypes.byref(argc),
    )
    if not argv:
        raise RuntimeError("Windows command line is invalid")
    try:
        return [argv[index] for index in range(argc.value)]
    finally:
        local_free = ctypes.windll.kernel32.LocalFree
        local_free.argtypes = [ctypes.wintypes.HLOCAL]
        local_free.restype = ctypes.wintypes.HLOCAL
        local_free(argv)


@dataclass(frozen=True)
class _TargetProcess:
    pid: int
    role: str
    executable: str
    script: str


@dataclass(frozen=True)
class _ProcessSnapshot:
    targets: dict[int, _TargetProcess]
    unexpected_count: int

    @property
    def bot_count(self) -> int:
        return sum(item.role == "bot" for item in self.targets.values())

    @property
    def worker_count(self) -> int:
        return sum(item.role == "worker" for item in self.targets.values())

    @property
    def exactly_running(self) -> bool:
        return (
            self.bot_count == 1
            and self.worker_count == 1
            and self.unexpected_count == 0
        )

    @property
    def exactly_stopped(self) -> bool:
        return not self.targets and self.unexpected_count == 0


class _WindowsOfflineLease(OfflineAccessLease):
    def __init__(
        self,
        controller: "WindowsHermesProcessController",
        handle: BinaryIO,
    ):
        self._controller = controller
        self._handle = handle
        self._released = False

    def validate(self) -> bool:
        if self._released or self._handle.closed:
            return False
        return self._controller._lease_is_valid(self)


class WindowsHermesProcessController:
    """Exact Windows process control for the two Hermes entrypoints."""

    def __init__(
        self,
        *,
        repo_root: str | Path | None = None,
        powershell_runner: Callable[..., subprocess.CompletedProcess[str]]
        | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.repo_root = Path(
            repo_root or Path(__file__).resolve().parents[3]
        ).resolve()
        self.python_path = (
            self.repo_root / ".venv" / "Scripts" / "python.exe"
        ).resolve()
        self.bot_path = (self.repo_root / "telegram_bot.py").resolve()
        self.worker_path = (
            self.repo_root / "scripts" / "run_job_worker.py"
        ).resolve()
        self.log_dir = (self.repo_root / "runtime_logs").resolve()
        self.lock_path = self.log_dir / ".hermes-offline.lock"
        self._powershell_runner = (
            powershell_runner or _default_powershell_runner
        )
        self._sleep = sleep
        self._target_processes: dict[int, _TargetProcess] = {}
        self._active_lease: _WindowsOfflineLease | None = None

    def discover(self) -> RuntimeState:
        snapshot = self._snapshot(timeout=15)
        self._target_processes = dict(snapshot.targets)
        return RuntimeState(
            bot_count=snapshot.bot_count,
            worker_count=snapshot.worker_count,
            unambiguous=snapshot.exactly_running,
        )

    def stop(self, state: RuntimeState, timeout_seconds: int) -> None:
        timeout = max(2, int(timeout_seconds))
        deadline = time.monotonic() + timeout
        if (
            not state.unambiguous
            or state.bot_count != 1
            or state.worker_count != 1
        ):
            raise RuntimeError("runtime state is not safe to stop")
        expected = dict(self._target_processes)
        if len(expected) != 2:
            raise RuntimeError("runtime discovery must precede stop")

        self._require_same_identities(
            expected,
            timeout=self._remaining_timeout(deadline),
        )
        self._stop_pids(
            sorted(expected),
            force=False,
            timeout=self._remaining_timeout(deadline),
        )
        remaining = self._snapshot(
            timeout=self._remaining_timeout(deadline)
        )
        if not remaining.exactly_stopped:
            remaining_expected = {
                pid: process
                for pid, process in expected.items()
                if pid in remaining.targets
            }
            if remaining.unexpected_count:
                raise RuntimeError("unexpected runtime process after stop")
            self._require_same_identities(
                remaining_expected,
                timeout=self._remaining_timeout(deadline),
            )
            self._stop_pids(
                sorted(remaining_expected),
                force=True,
                timeout=self._remaining_timeout(deadline),
            )

        final = self._snapshot(
            timeout=self._remaining_timeout(deadline)
        )
        if not final.exactly_stopped:
            raise RuntimeError("runtime did not stop within timeout")
        self._target_processes = {}

    def acquire_offline_lease(
        self,
        state: RuntimeState,
    ) -> OfflineAccessLease:
        if (
            not state.unambiguous
            or state.bot_count != 1
            or state.worker_count != 1
        ):
            raise RuntimeError("offline lease requires exact original state")
        if self._active_lease is not None:
            raise RuntimeError("offline lease is already active")
        self.log_dir.mkdir(parents=True, exist_ok=True)
        handle = self.lock_path.open("a+b")
        try:
            self._lock_handle(handle)
            lease = _WindowsOfflineLease(self, handle)
            self._active_lease = lease
            if not lease.validate():
                raise RuntimeError("runtime is not exactly stopped")
            return lease
        except Exception:
            self._active_lease = None
            self._unlock_and_close(handle)
            raise

    def release_offline_lease(self, lease: OfflineAccessLease) -> None:
        if lease is not self._active_lease or not isinstance(
            lease,
            _WindowsOfflineLease,
        ):
            raise RuntimeError("offline lease is not owned by this controller")
        lease._handle.seek(0)
        msvcrt.locking(lease._handle.fileno(), msvcrt.LK_UNLCK, 1)
        lease._handle.close()
        lease._released = True
        self._active_lease = None

    def start(self, state: RuntimeState) -> RuntimeState:
        if self._active_lease is not None:
            raise RuntimeError("cannot start while offline lease is active")
        if (
            not state.unambiguous
            or state.bot_count != 1
            or state.worker_count != 1
        ):
            raise RuntimeError("restart requires exact original state")
        self._assert_runtime_files()
        guard = self._acquire_runtime_guard()
        try:
            if not self._snapshot(timeout=15).exactly_stopped:
                raise RuntimeError(
                    "runtime must be exactly stopped before restart"
                )
            self.log_dir.mkdir(parents=True, exist_ok=True)
            payload = self._invoke(
                _START_COMMAND,
                timeout=15,
                env={
                    "HERMES_RUNTIME_PYTHON": str(self.python_path),
                    "HERMES_RUNTIME_BOT": str(self.bot_path),
                    "HERMES_RUNTIME_WORKER": str(self.worker_path),
                    "HERMES_RUNTIME_CWD": str(self.repo_root),
                    "HERMES_RUNTIME_BOT_STDOUT": str(
                        self.log_dir / "telegram_bot.stdout.log"
                    ),
                    "HERMES_RUNTIME_BOT_STDERR": str(
                        self.log_dir / "telegram_bot.stderr.log"
                    ),
                    "HERMES_RUNTIME_WORKER_STDOUT": str(
                        self.log_dir / "worker.stdout.log"
                    ),
                    "HERMES_RUNTIME_WORKER_STDERR": str(
                        self.log_dir / "worker.stderr.log"
                    ),
                    "PYTHONUTF8": "1",
                },
            )
            if payload.get("ok") is not True:
                raise RuntimeError("runtime restart failed")
            restarted = self._snapshot(timeout=15)
        finally:
            self._unlock_and_close(guard)
        self._target_processes = dict(restarted.targets)
        return RuntimeState(
            restarted.bot_count,
            restarted.worker_count,
            restarted.exactly_running,
        )

    def verify(self, state: RuntimeState) -> dict[str, bool]:
        if not state.unambiguous:
            return {"bot": False, "worker": False}
        snapshot = self._snapshot(timeout=15)
        return {
            "bot": snapshot.exactly_running and snapshot.bot_count == 1,
            "worker": snapshot.exactly_running
            and snapshot.worker_count == 1,
        }

    def _snapshot(self, *, timeout: int) -> _ProcessSnapshot:
        payload = self._invoke(_DISCOVER_COMMAND, timeout=timeout)
        raw_processes = payload.get("processes", [])
        if raw_processes is None:
            raw_processes = []
        if not isinstance(raw_processes, list):
            raw_processes = [raw_processes]
        targets: dict[int, _TargetProcess] = {}
        unexpected = 0
        for raw in raw_processes:
            if not isinstance(raw, dict):
                unexpected += 1
                continue
            process, mentions_target = self._classify_process(raw)
            if process is not None:
                if process.pid in targets:
                    unexpected += 1
                targets[process.pid] = process
            elif mentions_target:
                unexpected += 1
        return _ProcessSnapshot(targets, unexpected)

    def _classify_process(
        self,
        raw: dict[str, object],
    ) -> tuple[_TargetProcess | None, bool]:
        command_line = str(raw.get("CommandLine") or "")
        folded = command_line.casefold()
        mentions_target = (
            "telegram_bot.py" in folded
            or "run_job_worker.py" in folded
        )
        try:
            pid = int(raw["ProcessId"])
            executable = self._normalize_runtime_path(
                str(raw["ExecutablePath"])
            )
            args = _split_command_line(command_line)
        except (KeyError, TypeError, ValueError, RuntimeError):
            return None, mentions_target
        if (
            pid <= 0
            or executable != _normalized_path(self.python_path)
            or len(args) != 2
            or self._normalize_runtime_path(args[0])
            != _normalized_path(self.python_path)
        ):
            return None, mentions_target
        script = self._normalize_runtime_path(args[1])
        roles = {
            _normalized_path(self.bot_path): "bot",
            _normalized_path(self.worker_path): "worker",
        }
        role = roles.get(script)
        if role is None:
            return None, mentions_target
        return _TargetProcess(pid, role, executable, script), True

    def _normalize_runtime_path(self, value: str) -> str:
        path = Path(value)
        if not path.is_absolute():
            path = self.repo_root / path
        return _normalized_path(path)

    def _require_same_identities(
        self,
        expected: dict[int, _TargetProcess],
        *,
        timeout: int,
    ) -> None:
        if not expected:
            return
        current = self._snapshot(timeout=timeout)
        for pid, process in expected.items():
            if current.targets.get(pid) != process:
                raise RuntimeError("runtime PID identity changed before stop")
        if current.unexpected_count:
            raise RuntimeError("unexpected runtime process identity")

    def _stop_pids(
        self,
        pids: list[int],
        *,
        force: bool,
        timeout: int,
    ) -> None:
        if not pids:
            return
        payload = self._invoke(
            _FORCE_STOP_COMMAND if force else _STOP_COMMAND,
            timeout=max(1, timeout),
            env={"HERMES_RUNTIME_PIDS": json.dumps(pids)},
        )
        if payload.get("ok") is not True:
            raise RuntimeError("runtime stop command failed")

    def _lease_is_valid(self, lease: _WindowsOfflineLease) -> bool:
        if lease is not self._active_lease:
            return False
        try:
            return self._snapshot(timeout=15).exactly_stopped
        except Exception:
            return False

    def _assert_runtime_files(self) -> None:
        for path in (self.python_path, self.bot_path, self.worker_path):
            if not path.is_file():
                raise RuntimeError("required Hermes runtime file is missing")

    def _acquire_runtime_guard(self) -> BinaryIO:
        self.log_dir.mkdir(parents=True, exist_ok=True)
        handle = self.lock_path.open("a+b")
        try:
            self._lock_handle(handle)
        except OSError as exc:
            handle.close()
            raise RuntimeError("offline lease is held by another process") from exc
        return handle

    @staticmethod
    def _remaining_timeout(deadline: float) -> int:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise RuntimeError("runtime stop exceeded timeout")
        return max(1, math.ceil(remaining))

    @staticmethod
    def _lock_handle(handle: BinaryIO) -> None:
        handle.seek(0)
        if handle.read(1) == b"":
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)

    @staticmethod
    def _unlock_and_close(handle: BinaryIO) -> None:
        if handle.closed:
            return
        try:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
        finally:
            handle.close()

    def _invoke(
        self,
        command: str,
        *,
        timeout: int,
        env: dict[str, str] | None = None,
    ) -> dict[str, object]:
        child_env = dict(os.environ)
        if env:
            child_env.update(env)
        result = self._powershell_runner(
            command,
            env=child_env,
            timeout=max(1, int(timeout)),
        )
        if result.returncode != 0:
            raise RuntimeError("PowerShell runtime command failed")
        try:
            payload = json.loads(result.stdout)
        except (TypeError, json.JSONDecodeError) as exc:
            raise RuntimeError("PowerShell returned invalid JSON") from exc
        if not isinstance(payload, dict) or payload.get("ok") is not True:
            raise RuntimeError("PowerShell runtime command was not successful")
        return payload


__all__ = ["WindowsHermesProcessController"]
