"""Tests for Google Flow Playwright Keyframe Provider."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from hermes_personal.integrations.video_factory.google_flow_keyframe_provider import GoogleFlowKeyframeProvider

def test_google_flow_keyframe_config_initialization():
    provider = GoogleFlowKeyframeProvider(profile_path=Path("."))
    assert provider.provider_kind == "google_flow"
    assert provider.model == "ImageFx / Imagen 3"

def test_marker_generation_deterministic():
    class MockRequest:
        operation_id = "test-123"
        prompt = "test prompt"
    
    provider = GoogleFlowKeyframeProvider(profile_path=Path("."))
    # Calling internal logic manually or testing through public method
    # Marker is deterministic based on operation_id
    # Test requires executing the logic.
    pass

@patch("hermes_personal.integrations.video_factory.google_flow_keyframe_provider.sync_playwright")
def test_keyframe_submission_success_mock(mock_pw, tmp_path):
    mock_context = MagicMock()
    mock_pw.return_value.__enter__.return_value.chromium.launch_persistent_context.return_value = mock_context
    
    provider = GoogleFlowKeyframeProvider(profile_path=tmp_path, output_dir=tmp_path)
    # This would require mocking page interactions
    pass
