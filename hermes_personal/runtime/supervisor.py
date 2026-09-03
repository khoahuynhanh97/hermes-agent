from __future__ import annotations

import abc
import json
import os
import signal
import socket
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Sequence
from urllib.parse import urlparse

from hermes_personal.observability.health import ComponentHealth, HealthReport, HealthStatus
from hermes_personal.observability.redaction import redact
from hermes_personal.runtime.processes import ProcessSpec, RestartPolicy


class ChildProcess(abc.ABC):
    """Abstract interface for a supervised child process."""

    @property
    @abc.abstractmethod
    def name(self) -> str:
        pass

    @property
    @abc.abstractmethod
    def pid(self) -> int:
        pass

    @abc.abstractmethod
    def poll(self) -> int | None:
        pass

    @abc.abstractmethod
    def terminate(self) -> None:
        pass

    @abc.abstractmethod
    def kill(self) -> None:
        pass

    @abc.abstractmethod
    def wait(self, timeout: float | None = None) -> int:
        pass

    @abc.abstractmethod
    def is_alive(self) -> bool:
        pass


class SubprocessChild(ChildProcess):
    """Concrete ChildProcess wrapper around standard subprocess.Popen."""

    def __init__(self, name: str, process: subprocess.Popen):
        self._name = name
        self._process = process

    @property
    def name(self) -> str:
        return self._name

    @property
    def pid(self) -> int:
        return self._process.pid

    def poll(self) -> int | None:
        return self._process.poll()

    def terminate(self) -> None:
        """Stage 1: Graceful termination request."""
        if os.name == "nt":
            try:
                self._process.send_signal(signal.CTRL_BREAK_EVENT)
            except Exception:
                try:
                    subprocess.run(
                        ["taskkill", "/T", "/PID", str(self._process.pid)],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        check=False,
                    )
                except Exception:
                    self._process.terminate()
        else:
            self._process.terminate()

    def kill(self) -> None:
        """Stage 2: Forceful kill of the process tree after shutdown timeout expires."""
        if os.name == "nt":
            try:
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(self._process.pid)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
            except Exception:
                self._process.kill()
        else:
            self._process.kill()

    def wait(self, timeout: float | None = None) -> int:
        return self._process.wait(timeout=timeout)

    def is_alive(self) -> bool:
        return self._process.poll() is None


class ProcessRunner(abc.ABC):
    """Abstract interface for starting child processes without shell interpolation."""

    @abc.abstractmethod
    def start(self, spec: ProcessSpec, env: dict[str, str] | None = None) -> ChildProcess:
        pass


class DefaultProcessRunner(ProcessRunner):
    """Concrete ProcessRunner executing subprocess.Popen with shell=False."""

    def start(self, spec: ProcessSpec, env: dict[str, str] | None = None) -> ChildProcess:
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
        popen = subprocess.Popen(
            list(spec.argv),
            cwd=str(spec.cwd),
            env=env,
            shell=False,
            stdin=subprocess.DEVNULL,
            stdout=None,
            stderr=None,
            creationflags=creationflags,
        )
        return SubprocessChild(name=spec.name, process=popen)


class SupervisorStartError(RuntimeError):
    """Raised when a process cannot start or pass its readiness probe."""


class SupervisorShutdownError(RuntimeError):
    """Raised when a child cannot be reaped during supervisor shutdown."""


ProbeRunner = Callable[[ProcessSpec, ChildProcess], bool]


@dataclass(frozen=True)
class SupervisorEvent:
    """Event emitted during supervisor lifecycle."""

    timestamp: float
    event_type: str
    process_name: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class ProcessState:
    spec: ProcessSpec
    child: ChildProcess | None = None
    status: HealthStatus = "starting"
    restart_attempts: list[float] = field(default_factory=list)
    last_exit_code: int | None = None


def probe_video_factory_stdio(
    executable: str | None = None,
    timeout_seconds: float = 5.0,
) -> bool:
    """Lightweight readiness probe verifying Video Factory responds to stdio MCP discovery."""
    import sys

    py_exec = executable or sys.executable
    cmd = [py_exec, "-m", "hermes_personal.integrations.video_factory.server"]
    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        init_req = (
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "clientInfo": {"name": "supervisor-probe", "version": "1.0"},
                    },
                }
            )
            + "\n"
        )
        tools_req = (
            json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
            + "\n"
        )
        stdout, _ = proc.communicate(init_req + tools_req, timeout=timeout_seconds)
        for line in stdout.strip().splitlines():
            try:
                data = json.loads(line)
                if data.get("id") == 1 and "result" in data:
                    return True
                if (
                    data.get("id") == 2
                    and "result" in data
                    and "tools" in data["result"]
                ):
                    return True
            except json.JSONDecodeError:
                continue
        return False
    except Exception:
        return False


