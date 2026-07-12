"""
Hermes tool registry.

Loads manifest-first tool definitions so Hermes can list, create, export, and
eventually run small local tools in a controlled way.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path


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


class ToolRegistry:
    """Load and validate Hermes tool manifests."""

    def __init__(self, repo_root: str | Path):
        self.repo_root = Path(repo_root).resolve()
        self.manifest_dir = self.repo_root / "tools" / "manifests"

    def list_manifests(self) -> list[ToolManifest]:
        manifests = []
        if not self.manifest_dir.exists():
            return manifests
        for path in sorted(self.manifest_dir.glob("*.json")):
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
