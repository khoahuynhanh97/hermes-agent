"""Tests for compliance gateway: brand safety, asset rights, AIGC watermark."""
from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from hermes.video.compliance import ComplianceGateway


@pytest.fixture(autouse=True)
def _fake_providers(monkeypatch):
    monkeypatch.setenv("HERMES_ALLOW_FAKE_PROVIDERS", "1")


@pytest.fixture
def gateway():
    """Create a ComplianceGateway instance."""
    return ComplianceGateway()


class TestBrandSafetyFilter:
    """Test brand safety filter catches blocked patterns and passes clean text."""

    def test_clean_text_passes(self, gateway):
        """Clean product review text should pass brand safety."""
        result = gateway.check_brand_safety("Amazing product review with great features")
        assert result["passed"], f"Clean text failed: {result}"

    def test_hate_speech_blocked(self, gateway):
        """Text with hate speech keywords should be blocked."""
        result = gateway.check_brand_safety("I hate all people and wish violence on everyone")
        assert not result["passed"], "Should block hate speech"
        assert len(result["issues"]) > 0

    def test_violence_blocked(self, gateway):
        """Text with violence keywords should be blocked."""
        result = gateway.check_brand_safety("Kill this product with extreme violence and blood")
        assert not result["passed"], "Should block violent content"

    def test_spam_blocked(self, gateway):
        """Text with spam patterns should be blocked."""
        result = gateway.check_brand_safety("BUY NOW!!! FREE MONEY!!! CLICK HERE NOW!!!")
        assert not result["passed"], "Should block spam patterns"

    def test_empty_text_passes(self, gateway):
        """Empty text should pass (no violations to detect)."""
        result = gateway.check_brand_safety("")
        assert result["passed"], "Empty text should pass"

    def test_result_structure(self, gateway):
        """Brand safety result should have correct structure."""
        result = gateway.check_brand_safety("Test text")
        assert "passed" in result
        assert "issues" in result
        assert isinstance(result["issues"], list)


class TestAssetRightsChecker:
    """Test asset rights checker validates real files and catches missing files."""

    def test_existing_file_passes(self, gateway, tmp_path):
        """Existing file with valid extension should pass."""
        asset_path = tmp_path / "product_image.jpg"
        Image.new("RGB", (32, 32), "white").save(asset_path)
        result = gateway.check_asset_rights(str(asset_path))
        assert result["passed"], f"Existing file failed: {result}"

    def test_missing_file_fails(self, gateway, tmp_path):
        """Non-existent file should fail."""
        asset_path = tmp_path / "nonexistent.png"
        result = gateway.check_asset_rights(str(asset_path))
        assert not result["passed"], "Missing file should fail"
        assert any("not found" in issue.lower() or "missing" in issue.lower() for issue in result["issues"])

    def test_unsupported_extension_fails(self, gateway, tmp_path):
        """Unsupported file extension should fail."""
        asset_path = tmp_path / "malware.exe"
        asset_path.write_text("not a real image")
        result = gateway.check_asset_rights(str(asset_path))
        assert not result["passed"], "Unsupported extension should fail"

    def test_result_structure(self, gateway, tmp_path):
        """Asset rights result should have correct structure."""
        asset_path = tmp_path / "test.jpg"
        Image.new("RGB", (32, 32), "white").save(asset_path)
        result = gateway.check_asset_rights(str(asset_path))
        assert "passed" in result
        assert "issues" in result


class TestAIGCWatermark:
    """Test AIGC watermark embedder adds metadata to video."""

    def test_watermark_metadata_added(self, gateway, tmp_path):
        """Watermark should add AIGC metadata to video file."""
        # Create a minimal MP4 file for testing
        fake_video = tmp_path / "test_video.mp4"
        fake_video.write_bytes(b"\x00" * 1024)

        result = gateway.embed_aigc_watermark(str(fake_video))
        assert result["passed"], f"Watermark embedding failed: {result}"
        assert "metadata" in result

    def test_watermark_result_structure(self, gateway, tmp_path):
        """Watermark result should have correct structure."""
        fake_video = tmp_path / "test_video.mp4"
        fake_video.write_bytes(b"\x00" * 1024)

        result = gateway.embed_aigc_watermark(str(fake_video))
        assert "passed" in result
        assert "metadata" in result or "issues" in result

    def test_watermark_nonexistent_file_fails(self, gateway, tmp_path):
        """Watermark on non-existent file should fail gracefully."""
        result = gateway.embed_aigc_watermark(str(tmp_path / "nonexistent.mp4"))
        assert not result["passed"], "Should fail on non-existent file"


class TestComplianceGatewayOrchestrator:
    """Test the full compliance check orchestrator."""

    def test_full_compliance_check_passes(self, gateway, tmp_path):
        """Full compliance check on clean assets should pass."""
        # Create test assets
        image_path = tmp_path / "product.jpg"
        Image.new("RGB", (32, 32), "white").save(image_path)
        video_path = tmp_path / "final_video.mp4"
        video_path.write_bytes(b"\x00" * 1024)

        result = gateway.run_full_compliance(
            text_content="Amazing product review with great features",
            asset_paths=[str(image_path)],
            video_path=str(video_path),
        )
        assert result["passed"], f"Full compliance failed: {result}"
        assert "checks" in result
        assert len(result["checks"]) >= 3  # brand_safety, asset_rights, aigc_watermark

    def test_full_compliance_fails_on_bad_text(self, gateway, tmp_path):
        """Full compliance should fail if text content violates brand safety."""
        image_path = tmp_path / "product.jpg"
        Image.new("RGB", (32, 32), "white").save(image_path)
        video_path = tmp_path / "final_video.mp4"
        video_path.write_bytes(b"\x00" * 1024)

        result = gateway.run_full_compliance(
            text_content="HATE SPEECH VIOLENCE KILL EVERYONE",
            asset_paths=[str(image_path)],
            video_path=str(video_path),
        )
        assert not result["passed"], "Should fail on bad text"

    def test_full_compliance_fails_on_missing_asset(self, gateway, tmp_path):
        """Full compliance should fail if an asset is missing."""
        video_path = tmp_path / "final_video.mp4"
        video_path.write_bytes(b"\x00" * 1024)

        result = gateway.run_full_compliance(
            text_content="Clean text",
            asset_paths=[str(tmp_path / "nonexistent.jpg")],
            video_path=str(video_path),
        )
        assert not result["passed"], "Should fail on missing asset"

    def test_compliance_report_structure(self, gateway, tmp_path):
        """Full compliance report should have detailed structure."""
        image_path = tmp_path / "product.jpg"
        Image.new("RGB", (32, 32), "white").save(image_path)
        video_path = tmp_path / "final_video.mp4"
        video_path.write_bytes(b"\x00" * 1024)

        result = gateway.run_full_compliance(
            text_content="Clean product review",
            asset_paths=[str(image_path)],
            video_path=str(video_path),
        )
        assert "passed" in result
        assert "checks" in result
        assert "timestamp" in result
        for check in result["checks"]:
            assert "name" in check
            assert "passed" in check
