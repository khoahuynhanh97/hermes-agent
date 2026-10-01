from __future__ import annotations

from pathlib import Path
import pytest


@pytest.fixture(autouse=True)
def _isolate_video_ai_hub(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure all tests in hermes_personal run against an isolated VideoAI hub."""
    hub_dir = tmp_path / "VideoAI"
    monkeypatch.setenv("HERMES_VIDEO_AI_HUB", str(hub_dir))
