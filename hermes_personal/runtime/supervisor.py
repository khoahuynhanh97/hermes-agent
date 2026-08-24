from __future__ import annotations

import abc
import subprocess
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

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
        self._process.terminate()

    def kill(self) -> None:
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
        popen = subprocess.Popen(
            list(spec.argv),
            cwd=str(spec.cwd),
            env=env,
            shell=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return SubprocessChild(name=spec.name, process=popen)


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
    ) -> None:
        self._specs = tuple(specs)
        self._runner = runner
        self._clock = clock
        self._sleep = sleep_fn
        self._on_event = on_event
        self._on_health_update = on_health_update
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
        for spec in self._specs:
            self._start_process(spec.name)
        self._update_health()

    def _start_process(self, name: str) -> None:
        st = self._states[name]
        child = self._runner.start(st.spec)
        st.child = child
        st.status = "healthy"
        self._emit("started", name, {"pid": child.pid})

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
                    self._start_process(st.spec.name)

        self._update_health()
        return 0

    def stop_all(self) -> None:
        """Gracefully stop all running processes in reverse order."""
        for spec in reversed(self._specs):
            st = self._states[spec.name]
            if st.child and st.child.is_alive():
                self._emit("stopping", spec.name)
                st.status = "stopping"
                st.child.terminate()
                # Wait with timeout
                try:
                    st.child.wait(timeout=spec.shutdown_timeout_seconds)
                except Exception:
                    pass

                # If still alive, forced kill
                if st.child.is_alive():
                    self._emit("killing", spec.name)
                    st.child.kill()

                st.status = "stopped"
                self._emit("stopped", spec.name)

        self._update_health()

    def run(self, max_ticks: int | None = None) -> int:
        """Run supervisor until completion or failure."""
        self.start_all()
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
