"""Asset rights verification — checks that all assets have valid usage rights."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any


_PLACEHOLDER_PREFIXES = ("tmp_", "placeholder_", "stub_", "draft_")


class AssetRightsChecker:
    """Verifies that all assets in a project have proper usage rights."""

    def check_resource_pack(self, resource_pack: dict[str, Any]) -> dict[str, Any]:
        """Check all assets in a resource pack for rights compliance.

        Returns:
            {"passed": bool, "issues": list[str], "asset_status": dict}
        """
        issues: list[str] = []
        asset_status: dict[str, dict[str, Any]] = {}

        lock_id = resource_pack.get("lock_id") or resource_pack.get("id")
        if not lock_id:
            issues.append("Resource pack missing lock_id / id")
            return {"passed": False, "issues": issues, "asset_status": asset_status}

        for asset in resource_pack.get("assets", []):
            asset_id = asset.get("asset_id", "")
            local_path = asset.get("local_path") or asset.get("uri", "")
            status: dict[str, Any] = {"asset_id": asset_id, "valid": True, "issues": []}

            if not asset_id:
                issues.append(f"Asset missing asset_id (path={local_path})")
                status["valid"] = False
                status["issues"].append("missing asset_id")

            p = Path(local_path) if local_path else None
            if p is None or not local_path.strip():
                issues.append(f"Asset {asset_id} has no path")
                status["valid"] = False
                status["issues"].append("no path")
            elif not p.is_file():
                issues.append(f"Asset {asset_id} path does not exist: {local_path}")
                status["valid"] = False
                status["issues"].append("file not found")
            elif p.stat().st_size < 100:
                issues.append(f"Asset {asset_id} is suspiciously small ({p.stat().st_size} bytes)")
                status["valid"] = False
                status["issues"].append("file too small")

            stem = Path(local_path).stem.lower() if local_path else ""
            if any(stem.startswith(prefix) for prefix in _PLACEHOLDER_PREFIXES):
                issues.append(f"Asset {asset_id} appears to be a placeholder/temp file: {local_path}")
                status["valid"] = False
                status["issues"].append("placeholder path detected")

            asset_status[asset_id] = status

        return {"passed": len(issues) == 0, "issues": issues, "asset_status": asset_status}

    def check_scene_assets(
        self, scene_videos: list[str], keyframes: list[str]
    ) -> dict[str, Any]:
        """Verify scene assets are real files, not stubs."""
        issues: list[str] = []
        details: dict[str, Any] = {}

        for path_str in scene_videos + keyframes:
            p = Path(path_str)
            entry = {"path": path_str, "valid": True}
            if not p.is_file():
                issues.append(f"Missing file: {path_str}")
                entry["valid"] = False
            elif p.stat().st_size < 1000:
                issues.append(f"File too small ({p.stat().st_size} bytes): {path_str}")
                entry["valid"] = False
            details[str(p.name)] = entry

        return {"passed": len(issues) == 0, "issues": issues, "details": details}
