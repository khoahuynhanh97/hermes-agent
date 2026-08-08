"""Provider selection for video generation.

Config-based only:
- VIDEO_PROVIDER=fake (default, tests) | google_vertex
- VIDEO_MODEL=<available video model>
- GOOGLE_CLOUD_PROJECT / GOOGLE_CLOUD_LOCATION (for google_vertex)

Defaults to fake to avoid accidental paid generation.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hermes.ports.video_generation import VideoGenerationPort


def get_video_provider(output_dir: str | None = None) -> "VideoGenerationPort":
    provider = os.environ.get("VIDEO_PROVIDER", "").strip().lower() or "fake"
    if provider == "fake":
        _require_fake_allowed()
        from providers.fake_video_provider import FakeVideoGenerationProvider

        return FakeVideoGenerationProvider(output_dir)
    if provider == "google_vertex":
        from providers.vertex_video_provider import GoogleVertexVideoProvider

        return GoogleVertexVideoProvider(output_dir=output_dir)
    raise ValueError(f"unsupported VIDEO_PROVIDER: {provider}")


def _require_fake_allowed() -> None:
    """Fake providers are for tests/hermetic acceptance only."""
    if os.environ.get("HERMES_ALLOW_FAKE_PROVIDERS", "").strip() != "1":
        raise ValueError(
            "VIDEO_PROVIDER=fake selected but HERMES_ALLOW_FAKE_PROVIDERS is not set. "
            "Real runs must use a real provider (google_vertex)."
        )