from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import socket
from unittest.mock import patch

import pytest

from hermes_personal.runtime.processes import ProcessSpec, ProbeSpec, RestartPolicy
from hermes_personal.runtime.supervisor import (
    ChildProcess,
    DefaultProcessRunner,
    ProcessRunner,
    Supervisor,
    SupervisorStartError,
    SupervisorEvent,
)


class FakeChildProcess(ChildProcess):
    def __init__(self, name: str, pid: int = 1000, stubborn: bool = False):
        self._name = name
        self._pid = pid
        self._exit_code: int | None = None
        self._terminated = False
        self._killed = False
        self._stubborn = stubborn
        self.wait_calls: list[float | None] = []

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
        if not self._stubborn:
            self._exit_code = 0

    def kill(self) -> None:
        self._killed = True
        self._exit_code = -9

    def wait(self, timeout: float | None = None) -> int:
        self.wait_calls.append(timeout)
        if self._stubborn and not self._killed:
            raise TimeoutError(f"Process {self._name} timed out during graceful shutdown")
        return self._exit_code if self._exit_code is not None else 0

    def is_alive(self) -> bool:
        return self._exit_code is None


class FakeProcessRunner(ProcessRunner):
    def __init__(self):
        self.started: list[ProcessSpec] = []
        self.environments: list[dict[str, str] | None] = []
        self.active_processes: dict[str, list[FakeChildProcess]] = {}
        self._next_pid = 1000
        self.stubborn_names: set[str] = set()

    def start(self, spec: ProcessSpec, env: dict[str, str] | None = None) -> FakeChildProcess:
        self.started.append(spec)
        self.environments.append(env)
        self._next_pid += 1
        stubborn = spec.name in self.stubborn_names
        child = FakeChildProcess(name=spec.name, pid=self._next_pid, stubborn=stubborn)
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


