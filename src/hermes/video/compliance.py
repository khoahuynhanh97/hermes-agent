"""Compliance gateway: brand safety, asset rights, AIGC watermark checks."""
from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Any


# Blocked content patterns grouped by category
_BRAND_SAFETY_PATTERNS = {
    "hate_speech": [
        r"\bhate\b.*\b(people|race|religion|group)\b",
        r"\bkill\b.*\b(all|everyone|them)\b",
        r"\bviolence\b",
        r"\bblood\b",
    ],
    "spam": [
        r"BUY NOW[!!!]*",
        r"FREE MONEY[!!!]*",
        r"CLICK HERE[!!!]*",
        r"ACT NOW[!!!]*",
    ],
    "profanity": [
        r"\b(damn|hell)\b",
    ],
}

_ALLOWED_ASSET_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".mp4", ".mov", ".mp3", ".wav", ".ass"}


class ComplianceGateway:
    """Orchestrates compliance checks for video pipeline outputs."""

    def check_brand_safety(self, text: str) -> dict[str, Any]:
        """Check text content against brand safety filters.

        Returns {"passed": bool, "issues": list[str], "categories": list[str]}.
        """
        if not text or not text.strip():
            return {"passed": True, "issues": [], "categories": []}

        issues: list[str] = []
        categories: list[str] = []
        text_upper = text.upper()

        for category, patterns in _BRAND_SAFETY_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, text_upper, re.IGNORECASE):
                    msg = f"{category}: matched pattern '{pattern}'"
                    issues.append(msg)
                    if category not in categories:
                        categories.append(category)

        return {
            "passed": len(issues) == 0,
            "issues": issues,
            "categories": categories,
        }

    def check_asset_rights(self, asset_path: str) -> dict[str, Any]:
        """Validate that an asset file exists and has an allowed extension.

        Returns {"passed": bool, "issues": list[str]}.
        """
        path = Path(asset_path)
        issues: list[str] = []

        if not path.is_file():
            issues.append(f"Asset not found: {asset_path}")
            return {"passed": False, "issues": issues}

        ext = path.suffix.lower()
        if ext not in _ALLOWED_ASSET_EXTENSIONS:
            issues.append(f"Unsupported asset type: {ext}")
            return {"passed": False, "issues": issues}

        if path.stat().st_size == 0:
            issues.append(f"Asset is empty: {asset_path}")

        return {"passed": len(issues) == 0, "issues": issues}

    def embed_aigc_watermark(self, video_path: str) -> dict[str, Any]:
        """Embed AIGC (AI-Generated Content) metadata into video.

        In production this writes XMP/metadata tags. For now it records the
        watermark intent and validates the file exists.

        Returns {"passed": bool, "metadata": dict, "issues": list[str]}.
        """
        path = Path(video_path)
        if not path.is_file():
            return {
                "passed": False,
                "metadata": {},
                "issues": [f"Video file not found: {video_path}"],
            }

        metadata = {
            "aigc_generated": True,
            "aigc_tool": "hermes-agent",
            "aigc_timestamp": int(time.time()),
            "aigc_version": "1.0",
        }

        # Write metadata sidecar alongside the video
        sidecar_path = path.with_suffix(".aigc.json")
        try:
            import json
            sidecar_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        except Exception as exc:
            return {
                "passed": False,
                "metadata": metadata,
                "issues": [f"Failed to write AIGC sidecar: {exc}"],
            }

        return {"passed": True, "metadata": metadata, "issues": []}

    def run_full_compliance(
        self,
        text_content: str = "",
        asset_paths: list[str] | None = None,
        video_path: str | None = None,
    ) -> dict[str, Any]:
        """Run all compliance checks and return an aggregated report.

        Returns:
            {"passed": bool, "checks": list[dict], "timestamp": float}
        """
        checks: list[dict[str, Any]] = []

        # 1. Brand safety
        brand = self.check_brand_safety(text_content)
        checks.append({"name": "brand_safety", **brand})

        # 2. Asset rights
        all_assets_ok = True
        for asset_path in (asset_paths or []):
            rights = self.check_asset_rights(asset_path)
            checks.append({"name": f"asset_rights:{Path(asset_path).name}", **rights})
            if not rights["passed"]:
                all_assets_ok = False

        # 3. AIGC watermark
        if video_path:
            watermark = self.embed_aigc_watermark(video_path)
            checks.append({"name": "aigc_watermark", **watermark})

        overall = all(c["passed"] for c in checks)
        return {
            "passed": overall,
            "checks": checks,
            "timestamp": time.time(),
        }
