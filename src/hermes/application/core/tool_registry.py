"""
Hermes tool registry.

Loads manifest-first tool definitions so Hermes can list, create, export, and
eventually run small local tools in a controlled way.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
import sys


REQUIRED_FIELDS = [
    "schema_version",
    "name",
    "version",
    "description",
    "type",
    "entrypoint",
    "inputs",
    "outputs",
    "permissions",
]


@dataclass
class ToolManifest:
    path: str
    data: dict
    errors: list[str]

    @property
    def valid(self) -> bool:
        return not self.errors

    @property
    def name(self) -> str:
        return str(self.data.get("name", ""))

    @property
    def root(self) -> Path:
        return Path(self.path).resolve().parent


class ToolRegistry:
    """Load and validate Hermes tool manifests."""

    def __init__(self, repo_root: str | Path):
        self.repo_root = Path(repo_root).resolve()
        self.manifest_dir = self.repo_root / "tools" / "manifests"
        self.generated_dir = self.repo_root / "tools" / "generated"

    def list_manifests(self) -> list[ToolManifest]:
        manifests = []
        paths = list(self.manifest_dir.glob("*.json")) if self.manifest_dir.exists() else []
        if self.generated_dir.exists():
            paths.extend(self.generated_dir.glob("*/manifest.json"))
        for path in sorted(paths):
            manifests.append(self.load_manifest(path))
        return manifests

    def load_manifest(self, path: str | Path) -> ToolManifest:
        manifest_path = Path(path)
        if not manifest_path.is_absolute():
            manifest_path = self.repo_root / manifest_path
        errors = []
        data = {}
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"cannot load manifest: {exc}")
            return ToolManifest(str(manifest_path), data, errors)
        errors.extend(validate_manifest(data))
        return ToolManifest(str(manifest_path), data, errors)

    def get(self, name: str) -> ToolManifest | None:
        for manifest in self.list_manifests():
            if manifest.name == name:
                return manifest
        return None

    def run(self, name: str, inputs: dict[str, str] | None = None, timeout_seconds: int = 30) -> dict:
        """Run a generated Python tool with a bounded, shell-free process."""
        manifest = self.get(name)
        if manifest is None:
            raise ValueError(f"tool not found: {name}")
        if not manifest.valid:
            raise ValueError(f"invalid tool manifest: {manifest.errors}")
        generated_root = self.generated_dir.resolve()
        tool_root = manifest.root
        if generated_root not in tool_root.parents:
            raise PermissionError("only tools under tools/generated may be executed")

        entrypoint = (tool_root / str(manifest.data.get("entrypoint", ""))).resolve()
        if tool_root not in entrypoint.parents or entrypoint.suffix.lower() != ".py":
            raise PermissionError("tool entrypoint must be a Python file inside its tool directory")
        if not entrypoint.exists():
            raise FileNotFoundError(f"tool entrypoint not found: {entrypoint}")

        provided = {str(key): str(value) for key, value in (inputs or {}).items()}
        declared = {str(item.get("name")): item for item in manifest.data.get("inputs", []) if isinstance(item, dict)}
        unknown = sorted(set(provided) - set(declared))
        if unknown:
            raise ValueError(f"unknown tool inputs: {', '.join(unknown)}")
        missing = sorted(
            name for name, spec in declared.items()
            if spec.get("required") and name not in provided
        )
        if missing:
            raise ValueError(f"missing required tool inputs: {', '.join(missing)}")

        command = [sys.executable, str(entrypoint)]
        for key, value in provided.items():
            command.extend([f"--{key.replace('_', '-')}", value])
        timeout = max(1, min(60, int(timeout_seconds)))
        completed = subprocess.run(
            command,
            cwd=str(tool_root),
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
            check=False,
        )
        result = {
            "ok": completed.returncode == 0,
            "tool": manifest.name,
            "returncode": completed.returncode,
            "stdout": completed.stdout[-12000:],
            "stderr": completed.stderr[-4000:],
        }
        if not result["ok"]:
            raise RuntimeError(f"tool exited with code {completed.returncode}: {result['stderr']}")
        return result


def validate_manifest(data: dict) -> list[str]:
    errors = []
    for field in REQUIRED_FIELDS:
        if field not in data:
            errors.append(f"missing required field: {field}")
    if not isinstance(data.get("inputs", []), list):
        errors.append("inputs must be a list")
    if not isinstance(data.get("outputs", []), list):
        errors.append("outputs must be a list")
    if not isinstance(data.get("permissions", {}), dict):
        errors.append("permissions must be an object")
    name = data.get("name", "")
    if name and not is_kebab_name(str(name)):
        errors.append("name must be lowercase kebab-case")
    return errors


def is_kebab_name(value: str) -> bool:
    if not value:
        return False
    allowed = "abcdefghijklmnopqrstuvwxyz0123456789-"
    return all(char in allowed for char in value) and "--" not in value and not value.startswith("-") and not value.endswith("-")
