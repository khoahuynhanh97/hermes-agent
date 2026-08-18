"""
Verification runner for Hermes coding-agent workflows.

Runs focused, allowlisted commands and captures stdout/stderr into a report.
This is intentionally not a general shell.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
import shlex
import subprocess


ALLOWED_PREFIXES = [
    ["python", "-c"],
    ["python", "-m", "py_compile"],
    ["python", "scripts\\hermes_repo_map.py"],
    ["python", "scripts/hermes_repo_map.py"],
    ["python", "scripts\\hermes_code_agent.py"],
    ["python", "scripts/hermes_code_agent.py"],
    ["python", "scripts\\test_reliability_integration.py"],
    ["python", "scripts/test_reliability_integration.py"],
    ["python", "scripts\\test_knowledge_store_safety.py"],
    ["python", "scripts/test_knowledge_store_safety.py"],
    ["python", "scripts\\test_script_generator_knowledge_injection.py"],
    ["python", "scripts/test_script_generator_knowledge_injection.py"],
]


@dataclass
class VerificationCommandResult:
    command: str
    allowed: bool
    returncode: int | None
    stdout: str
    stderr: str
    duration_seconds: float
    reason: str


@dataclass
class VerificationRun:
    ok: bool
    created_at: str
    results: list[VerificationCommandResult]
    report_path: str


class VerificationRunner:
    """Run allowlisted verification commands and write reports."""

    def __init__(self, repo_root: str | Path, timeout_seconds: int = 60):
        self.repo_root = Path(repo_root).resolve()
        self.timeout_seconds = timeout_seconds

    def run(self, commands: list[str], report_path: str | Path | None = None) -> VerificationRun:
        results = [self._run_one(command) for command in commands]
        ok = all(item.allowed and item.returncode == 0 for item in results)
        run = VerificationRun(
            ok=ok,
            created_at=datetime.now().isoformat(timespec="seconds"),
            results=results,
            report_path="",
        )
        run.report_path = str(self.write_report(run, report_path))
        return run

    def write_report(self, run: VerificationRun, report_path: str | Path | None = None) -> Path:
        output = Path(report_path) if report_path else self._default_report_path()
        output.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            "# Hermes Verification Report",
            "",
            f"Created at: {run.created_at}",
            f"OK: {run.ok}",
            "",
            "## Commands",
        ]
        for result in run.results:
            lines.extend(
                [
                    f"### `{result.command}`",
                    "",
                    f"- Allowed: {result.allowed}",
                    f"- Return code: {result.returncode}",
                    f"- Duration seconds: {result.duration_seconds:.3f}",
                    f"- Reason: {result.reason}",
                    "",
                    "stdout:",
                    "```text",
                    result.stdout.strip(),
                    "```",
                    "",
                    "stderr:",
                    "```text",
                    result.stderr.strip(),
                    "```",
                    "",
                ]
            )
        output.write_text("\n".join(lines), encoding="utf-8")
        return output

    def to_dict(self, run: VerificationRun) -> dict:
        data = asdict(run)
        data["results"] = [asdict(item) for item in run.results]
        return data

    def _run_one(self, command: str) -> VerificationCommandResult:
        started = datetime.now()
        allowed, reason = is_allowed_command(command)
        if not allowed:
            return VerificationCommandResult(
                command=command,
                allowed=False,
                returncode=None,
                stdout="",
                stderr="",
                duration_seconds=0.0,
                reason=reason,
            )
        try:
            completed = subprocess.run(
                command,
                cwd=str(self.repo_root),
                shell=False,
                text=True,
                capture_output=True,
                timeout=self.timeout_seconds,
            )
            duration = (datetime.now() - started).total_seconds()
            return VerificationCommandResult(
                command=command,
                allowed=True,
                returncode=completed.returncode,
                stdout=completed.stdout,
                stderr=completed.stderr,
                duration_seconds=duration,
                reason="completed",
            )
        except subprocess.TimeoutExpired as exc:
            duration = (datetime.now() - started).total_seconds()
            return VerificationCommandResult(
                command=command,
                allowed=True,
                returncode=None,
                stdout=exc.stdout or "",
                stderr=exc.stderr or "timeout",
                duration_seconds=duration,
                reason=f"timeout after {self.timeout_seconds}s",
            )

    def _default_report_path(self) -> Path:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        return self.repo_root / "reports" / f"verification_{stamp}.md"


def is_allowed_command(command: str) -> tuple[bool, str]:
    try:
        parts = shlex.split(command, posix=False)
    except ValueError as exc:
        return False, f"invalid command: {exc}"
    if not parts:
        return False, "empty command"
    normalized = [part.strip('"') for part in parts]
    for prefix in ALLOWED_PREFIXES:
        if normalized[: len(prefix)] == prefix:
            return True, "allowed prefix"
    return False, "command prefix is not allowlisted"
