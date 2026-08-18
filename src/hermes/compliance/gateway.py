"""Compliance Gateway — master orchestrator for all compliance checks."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from hermes.compliance.asset_rights import AssetRightsChecker
from hermes.compliance.aigc_watermark import AIGCWatermarkEmbedder
from hermes.compliance.brand_safety import BrandSafetyFilter

logger = logging.getLogger(__name__)


class ComplianceGateway:
    """Master compliance check orchestrator."""

    def __init__(self) -> None:
        self.asset_checker = AssetRightsChecker()
        self.brand_filter = BrandSafetyFilter()
        self.watermark_embedder = AIGCWatermarkEmbedder()

    def run_full_check(
        self,
        project_id: str,
        video_path: str,
        voiceover_text: str,
        caption_text: str,
        resource_pack: dict[str, Any],
    ) -> dict[str, Any]:
        """Run all compliance checks and produce a report.

        Returns:
            {
                "passed": bool,
                "asset_rights": dict,
                "brand_safety": dict,
                "aigc_watermark": dict,
                "summary": str,
                "issues": list[str],
            }
        """
        all_issues: list[str] = []

        # 1. Asset rights
        asset_result = self.asset_checker.check_resource_pack(resource_pack)
        all_issues.extend(asset_result.get("issues", []))

        # 2. Brand safety
        vo_result = self.brand_filter.scan_voiceover_script(voiceover_text)
        cap_result = self.brand_filter.scan_caption_text(
            [{"text": caption_text}]
        )
        brand_issues = (
            [v["match"] for v in vo_result.get("violations", [])]
            + [v["match"] for v in cap_result.get("violations", [])]
        )
        all_issues.extend(brand_issues)

        # 3. AIGC watermark
        wm_result: dict[str, Any] = {"success": False, "output_path": ""}
        if Path(video_path).is_file():
            wm_result = self.watermark_embedder.embed_metadata(
                video_path, project_id
            )
        else:
            all_issues.append(f"Video file not found for watermarking: {video_path}")

        passed = asset_result["passed"] and vo_result["passed"] and wm_result.get("success", False)
        summary = (
            "All compliance checks passed"
            if passed
            else f"Compliance issues found: {len(all_issues)}"
        )

        return {
            "passed": passed,
            "asset_rights": asset_result,
            "brand_safety": {
                "voiceover": vo_result,
                "captions": cap_result,
            },
            "aigc_watermark": wm_result,
            "summary": summary,
            "issues": all_issues,
        }

    def run_brand_safety_only(self, text: str) -> dict[str, Any]:
        """Quick brand safety check on text."""
        return self.brand_filter.scan_text(text)
