"""Google Cloud (Vertex AI) Gemini image provider adapter.

Implements ImageGenerationPort against the Vertex AI generateContent REST API
using Application Default Credentials (ADC / service account / gcloud auth).
No credentials are hardcoded.

Provider contract:
- IMAGE_PROVIDER=google_vertex
- IMAGE_MODEL=gemini-3.1-flash-lite-image
- GOOGLE_CLOUD_PROJECT=<project>
- GOOGLE_CLOUD_LOCATION=global (default)

Endpoint:
    https://{location}-aiplatform.googleapis.com/v1/projects/{project}/locations/{location}/publishers/google/models/{model}:generateContent

Auth: Bearer token obtained from google.auth.default() (ADC).
Idempotency: existing output file for a request_id is reused without a call.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

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
from providers.vertex_auth import get_access_token, vertex_model_endpoint, vertex_required_project


def vertex_endpoint(project: str, location: str, model: str) -> str:
    return vertex_model_endpoint(project, location, model, "generateContent")


class GoogleVertexImageProvider(ImageGenerationPort):
    """Vertex AI Gemini image generation adapter."""

    def __init__(
        self,
        project: str | None = None,
        location: str | None = None,
        model: str | None = None,
        output_dir: str | None = None,
        timeout: int = 180,
    ):
        self.project = project or vertex_required_project()

        self.location = (location or os.environ.get("GOOGLE_CLOUD_LOCATION", "")).strip() or "us-central1"
        self.model = (model or os.environ.get("IMAGE_MODEL", "")).strip() or "gemini-2.5-flash-image"
        self.timeout = int(timeout)

        configured_dir = output_dir or os.environ.get("HERMES_VIDEO_FACTORY_WORKSPACE", "")
        self.output_dir = Path(configured_dir).expanduser().resolve() if configured_dir else (Path.cwd() / "workspace")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # ImageGenerationPort
    # ------------------------------------------------------------------

    def generate(self, request: ImageGenerationRequest) -> ImageGenerationResult:
        output_file = output_path_for(self.output_dir, request.request_id)
        if output_file.exists() and output_file.stat().st_size > 0:
            return ImageGenerationResult(
                request_id=request.request_id,
                success=True,
                image_paths=(str(output_file),),
                provider_operation_id=f"cached:{request.request_id}",
                metadata={"provider": "google_vertex", "idempotent": True},
            )

        try:
            token = get_access_token()
            payload = {
                "contents": build_contents(request),
                "generationConfig": generation_config(request),
            }
            endpoint = vertex_endpoint(self.project, self.location, self.model)
            response = requests.post(
                endpoint,
                headers={"Authorization": f"Bearer {token}"},
                json=payload,
                timeout=self.timeout,
            )
            if response.status_code != 200:
                return ImageGenerationResult(
                    request_id=request.request_id,
                    success=False,
                    error_message=self._normalize_error(response),
                    metadata={"provider": "google_vertex", "http_status": response.status_code},
                )

            image_bytes = extract_image(response.json())
            if not image_bytes:
                return ImageGenerationResult(
                    request_id=request.request_id,
                    success=False,
                    error_message="vertex response contained no inline image data",
                    metadata={"provider": "google_vertex"},
                )

            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_bytes(image_bytes)

            return ImageGenerationResult(
                request_id=request.request_id,
                success=True,
                image_paths=(str(output_file),),
                provider_operation_id=f"vertex:{time.strftime('%Y%m%d%H%M%S')}",
                metadata={"provider": "google_vertex", "model": self.model, "idempotent": False},
            )
        except Exception as error:  # noqa: BLE001 - normalize any adapter error
            return ImageGenerationResult(
                request_id=request.request_id,
                success=False,
                error_message=str(error),
                metadata={"provider": "google_vertex"},
            )

    def check_status(self, operation_id: str) -> ImageGenerationResult:
        # Vertex generateContent is synchronous.
        return ImageGenerationResult(
            request_id=operation_id,
            success=True,
            metadata={"provider": "google_vertex", "status": "completed"},
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_error(response: requests.Response) -> str:
        try:
            body = response.json()
            message = body.get("error", {}).get("message", "")
            return f"vertex http {response.status_code}: {message}" if message else f"vertex http {response.status_code}"
        except ValueError:
            return f"vertex http {response.status_code}: {response.text[:200]}"