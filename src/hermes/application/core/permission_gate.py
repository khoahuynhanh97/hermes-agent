"""
Permission gate for Hermes code-writing workflows.

The gate is conservative by default. It protects secrets, runtime artifacts,
approved knowledge, generated media, and paths outside the repository.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import fnmatch


BLOCKED_PATTERNS = [
    ".env",
    ".env.*",
    "userbot.session",
    ".git/**",
    ".agents/**",
    ".codex/**",
    "__pycache__/**",
    "downloads/**",
    "scratch/**",
    "scratch_test_downloads/**",
    "projects/**",
    "knowledge_base/approved_lessons/**",
    "knowledge_base/entries/**",
    "*.pyc",
    "*.pyo",
    "*.log",
    "*.mp4",
    "*.mp3",
    "*.wav",
    "*.jpg",
    "*.jpeg",
    "*.png",
    "*.gif",
    "*.session",
    "*.bin",
]


@dataclass
class PermissionDecision:
    allowed: bool
    path: str
    reason: str


class PermissionGate:
    """Validate whether a path can be modified by Hermes."""

    def __init__(self, repo_root: str | Path):
        self.repo_root = Path(repo_root).resolve()

    def check_write_path(self, path: str | Path) -> PermissionDecision:
        raw = str(path).replace("\\", "/")
        if raw in {"", "/dev/null"}:
            return PermissionDecision(True, raw, "special diff path")

        candidate = Path(raw)
        if candidate.is_absolute():
            abs_path = candidate.resolve()
        else:
            abs_path = (self.repo_root / candidate).resolve()

        try:
            relative = abs_path.relative_to(self.repo_root)
        except ValueError:
            return PermissionDecision(False, raw, "path is outside repository")

        relative_text = str(relative).replace("\\", "/")
        for pattern in BLOCKED_PATTERNS:
            if fnmatch.fnmatch(relative_text, pattern):
                return PermissionDecision(False, relative_text, f"blocked by pattern {pattern}")

        return PermissionDecision(True, relative_text, "allowed")

    def check_many(self, paths: list[str]) -> list[PermissionDecision]:
        return [self.check_write_path(path) for path in paths]

    def assert_allowed(self, paths: list[str]) -> None:
        denied = [item for item in self.check_many(paths) if not item.allowed]
        if denied:
            detail = "; ".join(f"{item.path}: {item.reason}" for item in denied)
            raise PermissionError(detail)
