"""Gemini Developer API image provider adapter (API-key based).

Implements ImageGenerationPort against the Gemini Developer API
(generativelanguage.googleapis.com). For Google Cloud/Vertex usage, see
providers/vertex_image_provider.py.

Provider contract:
- IMAGE_PROVIDER=gemini
- IMAGE_MODEL=gemini-2.5-flash-image
- GEMINI_API_KEY=<key>  (never logged or persisted)

Idempotency: existing output file for a request_id is reused without a call.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import requests

from hermes.ports.image_generation import (
    ImageGenerationPort,
    ImageGenerationRequest,
    ImageGenerationResult,
)
from providers.gemini_common import (
    build_contents,
    extract_image,
    generation_config,
    output_path_for,
)


GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class GeminiImageProvider(ImageGenerationPort):
    """Gemini Developer API image generation adapter."""

    def __init__(self, api_key: str | None = None, model: str | None = None, output_dir: str | None = None, timeout: int = 120):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY", "").strip()
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY is required for GeminiImageProvider")
        self.model = model or os.environ.get("IMAGE_MODEL", "").strip() or "gemini-2.5-flash-image"
        configured_dir = output_dir or os.environ.get("HERMES_VIDEO_FACTORY_WORKSPACE", "")
        self.output_dir = Path(configured_dir).expanduser().resolve() if configured_dir else (Path.cwd() / "workspace")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.timeout = int(timeout)

    def generate(self, request: ImageGenerationRequest) -> ImageGenerationResult:
        output_file = output_path_for(self.output_dir, request.request_id)
        if output_file.exists() and output_file.stat().st_size > 0:
            return ImageGenerationResult(
                request_id=request.request_id,
                success=True,
                image_paths=(str(output_file),),
                provider_operation_id=f"cached:{request.request_id}",
                metadata={"provider": "gemini", "idempotent": True},
            )

        try:
            payload = {
                "contents": build_contents(request),
                "generationConfig": generation_config(request),
            }
            response = requests.post(
                GEMINI_ENDPOINT.format(model=self.model),
                params={"key": self.api_key},
                json=payload,
                timeout=self.timeout,
            )
            if response.status_code != 200:
                return ImageGenerationResult(
                    request_id=request.request_id,
                    success=False,
                    error_message=self._normalize_error(response),
                    metadata={"provider": "gemini", "http_status": response.status_code},
                )

            image_bytes = extract_image(response.json())
            if not image_bytes:
                return ImageGenerationResult(
                    request_id=request.request_id,
                    success=False,
                    error_message="gemini response contained no inline image data",
                    metadata={"provider": "gemini"},
                )

            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_bytes(image_bytes)

            return ImageGenerationResult(
                request_id=request.request_id,
                success=True,
                image_paths=(str(output_file),),
                provider_operation_id=f"gemini:{time.strftime('%Y%m%d%H%M%S')}",
                metadata={"provider": "gemini", "model": self.model, "idempotent": False},
            )
        except Exception as error:  # noqa: BLE001 - normalize any adapter error
            return ImageGenerationResult(
                request_id=request.request_id,
                success=False,
                error_message=str(error),
                metadata={"provider": "gemini"},
            )

    def check_status(self, operation_id: str) -> ImageGenerationResult:
        # Gemini generateContent is synchronous.
        return ImageGenerationResult(
            request_id=operation_id,
            success=True,
            metadata={"provider": "gemini", "status": "completed"},
        )

    @staticmethod
    def _normalize_error(response: requests.Response) -> str:
        try:
            body = response.json()
            message = body.get("error", {}).get("message", "")
            return f"gemini http {response.status_code}: {message}" if message else f"gemini http {response.status_code}"
        except ValueError:
            return f"gemini http {response.status_code}: {response.text[:200]}"