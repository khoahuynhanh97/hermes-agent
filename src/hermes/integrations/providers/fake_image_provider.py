"""Fake image generation provider for testing."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from uuid import uuid4

from hermes.ports.image_generation import (
    ImageGenerationPort,
    ImageGenerationRequest,
    ImageGenerationResult,
)


class FakeImageGenerationProvider(ImageGenerationPort):
    """Deterministic fake image provider for tests and architecture acceptance."""

    def __init__(self, output_dir: str | None = None):
        self.output_dir = Path(output_dir) if output_dir else Path(tempfile.gettempdir()) / "hermes-fake-images"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate(self, request: ImageGenerationRequest) -> ImageGenerationResult:
        """Generate a fake 1x1 PNG placeholder."""
        try:
            # Create minimal valid 1x1 PNG
            png_data = (
                b'\x89PNG\r\n\x1a\n'
                b'\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
                b'\x08\x02\x00\x00\x00\x90wS\xde'
                b'\x00\x00\x00\x0cIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01'
                b'\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82'
            )
            
            output_paths = []
            for i in range(request.num_images):
                filename = f"{request.request_id}_{i}.png"
                output_path = self.output_dir / filename
                output_path.write_bytes(png_data)
                output_paths.append(str(output_path))
            
            return ImageGenerationResult(
                request_id=request.request_id,
                success=True,
                image_paths=tuple(output_paths),
                provider_operation_id=f"fake_op_{uuid4().hex[:8]}",
                metadata={"provider": "fake", "mode": "test"},
            )
        except Exception as e:
            return ImageGenerationResult(
                request_id=request.request_id,
                success=False,
                error_message=str(e),
            )

    def check_status(self, operation_id: str) -> ImageGenerationResult:
        """Fake operations complete immediately."""
        return ImageGenerationResult(
            request_id=operation_id,
            success=True,
            metadata={"provider": "fake", "status": "completed"},
        )