def make_spec(
    name: str,
    required: bool = True,
    max_attempts: int = 3,
    window: float = 60.0,
    base_backoff: float = 1.0,
    max_backoff: float = 10.0,
    probe: ProbeSpec | None = None,
) -> ProcessSpec:
    return ProcessSpec(
        name=name,
        argv=("python", "-m", f"hermes.{name}"),
        cwd=Path("/tmp"),
        env_keys=(),
        required=required,
        readiness_probe=probe or ProbeSpec(probe_type="noop"),
        shutdown_timeout_seconds=2.0,
        restart=RestartPolicy(
            max_attempts=max_attempts,
            window_seconds=window,
            base_backoff_seconds=base_backoff,
            max_backoff_seconds=max_backoff,
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


def test_supervisor_passes_declared_runtime_environment(fake_runner, fake_clock, monkeypatch):
    monkeypatch.setenv("HERMES_API_KEY", "runtime-secret")
    spec = replace(make_spec("gateway"), env_keys=("HERMES_API_KEY",))

    Supervisor(
        specs=(spec,),
        runner=fake_runner,
        clock=fake_clock.time,
        sleep_fn=fake_clock.sleep,
    ).start_all()

    assert fake_runner.environments[0]["HERMES_API_KEY"] == "runtime-secret"


def test_builtin_http_probe_retries_until_service_is_ready(fake_runner, fake_clock):
    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    spec = make_spec(
        "http_service",
        probe=ProbeSpec(
            probe_type="http",
            endpoint="http://127.0.0.1/healthz",
            initial_delay_seconds=0.0,
            interval_seconds=0.001,
            timeout_seconds=0.1,
        ),
    )
    with patch(
        "urllib.request.urlopen",
        side_effect=[ConnectionRefusedError(), Response()],
    ) as probe:
        Supervisor(
            specs=(spec,),
            runner=fake_runner,
            clock=fake_clock.time,
            sleep_fn=lambda _: None,
        ).start_all()

    assert probe.call_count == 2


def test_default_runner_inherits_child_streams_without_shell(monkeypatch):
    calls = {}

    class FakePopen:
        pid = 4242

        def poll(self):
            return None

        def terminate(self):
            pass

        def kill(self):
            pass

        def wait(self, timeout=None):
            return 0

    def fake_popen(*args, **kwargs):
        calls["args"] = args
        calls["kwargs"] = kwargs
        return FakePopen()

    monkeypatch.setattr("hermes_personal.runtime.supervisor.subprocess.Popen", fake_popen)

    DefaultProcessRunner().start(make_spec("worker"))

    assert calls["kwargs"]["shell"] is False
    assert calls["kwargs"]["stdout"] is None
    assert calls["kwargs"]["stderr"] is None
    assert "secret" not in repr(calls)


def test_builtin_file_probe_must_pass_before_process_is_healthy(fake_runner, fake_clock, tmp_path):
    marker = tmp_path / "ready"
    marker.write_text("ok", encoding="utf-8")
    spec = make_spec(
        "file_service",
        probe=ProbeSpec(
            probe_type="file",
            endpoint=str(marker),
            initial_delay_seconds=0.0,
            timeout_seconds=0.01,
        ),
    )

    Supervisor(
        specs=(spec,),
        runner=fake_runner,
        clock=fake_clock.time,
        sleep_fn=fake_clock.sleep,
    ).start_all()

    assert fake_runner.active_processes["file_service"][-1].is_alive()


def test_probe_timeout_is_reported_as_required_start_failure(fake_runner, fake_clock):
    spec = make_spec(
        "http_service",
        probe=ProbeSpec(
            probe_type="http",
            endpoint="http://127.0.0.1:1/healthz",
            initial_delay_seconds=0.0,
            timeout_seconds=0.01,
        ),
    )
    with patch("urllib.request.urlopen", side_effect=TimeoutError):
        sup = Supervisor(
            specs=(spec,),
            runner=fake_runner,
            clock=fake_clock.time,
            sleep_fn=fake_clock.sleep,
        )
        with pytest.raises(SupervisorStartError, match="http_service"):
            sup.start_all()

    assert not fake_runner.active_processes["http_service"][-1].is_alive()


def test_builtin_http_probe_accepts_success_response_status(fake_runner, fake_clock):
    class Response:
        status = 204

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    spec = make_spec(
        "http_service",
        probe=ProbeSpec(
            probe_type="http",
            endpoint="http://127.0.0.1/healthz",
            initial_delay_seconds=0.0,
            timeout_seconds=1.0,
        ),
    )
    with patch("urllib.request.urlopen", return_value=Response()):
        Supervisor(
            specs=(spec,),
            runner=fake_runner,
            clock=fake_clock.time,
            sleep_fn=fake_clock.sleep,
        ).start_all()


def test_builtin_tcp_probe_connects_to_ready_listener(fake_runner, fake_clock):
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    try:
        host, port = listener.getsockname()
        spec = make_spec(
            "tcp_service",
            probe=ProbeSpec(
                probe_type="tcp",
                endpoint=f"tcp://{host}:{port}",
                initial_delay_seconds=0.0,
                timeout_seconds=1.0,
            ),
        )
        Supervisor(
            specs=(spec,),
            runner=fake_runner,
            clock=fake_clock.time,
            sleep_fn=fake_clock.sleep,
        ).start_all()
    finally:
        listener.close()


def test_injected_probe_runner_controls_readiness_for_all_probe_types(fake_runner, fake_clock, tmp_path):
    probe_types = ("noop", "http", "tcp", "file")
    seen = []

    def probe_runner(spec, child):
        seen.append((spec.name, spec.readiness_probe.probe_type, child.pid))
        return True

    specs = tuple(
        make_spec(
            f"service_{probe_type}",
            probe=ProbeSpec(probe_type=probe_type, endpoint=str(tmp_path / "ready")),
        )
        for probe_type in probe_types
    )
    Supervisor(
        specs=specs,
        runner=fake_runner,
        probe_runner=probe_runner,
        clock=fake_clock.time,
        sleep_fn=fake_clock.sleep,
    ).start_all()

    assert [item[1] for item in seen] == list(probe_types)
    assert all(fake_runner.active_processes[spec.name][-1].is_alive() for spec in specs)


def test_required_probe_failure_stops_prior_children_and_optional_failure_degrades(fake_runner, fake_clock):
    specs = (
        make_spec("required_ok"),
        make_spec("optional_bad", required=False),
        make_spec("required_bad"),
    )

    def probe_runner(spec, child):
        return spec.name not in {"optional_bad", "required_bad"}

    sup = Supervisor(
        specs=specs,
        runner=fake_runner,
        probe_runner=probe_runner,
        clock=fake_clock.time,
        sleep_fn=fake_clock.sleep,
    )
    with pytest.raises(SupervisorStartError, match="required_bad"):
        sup.start_all()

    assert sup.get_process_status("optional_bad") == "degraded"
    assert all(not children[-1].is_alive() for children in fake_runner.active_processes.values())


def test_child_exit_before_probe_is_a_probe_failure(fake_runner, fake_clock):
    spec = make_spec("early_exit")
    probe_calls = []

    def probe_runner(_spec, _child):
        probe_calls.append(True)
        return True

    original_start = fake_runner.start

    def start_and_exit(start_spec):
        child = original_start(start_spec)
        child.exit_with(1)
        return child

    fake_runner.start = start_and_exit
    sup = Supervisor(
        specs=(spec,),
        runner=fake_runner,
        probe_runner=probe_runner,
        clock=fake_clock.time,
        sleep_fn=fake_clock.sleep,
    )

    with pytest.raises(SupervisorStartError, match="early_exit"):
        sup.start_all()
    assert probe_calls == []


def test_child_exit_during_probe_is_not_marked_healthy(fake_runner, fake_clock):
    spec = make_spec("probe_exit")

    def probe_runner(_spec, child):
        child.exit_with(1)
        return True

    sup = Supervisor(
        specs=(spec,),
        runner=fake_runner,
        probe_runner=probe_runner,
        clock=fake_clock.time,
        sleep_fn=fake_clock.sleep,
    )

    with pytest.raises(SupervisorStartError, match="probe_exit"):
        sup.start_all()


def test_request_stop_during_backoff_does_not_restart_child(fake_runner, fake_clock):
    spec = make_spec("backoff_service", probe=ProbeSpec(probe_type="noop", initial_delay_seconds=0.0))
    sup = None

    def sleep_and_stop(_seconds):
        fake_clock.advance(_seconds)
        sup.request_stop()

    sup = Supervisor(
        specs=(spec,),
        runner=fake_runner,
        clock=fake_clock.time,
        sleep_fn=sleep_and_stop,
    )
    sup.start_all()
    fake_runner.active_processes["backoff_service"][-1].exit_with(1)

    assert sup.step() == 0
    assert len(fake_runner.started) == 1


def test_run_returns_zero_after_stop_requested_by_interrupt_path(fake_runner, fake_clock):
    sup = None

    def on_event(event):
        if event.event_type == "started":
            sup.request_stop()

    sup = Supervisor(
        specs=(make_spec("interruptible_service"),),
        runner=fake_runner,
        clock=fake_clock.time,
        sleep_fn=fake_clock.sleep,
        on_event=on_event,
    )

    assert sup.run() == 0
    assert not fake_runner.active_processes["interruptible_service"][-1].is_alive()


def test_shutdown_reaps_after_forced_kill(fake_runner, fake_clock):
    spec = make_spec("stubborn_service")
    fake_runner.stubborn_names.add(spec.name)
    sup = Supervisor(
        specs=(spec,),
        runner=fake_runner,
        clock=fake_clock.time,
        sleep_fn=fake_clock.sleep,
    )
    sup.start_all()
    child = fake_runner.active_processes[spec.name][-1]

    sup.stop_all()

    assert child._killed is True
    assert len(child.wait_calls) >= 2
    assert not child.is_alive()


def test_unexpected_child_exit_triggers_bounded_exponential_backoff(fake_runner, fake_clock):
    specs = (make_spec("gw", required=True, max_attempts=5, base_backoff=1.5, max_backoff=10.0),)
    events: list[SupervisorEvent] = []

    sup = Supervisor(
        specs=specs,
        runner=fake_runner,
        clock=fake_clock.time,
        sleep_fn=fake_clock.sleep,
        on_event=events.append,
    )
    sup.start_all()

    # Exit 1 -> attempt 1 backoff = 1.5 * 2^0 = 1.5
    fake_runner.active_processes["gw"][-1].exit_with(1)
    sup.step()
    # Exit 2 -> attempt 2 backoff = 1.5 * 2^1 = 3.0
    fake_runner.active_processes["gw"][-1].exit_with(1)
    sup.step()
    # Exit 3 -> attempt 3 backoff = 1.5 * 2^2 = 6.0
    fake_runner.active_processes["gw"][-1].exit_with(1)
    sup.step()

    restart_events = [e for e in events if e.event_type == "restarting"]
    assert len(restart_events) == 3
    assert restart_events[0].details["backoff_seconds"] == 1.5
    assert restart_events[1].details["backoff_seconds"] == 3.0
    assert restart_events[2].details["backoff_seconds"] == 6.0


def test_restart_attempt_window_reset(fake_runner, fake_clock):
    # max_attempts=2 within 60s window
    specs = (make_spec("gw", required=True, max_attempts=2, window=60.0),)
    events: list[SupervisorEvent] = []

    sup = Supervisor(
        specs=specs,
        runner=fake_runner,
        clock=fake_clock.time,
        sleep_fn=fake_clock.sleep,
        on_event=events.append,
    )
    sup.start_all()

    # Failure 1 at t=1000
    fake_runner.active_processes["gw"][-1].exit_with(1)
    sup.step()
    assert len([e for e in events if e.event_type == "restarting"]) == 1

    # Clock advances by 70s to t=1070 (past 60s window)
    fake_clock.advance(70.0)

    # Failure 2 at t=1070 (previous attempt at t=1000 expired -> window reset to 1 attempt)
    fake_runner.active_processes["gw"][-1].exit_with(1)
    exit_code = sup.step()

    # Must NOT be exhausted; supervisor restarts smoothly
    assert exit_code == 0
    assert not any(e.event_type == "exhausted" for e in events)
    assert len([e for e in events if e.event_type == "restarting"]) == 2


def test_required_child_exhaustion_causes_nonzero_exit(fake_runner, fake_clock):
    specs = (make_spec("gw", required=True, max_attempts=2, window=60.0),)
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


def test_forced_kill_after_shutdown_timeout(fake_runner, fake_clock):
    specs = (make_spec("stubborn_svc"), make_spec("normal_svc"))
    # Make stubborn_svc ignore terminate()
    fake_runner.stubborn_names.add("stubborn_svc")

    events: list[SupervisorEvent] = []
    sup = Supervisor(
        specs=specs,
        runner=fake_runner,
        clock=fake_clock.time,
        sleep_fn=fake_clock.sleep,
        on_event=events.append,
    )
    sup.start_all()

    sup.stop_all()

    # Event log must show forced kill for stubborn service
    killing_events = [e for e in events if e.event_type == "killing"]
    assert len(killing_events) == 1
    assert killing_events[0].process_name == "stubborn_svc"

    # All processes (including stubborn) must be dead with no orphans
    for spec in specs:
        for child in fake_runner.active_processes[spec.name]:
            assert not child.is_alive()
            assert child.poll() is not None


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
