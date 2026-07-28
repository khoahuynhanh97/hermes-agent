from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from hermes.maintenance import MaintenanceResult, RuntimeState


class _PowerShellResult:
    def __init__(self, payload: dict[str, object], returncode: int = 0):
        self.returncode = returncode
        self.stdout = json.dumps(payload)
        self.stderr = ""


class WindowsRuntimeProcessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name).resolve()
        self.python = self.root / ".venv" / "Scripts" / "python.exe"
        self.bot = self.root / "telegram_bot.py"
        self.worker = self.root / "scripts" / "run_job_worker.py"
        self.python.parent.mkdir(parents=True)
        self.worker.parent.mkdir(parents=True)
        for path in (self.python, self.bot, self.worker):
            path.touch()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _process(
        self,
        pid: int,
        script: Path,
        *,
        executable: Path | None = None,
    ) -> dict[str, object]:
        executable = executable or self.python
        return {
            "ProcessId": pid,
            "ExecutablePath": str(executable),
            "CommandLine": f'"{executable}" "{script}"',
        }

    def _controller(self, responses: list[dict[str, object]]):
        from hermes.adapters.local.windows_runtime_processes import (
            WindowsHermesProcessController,
        )

        runner = Mock(
            side_effect=[_PowerShellResult(payload) for payload in responses]
        )
        controller = WindowsHermesProcessController(
            repo_root=self.root,
            powershell_runner=runner,
            sleep=lambda _seconds: None,
        )
        return controller, runner

    def test_discover_requires_exact_python_and_entrypoint_paths(self):
        relative_bot = Path("telegram_bot.py")
        relative_worker = Path("scripts") / "run_job_worker.py"
        controller, runner = self._controller(
            [
                {
                    "ok": True,
                    "processes": [
                        self._process(101, relative_bot),
                        self._process(102, relative_worker),
                    ],
                }
            ]
        )

        state = controller.discover()

        self.assertEqual(
            state,
            RuntimeState(bot_count=1, worker_count=1, unambiguous=True),
        )
        command = runner.call_args.args[0]
        self.assertIn("Get-CimInstance Win32_Process", command)
        self.assertIn("ConvertTo-Json", command)

    def test_discover_rejects_zero_duplicate_and_unexpected_matches(self):
        wrong_python = self.root / "python.exe"
        wrong_python.touch()
        cases = (
            [],
            [
                self._process(1, self.bot),
                self._process(2, self.bot),
                self._process(3, self.worker),
            ],
            [
                self._process(1, self.bot),
                self._process(2, self.worker),
                self._process(3, self.bot, executable=wrong_python),
            ],
        )
        for processes in cases:
            with self.subTest(processes=processes):
                controller, _runner = self._controller(
                    [{"ok": True, "processes": processes}]
                )
                self.assertFalse(controller.discover().unambiguous)

    def test_stop_rechecks_pid_identity_before_stop_process(self):
        controller, runner = self._controller(
            [
                {
                    "ok": True,
                    "processes": [
                        self._process(101, self.bot),
                        self._process(102, self.worker),
                    ],
                },
                {
                    "ok": True,
                    "processes": [
                        self._process(
                            101,
                            self.root / "scripts" / "other.py",
                        ),
                        self._process(102, self.worker),
                    ],
                },
            ]
        )
        state = controller.discover()

        with self.assertRaisesRegex(RuntimeError, "identity"):
            controller.stop(state, timeout_seconds=2)

        self.assertEqual(runner.call_count, 2)
        self.assertNotIn("Stop-Process", runner.call_args.args[0])

    def test_stop_uses_bounded_normal_then_force_and_verifies_stopped(self):
        running = [
            self._process(101, self.bot),
            self._process(102, self.worker),
        ]
        controller, runner = self._controller(
            [
                {"ok": True, "processes": running},
                {"ok": True, "processes": running},
                {"ok": True},
                {"ok": True, "processes": running},
                {"ok": True, "processes": running},
                {"ok": True},
                {"ok": True, "processes": []},
            ]
        )

        controller.stop(controller.discover(), timeout_seconds=2)

        stop_command = runner.call_args_list[5].args[0]
        self.assertIn("Stop-Process", stop_command)
        self.assertIn("-Force", stop_command)
        self.assertLessEqual(runner.call_args_list[2].kwargs["timeout"], 2)
        self.assertEqual(controller._target_processes, {})

    def test_offline_lease_validates_stopped_state_and_blocks_start(self):
        controller, _runner = self._controller(
            [
                {"ok": True, "processes": []},
                {"ok": True, "processes": []},
                {
                    "ok": True,
                    "processes": [self._process(301, self.bot)],
                },
            ]
        )
        expected = RuntimeState(1, 1, True)

        lease = controller.acquire_offline_lease(expected)

        self.assertTrue(lease.validate())
        with self.assertRaisesRegex(RuntimeError, "offline lease"):
            controller.start(expected)
        self.assertFalse(lease.validate())
        controller.release_offline_lease(lease)

    def test_offline_lease_blocks_a_second_controller_until_release(self):
        from hermes.adapters.local.windows_runtime_processes import (
            WindowsHermesProcessController,
        )

        owner, _owner_runner = self._controller(
            [{"ok": True, "processes": []}]
        )
        other_runner = Mock()
        other = WindowsHermesProcessController(
            repo_root=self.root,
            powershell_runner=other_runner,
            sleep=lambda _seconds: None,
        )
        expected = RuntimeState(1, 1, True)
        lease = owner.acquire_offline_lease(expected)

        with self.assertRaisesRegex(RuntimeError, "another process"):
            other.start(expected)

        other_runner.assert_not_called()
        owner.release_offline_lease(lease)

    def test_restart_uses_fixed_hidden_venv_processes_and_runtime_logs(self):
        controller, runner = self._controller(
            [
                {"ok": True, "processes": []},
                {"ok": True, "pids": [201, 202]},
                {
                    "ok": True,
                    "processes": [
                        self._process(201, self.bot),
                        self._process(202, self.worker),
                    ],
                },
            ]
        )

        state = controller.start(RuntimeState(1, 1, True))

        self.assertTrue(state.unambiguous)
        call = runner.call_args_list[1]
        self.assertIn("Start-Process", call.args[0])
        self.assertIn("-WindowStyle Hidden", call.args[0])
        child_env = call.kwargs["env"]
        self.assertEqual(child_env["HERMES_RUNTIME_PYTHON"], str(self.python))
        self.assertEqual(child_env["HERMES_RUNTIME_BOT"], str(self.bot))
        self.assertEqual(child_env["HERMES_RUNTIME_WORKER"], str(self.worker))
        self.assertEqual(
            child_env["HERMES_RUNTIME_BOT_STDOUT"],
            str(self.root / "runtime_logs" / "telegram_bot.stdout.log"),
        )
        self.assertEqual(
            child_env["HERMES_RUNTIME_WORKER_STDERR"],
            str(self.root / "runtime_logs" / "worker.stderr.log"),
        )


