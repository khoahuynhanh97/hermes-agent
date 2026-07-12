"""
Safe unified-diff patch executor for Hermes.

Default usage should be check-only. Applying a patch requires an explicit
caller action, because this module writes source files through `git apply`.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import re
import subprocess
import tempfile

from core.permission_gate import PermissionDecision, PermissionGate


DIFF_PATH_RE = re.compile(r"^(?:---|\+\+\+)\s+(?P<path>\S+)")


@dataclass
class PatchExecutionResult:
    ok: bool
    applied: bool
    checked_paths: list[str]
    decisions: list[PermissionDecision]
    stdout: str
    stderr: str
    report_path: str


class PatchExecutor:
    """Validate and optionally apply unified diffs inside a repo."""

    def __init__(self, repo_root: str | Path):
        self.repo_root = Path(repo_root).resolve()
        self.gate = PermissionGate(self.repo_root)

    def check(self, patch_text: str, report_path: str | Path | None = None) -> PatchExecutionResult:
        return self.execute(patch_text, apply=False, report_path=report_path)

    def execute(
        self,
        patch_text: str,
        apply: bool = False,
        report_path: str | Path | None = None,
    ) -> PatchExecutionResult:
        paths = extract_patch_paths(patch_text)
        decisions = self.gate.check_many(paths)
        denied = [item for item in decisions if not item.allowed]
        if denied:
            result = PatchExecutionResult(
                ok=False,
                applied=False,
                checked_paths=paths,
                decisions=decisions,
                stdout="",
                stderr="Permission denied for one or more patch paths.",
                report_path="",
            )
            result.report_path = str(self.write_report(result, report_path))
            return result

        command = ["git", "apply", "--check"]
        check_run = self._run_git_apply(command, patch_text)
        if check_run.returncode != 0 or not apply:
            result = PatchExecutionResult(
                ok=check_run.returncode == 0,
                applied=False,
                checked_paths=paths,
                decisions=decisions,
                stdout=check_run.stdout,
                stderr=check_run.stderr,
                report_path="",
            )
            result.report_path = str(self.write_report(result, report_path))
            return result

        apply_run = self._run_git_apply(["git", "apply"], patch_text)
        result = PatchExecutionResult(
            ok=apply_run.returncode == 0,
            applied=apply_run.returncode == 0,
            checked_paths=paths,
            decisions=decisions,
            stdout=apply_run.stdout,
            stderr=apply_run.stderr,
            report_path="",
        )
        result.report_path = str(self.write_report(result, report_path))
        return result

    def write_report(self, result: PatchExecutionResult, report_path: str | Path | None = None) -> Path:
        output = Path(report_path) if report_path else self._default_report_path()
        output.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            "# Hermes Patch Executor Report",
            "",
            f"Created at: {datetime.now().isoformat(timespec='seconds')}",
            f"OK: {result.ok}",
            f"Applied: {result.applied}",
            "",
            "## Checked paths",
        ]
        for decision in result.decisions:
            status = "allowed" if decision.allowed else "blocked"
            lines.append(f"- `{decision.path}`: {status} ({decision.reason})")
        lines.extend(["", "## stdout", "```text", result.stdout.strip(), "```"])
        lines.extend(["", "## stderr", "```text", result.stderr.strip(), "```"])
        output.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return output

    def _run_git_apply(self, command: list[str], patch_text: str) -> subprocess.CompletedProcess:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".patch", delete=False) as handle:
            handle.write(patch_text)
            patch_path = handle.name
        try:
            return subprocess.run(
                command + [patch_path],
                cwd=str(self.repo_root),
                text=True,
                capture_output=True,
                timeout=30,
            )
        finally:
            try:
                Path(patch_path).unlink()
            except OSError:
                pass

    def _default_report_path(self) -> Path:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        return self.repo_root / "reports" / f"patch_executor_{stamp}.md"


def extract_patch_paths(patch_text: str) -> list[str]:
    paths = []
    seen = set()
    for line in (patch_text or "").splitlines():
        match = DIFF_PATH_RE.match(line.strip())
        if not match:
            continue
        path = normalize_diff_path(match.group("path"))
        if path and path not in seen:
            seen.add(path)
            paths.append(path)
    return paths


def normalize_diff_path(path: str) -> str:
    cleaned = (path or "").strip()
    if cleaned in {"/dev/null", "NUL"}:
        return "/dev/null"
    if cleaned.startswith("a/") or cleaned.startswith("b/"):
        cleaned = cleaned[2:]
    return cleaned.replace("\\", "/")
