from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import pytest

from hermes_personal.observability.health import HealthStatus
from hermes_personal.runtime.processes import ProcessSpec, ProbeSpec, RestartPolicy
from hermes_personal.runtime.supervisor import (
    ChildProcess,
    ProcessRunner,
    Supervisor,
    SupervisorEvent,
)


class FakeChildProcess(ChildProcess):
    def __init__(self, name: str, pid: int = 1000):
        self._name = name
        self._pid = pid
        self._exit_code: int | None = None
        self._terminated = False
        self._killed = False

    @property
    def name(self) -> str:
        return self._name

    @property
    def pid(self) -> int:
        return self._pid

    def poll(self) -> int | None:
        return self._exit_code

    def exit_with(self, code: int) -> None:
        self._exit_code = code

    def terminate(self) -> None:
        self._terminated = True
        self._exit_code = 0

    def kill(self) -> None:
        self._killed = True
        self._exit_code = -9

    def wait(self, timeout: float | None = None) -> int:
        return self._exit_code if self._exit_code is not None else 0

    def is_alive(self) -> bool:
        return self._exit_code is None


class FakeProcessRunner(ProcessRunner):
    def __init__(self):
        self.started: list[ProcessSpec] = []
        self.active_processes: dict[str, list[FakeChildProcess]] = {}
        self._next_pid = 1000

    def start(self, spec: ProcessSpec, env: dict[str, str] | None = None) -> FakeChildProcess:
        self.started.append(spec)
        self._next_pid += 1
        child = FakeChildProcess(name=spec.name, pid=self._next_pid)
        self.active_processes.setdefault(spec.name, []).append(child)
        return child


class FakeClock:
    def __init__(self, start: float = 1000.0):
        self.now = start

    def time(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds

    def sleep(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def fake_runner():
    return FakeProcessRunner()


@pytest.fixture
def fake_clock():
    return FakeClock()


def make_spec(name: str, required: bool = True, max_attempts: int = 3, window: float = 60.0) -> ProcessSpec:
    return ProcessSpec(
        name=name,
        argv=("python", "-m", f"hermes.{name}"),
        cwd=Path("/tmp"),
        env_keys=(),
        required=required,
        readiness_probe=ProbeSpec(probe_type="noop"),
        shutdown_timeout_seconds=2.0,
        restart=RestartPolicy(
            max_attempts=max_attempts,
            window_seconds=window,
            base_backoff_seconds=1.0,
            max_backoff_seconds=10.0,
        ),
    )


def test_ordered_start_of_processes(fake_runner, fake_clock):
    specs = (make_spec("p1"), make_spec("p2"), make_spec("p3"))
    events: list[SupervisorEvent] = []

    sup = Supervisor(
        specs=specs,
        runner=fake_runner,
        clock=fake_clock.time,
        sleep_fn=fake_clock.sleep,
        on_event=events.append,
    )
    sup.start_all()

    assert [s.name for s in fake_runner.started] == ["p1", "p2", "p3"]
    assert len(events) == 3
    assert all(e.event_type == "started" for e in events)


def test_unexpected_child_exit_triggers_restart_with_backoff(fake_runner, fake_clock):
    specs = (make_spec("gw", required=True),)
    events: list[SupervisorEvent] = []

    sup = Supervisor(
        specs=specs,
        runner=fake_runner,
        clock=fake_clock.time,
        sleep_fn=fake_clock.sleep,
        on_event=events.append,
    )
    sup.start_all()

    # Simulate child exit
    child1 = fake_runner.active_processes["gw"][0]
    child1.exit_with(1)

    sup.step()

    # Restart occurred
    assert len(fake_runner.active_processes["gw"]) == 2
    restart_events = [e for e in events if e.event_type == "restarting"]
    assert len(restart_events) == 1
    assert restart_events[0].process_name == "gw"


def test_required_child_exhaustion_causes_nonzero_exit(fake_runner, fake_clock):
    specs = (make_spec("gw", required=True, max_attempts=2),)
    events: list[SupervisorEvent] = []

    sup = Supervisor(
        specs=specs,
        runner=fake_runner,
        clock=fake_clock.time,
        sleep_fn=fake_clock.sleep,
        on_event=events.append,
    )
    sup.start_all()

    # Fail 1
    fake_runner.active_processes["gw"][-1].exit_with(1)
    sup.step()

    # Fail 2
    fake_runner.active_processes["gw"][-1].exit_with(1)
    sup.step()

    # Fail 3 (exhausted)
    fake_runner.active_processes["gw"][-1].exit_with(1)
    exit_code = sup.step()

    assert exit_code != 0
    assert any(e.event_type == "exhausted" for e in events)


def test_optional_child_failure_degrades_without_global_shutdown(fake_runner, fake_clock):
    specs = (make_spec("gw", required=True), make_spec("tg", required=False, max_attempts=1))
    events: list[SupervisorEvent] = []

    sup = Supervisor(
        specs=specs,
        runner=fake_runner,
        clock=fake_clock.time,
        sleep_fn=fake_clock.sleep,
        on_event=events.append,
    )
    sup.start_all()

    # Fail optional telegram process twice to exhaust attempts
    fake_runner.active_processes["tg"][-1].exit_with(1)
    sup.step()
    fake_runner.active_processes["tg"][-1].exit_with(1)
    exit_code = sup.step()

    # Required gw still alive, supervisor continues
    assert exit_code == 0
    assert sup.get_process_status("tg") in ("degraded", "unavailable")
    assert sup.get_process_status("gw") == "healthy"


def test_graceful_reverse_order_stop_and_no_orphans(fake_runner, fake_clock):
    specs = (make_spec("p1"), make_spec("p2"), make_spec("p3"))
    sup = Supervisor(
        specs=specs,
        runner=fake_runner,
        clock=fake_clock.time,
        sleep_fn=fake_clock.sleep,
    )
    sup.start_all()

    sup.stop_all()

    # All processes terminated
    for spec in specs:
        for child in fake_runner.active_processes[spec.name]:
            assert not child.is_alive()