class MaintenanceCliTests(unittest.TestCase):
    def _load_cli(self):
        import scripts.hermes_maintenance as cli

        return cli

    def test_run_refuses_without_confirmation_before_building_runtime(self):
        cli = self._load_cli()
        output = io.StringIO()
        with patch.object(cli, "_build_runner") as build_runner:
            exit_code = cli.main(
                ["run"],
                environ={"HERMES_STORAGE_BACKEND": "sqlite"},
                stdout=output,
            )

        self.assertEqual(exit_code, cli.EXIT_CONFIRMATION_REQUIRED)
        build_runner.assert_not_called()
        self.assertEqual(json.loads(output.getvalue()), {"status": "refused"})

    def test_run_refuses_non_sqlite_backend_before_building_runtime(self):
        cli = self._load_cli()
        output = io.StringIO()
        with patch.object(cli, "_build_runner") as build_runner:
            exit_code = cli.main(
                ["run", "--confirm-live"],
                environ={"HERMES_STORAGE_BACKEND": "json"},
                stdout=output,
            )

        self.assertEqual(exit_code, cli.EXIT_SQLITE_REQUIRED)
        build_runner.assert_not_called()
        self.assertEqual(json.loads(output.getvalue()), {"status": "refused"})

    def test_audit_is_read_only_and_never_builds_process_controller(self):
        cli = self._load_cli()
        output = io.StringIO()
        audit_result = cli.CommandResult(
            status="audit_completed",
            report_json="audit.json",
            report_markdown="audit.md",
        )
        with patch.object(cli, "_run_audit", return_value=audit_result) as audit:
            with patch.object(cli, "_build_runner") as build_runner:
                exit_code = cli.main(
                    ["audit"],
                    environ={"HERMES_STORAGE_BACKEND": "json"},
                    stdout=output,
                )

        self.assertEqual(exit_code, 0)
        audit.assert_called_once()
        build_runner.assert_not_called()
        self.assertEqual(
            json.loads(output.getvalue()),
            {
                "report_json": "audit.json",
                "report_markdown": "audit.md",
                "status": "audit_completed",
            },
        )

    def test_run_prints_only_status_and_report_paths_with_stable_exit(self):
        cli = self._load_cli()
        statuses = (
            ("completed", 0),
            ("failed", cli.EXIT_RUN_FAILED),
            (
                "manual_intervention_required",
                cli.EXIT_MANUAL_INTERVENTION,
            ),
        )
        for status, expected_exit in statuses:
            with self.subTest(status=status):
                output = io.StringIO()
                runner = Mock()
                runner.run.return_value = MaintenanceResult(
                    run_id="run-" + "1" * 32,
                    status=status,
                    backup_path=r"D:\sensitive\backup.db",
                    report_json="result.json",
                    report_markdown="result.md",
                )
                with patch.object(cli, "_build_runner", return_value=runner):
                    exit_code = cli.main(
                        ["run", "--confirm-live"],
                        environ={"HERMES_STORAGE_BACKEND": "sqlite"},
                        stdout=output,
                    )

                self.assertEqual(exit_code, expected_exit)
                self.assertEqual(
                    json.loads(output.getvalue()),
                    {
                        "report_json": "result.json",
                        "report_markdown": "result.md",
                        "status": status,
                    },
                )
                self.assertNotIn("backup", output.getvalue().lower())

    def test_cli_source_has_no_restore_path(self):
        cli = self._load_cli()
        source = Path(cli.__file__).read_text(encoding="utf-8").casefold()
        self.assertNotIn(".restore(", source)
        self.assertNotIn('"restore"', source)


if __name__ == "__main__":
    unittest.main()
