"""Provider selection for image generation.

Config-based only:
- IMAGE_PROVIDER=fake (default, tests) | gemini
- IMAGE_MODEL=<specialized image model>
- GEMINI_API_KEY=<key>

Never routes through reason_combo. Defaults to fake to avoid accidental
paid generation.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hermes.ports.image_generation import ImageGenerationPort


def get_image_provider(output_dir: str | None = None) -> "ImageGenerationPort":
    provider = os.environ.get("IMAGE_PROVIDER", "").strip().lower() or "fake"
    if provider == "fake":
        _require_fake_allowed()
        from hermes.integrations.providers.fake_image_provider import FakeImageGenerationProvider

        return FakeImageGenerationProvider(output_dir)
    if provider == "google_vertex":
        from hermes.integrations.providers.vertex_image_provider import GoogleVertexImageProvider

        return GoogleVertexImageProvider(output_dir=output_dir)
    if provider == "gemini":
        from hermes.integrations.providers.gemini_image_provider import GeminiImageProvider

        return GeminiImageProvider(output_dir=output_dir)
    raise ValueError(f"unsupported IMAGE_PROVIDER: {provider}")


def _require_fake_allowed() -> None:
    """Fake providers are for tests/hermetic acceptance only.

    A real runtime run must never silently fall back to fake. Explicit flag
    required: HERMES_ALLOW_FAKE_PROVIDERS=1.
    """
    if os.environ.get("HERMES_ALLOW_FAKE_PROVIDERS", "").strip() != "1":
        raise ValueError(
            "IMAGE_PROVIDER=fake selected but HERMES_ALLOW_FAKE_PROVIDERS is not set. "
            "Real runs must use a real provider (google_vertex)."
        )