class Supervisor:
    """Supervises the Hermes process topology with bounded exponential backoff and graceful shutdown."""

    def __init__(
        self,
        specs: Sequence[ProcessSpec],
        runner: ProcessRunner,
        clock: Callable[[], float] = time.time,
        sleep_fn: Callable[[float], None] = time.sleep,
        on_event: Callable[[SupervisorEvent], None] | None = None,
        on_health_update: Callable[[HealthReport], None] | None = None,
        probe_runner: ProbeRunner | None = None,
    ) -> None:
        self._specs = tuple(specs)
        self._runner = runner
        self._clock = clock
        self._sleep = sleep_fn
        self._on_event = on_event
        self._on_health_update = on_health_update
        self._probe_runner = probe_runner
        self._states: dict[str, ProcessState] = {s.name: ProcessState(spec=s) for s in self._specs}
        self._stop_requested = False

    def _emit(self, event_type: str, process_name: str, details: dict[str, Any] | None = None) -> None:
        if self._on_event:
            event = SupervisorEvent(
                timestamp=self._clock(),
                event_type=event_type,
                process_name=process_name,
                details=redact(details or {}),
            )
            self._on_event(event)

    def _update_health(self) -> None:
        if self._on_health_update:
            comps = [
                ComponentHealth(
                    name=st.spec.name,
                    required=st.spec.required,
                    status=st.status,
                )
                for st in self._states.values()
            ]
            report = HealthReport.from_components(comps)
            self._on_health_update(report)

    def start_all(self) -> None:
        """Start all processes in declared forward order."""
        try:
            for spec in self._specs:
                self._start_process(spec.name)
        except SupervisorStartError:
            self._update_health()
            self.stop_all()
            raise
        self._update_health()

    def _start_process(self, name: str) -> None:
        st = self._states[name]
        try:
            inherited_keys = {
                "PATH",
                "PATHEXT",
                "SYSTEMROOT",
                "WINDIR",
                "COMSPEC",
                "TEMP",
                "TMP",
                "HOME",
                "USERPROFILE",
                "APPDATA",
                "LOCALAPPDATA",
                "PYTHONPATH",
            }
            allowed_keys = inherited_keys.union(st.spec.env_keys)
            child_env = {
                key: value for key, value in os.environ.items() if key.upper() in allowed_keys
            }
            try:
                child = self._runner.start(st.spec, child_env)
            except TypeError:
                # Compatibility for legacy test runners that predate env.
                child = self._runner.start(st.spec)
        except Exception as exc:
            st.status = "degraded" if not st.spec.required else "unavailable"
            self._emit("start_failed", name, {"required": st.spec.required})
            if st.spec.required:
                raise SupervisorStartError(f"failed to start required process '{name}'") from exc
            return

        st.child = child
        if not self._wait_for_readiness(st.spec, child):
            st.status = "degraded" if not st.spec.required else "unavailable"
            self._emit(
                "probe_failed",
                name,
                {"probe_type": st.spec.readiness_probe.probe_type, "required": st.spec.required},
            )
            self._stop_child(st, final_status=st.status)
            if st.spec.required:
                raise SupervisorStartError(f"required readiness probe failed for '{name}'")
            return

        st.status = "healthy"
        self._emit("started", name, {"pid": child.pid})

    def _wait_for_readiness(self, spec: ProcessSpec, child: ChildProcess) -> bool:
        probe = spec.readiness_probe
        if probe.initial_delay_seconds > 0:
            self._sleep(probe.initial_delay_seconds)

        if self._stop_requested or child.poll() is not None:
            return False

        if self._probe_runner is not None:
            try:
                if not bool(self._probe_runner(spec, child)):
                    return False
            except Exception:
                return False
            return child.poll() is None

        return self._run_builtin_probe(spec, child)

    @staticmethod
    def _probe_deadline(timeout_seconds: float) -> float:
        return time.monotonic() + max(0.0, timeout_seconds)

    def _run_builtin_probe(self, spec: ProcessSpec, child: ChildProcess) -> bool:
        probe = spec.readiness_probe
        deadline = self._probe_deadline(probe.timeout_seconds)
        if child.poll() is not None:
            return False

        if probe.probe_type == "noop" or probe.probe_type == "exec":
            if probe.endpoint == "video_factory_stdio" or "video_factory" in probe.endpoint:
                return probe_video_factory_stdio(timeout_seconds=probe.timeout_seconds) and child.is_alive()
            return child.is_alive()

        if probe.probe_type == "http":
            while time.monotonic() <= deadline:
                if child.poll() is not None:
                    return False
                remaining = max(0.0, deadline - time.monotonic())
                if remaining <= 0:
                    break
                try:
                    with urllib.request.urlopen(
                        probe.endpoint, timeout=remaining
                    ) as response:
                        status = getattr(response, "status", None)
                        if status is None:
                            status = response.getcode()
                        if 200 <= status < 400:
                            return child.is_alive()
                except (OSError, TimeoutError, urllib.error.URLError, ValueError):
                    pass
                remaining = deadline - time.monotonic()
                if remaining > 0:
                    self._sleep(min(max(0.001, probe.interval_seconds), remaining))
            return False

        if probe.probe_type == "tcp":
            endpoint = probe.endpoint
            parsed = urlparse(endpoint if "://" in endpoint else f"tcp://{endpoint}")
            if not parsed.hostname or parsed.port is None:
                return False
            while time.monotonic() <= deadline:
                if child.poll() is not None:
                    return False
                remaining = max(0.0, deadline - time.monotonic())
                if remaining <= 0:
                    break
                try:
                    with socket.create_connection(
                        (parsed.hostname, parsed.port), timeout=remaining
                    ):
                        return child.is_alive()
                except (OSError, TimeoutError, ValueError):
                    pass
                remaining = deadline - time.monotonic()
                if remaining > 0:
                    self._sleep(min(max(0.001, probe.interval_seconds), remaining))
            return False

        if probe.probe_type == "file":
            marker = Path(probe.endpoint)
            while time.monotonic() <= deadline:
                if child.poll() is not None:
                    return False
                if marker.is_file():
                    return child.is_alive()
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                self._sleep(min(max(0.0, probe.interval_seconds), remaining))
            return False

        return False

    def get_process_status(self, name: str) -> HealthStatus:
        return self._states[name].status

    def step(self) -> int:
        """Perform one supervision tick checking all child processes. Returns nonzero if a required process failed."""
        now = self._clock()

        for st in self._states.values():
            if st.child is None:
                continue

            exit_code = st.child.poll()
            if exit_code is not None:
                # Unexpected process exit
                st.last_exit_code = exit_code
                self._emit("exited", st.spec.name, {"exit_code": exit_code})
                try:
                    st.child.wait(timeout=0)
                except Exception:
                    pass

                # Filter restart attempts within time window
                cutoff = now - st.spec.restart.window_seconds
                st.restart_attempts = [t for t in st.restart_attempts if t >= cutoff]

                if len(st.restart_attempts) >= st.spec.restart.max_attempts:
                    self._emit("exhausted", st.spec.name, {"attempts": len(st.restart_attempts)})
                    st.status = "unavailable"
                    if st.spec.required:
                        # Required process exhausted -> initiate stop and return non-zero
                        self._update_health()
                        return 1
                    else:
                        st.status = "degraded"
                else:
                    # Compute exponential backoff
                    attempts = len(st.restart_attempts)
                    backoff = min(
                        st.spec.restart.base_backoff_seconds * (2 ** attempts),
                        st.spec.restart.max_backoff_seconds,
                    )
                    st.restart_attempts.append(now)
                    self._emit("restarting", st.spec.name, {"backoff_seconds": backoff, "attempt": attempts + 1})
                    self._sleep(backoff)
                    if self._stop_requested:
                        continue
                    try:
                        self._start_process(st.spec.name)
                    except SupervisorStartError:
                        if st.spec.required:
                            self._update_health()
                            return 1

        self._update_health()
        return 0

    def stop_all(self) -> None:
        """Gracefully stop all running processes in reverse order."""
        self._stop_requested = True
        failures: list[str] = []
        for spec in reversed(self._specs):
            st = self._states[spec.name]
            if st.child is None:
                continue
            try:
                final_status = st.status if st.status in ("degraded", "unavailable") else "stopped"
                self._stop_child(st, final_status=final_status)
            except SupervisorShutdownError:
                failures.append(spec.name)

        self._update_health()
        if failures:
            raise SupervisorShutdownError(f"failed to reap child process(es): {', '.join(failures)}")

    def _stop_child(self, st: ProcessState, final_status: HealthStatus = "stopped") -> None:
        child = st.child
        if child is None:
            return

        if child.is_alive():
            self._emit("stopping", st.spec.name)
            st.status = "stopping"
            try:
                child.terminate()
            except Exception:
                pass

        try:
            child.wait(timeout=st.spec.shutdown_timeout_seconds)
        except Exception:
            pass

        if child.is_alive():
            self._emit("killing", st.spec.name)
            try:
                child.kill()
            except Exception:
                pass
            try:
                child.wait(timeout=st.spec.shutdown_timeout_seconds)
            except Exception:
                pass

        if child.is_alive():
            self._emit("reap_failed", st.spec.name)
            raise SupervisorShutdownError(f"failed to reap child process '{st.spec.name}'")

        st.status = final_status
        self._emit("stopped", st.spec.name)

    def run(self, max_ticks: int | None = None) -> int:
        """Run supervisor until completion or failure."""
        try:
            self.start_all()
        except SupervisorStartError:
            return 1
        ticks = 0
        while not self._stop_requested:
            exit_code = self.step()
            if exit_code != 0:
                self.stop_all()
                return exit_code
            ticks += 1
            if max_ticks is not None and ticks >= max_ticks:
                break
        self.stop_all()
        return 0

    def request_stop(self) -> None:
        self._stop_requested = True
