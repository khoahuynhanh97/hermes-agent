"""Google Cloud Vertex Veo video generation provider adapter.

Implements VideoGenerationPort against the Vertex Veo REST API for
veo-3.1-generate-001:

- submit:  POST {model}:predictLongRunning  -> full operation name
- poll:    POST {model}:fetchPredictOperation body {"operationName": <full>}
- result:  response.videos[].bytesBase64Encoded (video/mp4) -> workspace file

Auth: shared ADC helper (providers/vertex_auth), no credentials in code.

Provider contract:
- VIDEO_PROVIDER=google_vertex
- VIDEO_MODEL=veo-3.1-generate-001
- GOOGLE_CLOUD_PROJECT=<project>
- GOOGLE_CLOUD_LOCATION=us-central1
"""

from __future__ import annotations

import base64
import os
from pathlib import Path
from typing import Any

import requests

from hermes.ports.video_generation import (
    VideoGenerationPort,
    VideoGenerationRequest,
    VideoGenerationResult,
)
from providers.gemini_common import mime_for
from providers.vertex_auth import get_access_token, vertex_model_endpoint

SUPPORTED_ASPECT_RATIOS = {"9:16", "16:9"}
SUPPORTED_RESOLUTIONS = {"720p", "1080p"}


class GoogleVertexVideoProvider(VideoGenerationPort):
    """Vertex AI Veo video generation adapter (async via predictLongRunning)."""

    def __init__(
        self,
        project: str | None = None,
        location: str | None = None,
        model: str | None = None,
        output_dir: str | None = None,
        timeout: int = 60,
    ):
        self.project = (project or os.environ.get("GOOGLE_CLOUD_PROJECT", "")).strip()
        if not self.project:
            raise ValueError("GOOGLE_CLOUD_PROJECT is required for GoogleVertexVideoProvider")
        self.location = (location or os.environ.get("GOOGLE_CLOUD_LOCATION", "")).strip() or "us-central1"
        self.model = (model or os.environ.get("VIDEO_MODEL", "")).strip() or "veo-3.1-generate-001"
        self.timeout = int(timeout)

        configured_dir = output_dir or os.environ.get("HERMES_VIDEO_FACTORY_WORKSPACE", "")
        self.output_dir = Path(configured_dir).expanduser().resolve() if configured_dir else (Path.cwd() / "workspace")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # VideoGenerationPort
    # ------------------------------------------------------------------

    def generate(self, request: VideoGenerationRequest) -> VideoGenerationResult:
        try:
            token = get_access_token()
            body = self._submit_body(request)
            endpoint = vertex_model_endpoint(self.project, self.location, self.model, "predictLongRunning")
            response = requests.post(
                endpoint,
                headers={"Authorization": f"Bearer {token}"},
                json=body,
                timeout=self.timeout,
            )
            if response.status_code != 200:
                return VideoGenerationResult(
                    request_id=request.request_id,
                    success=False,
                    error_message=self._normalize_error(response),
                    metadata={"provider": "google_vertex", "http_status": response.status_code},
                )

            operation_name = response.json().get("name")
            if not operation_name:
                return VideoGenerationResult(
                    request_id=request.request_id,
                    success=False,
                    error_message="vertex predictLongRunning returned no operation name",
                    metadata={"provider": "google_vertex"},
                )

            return VideoGenerationResult(
                request_id=request.request_id,
                success=True,
                video_path=None,  # async; poll check_status
                provider_operation_id=operation_name,
                metadata={"provider": "google_vertex", "model": self.model, "status": "submitted"},
            )
        except Exception as error:  # noqa: BLE001 - normalize any adapter error
            return VideoGenerationResult(
                request_id=request.request_id,
                success=False,
                error_message=str(error),
                metadata={"provider": "google_vertex"},
            )

    def check_status(self, operation_id: str) -> VideoGenerationResult:
        try:
            token = get_access_token()
            endpoint = vertex_model_endpoint(self.project, self.location, self.model, "fetchPredictOperation")
            response = requests.post(
                endpoint,
                headers={"Authorization": f"Bearer {token}"},
                json={"operationName": operation_id},
                timeout=self.timeout,
            )
            if response.status_code != 200:
                return VideoGenerationResult(
                    request_id=operation_id,
                    success=False,
                    error_message=self._normalize_error(response),
                    metadata={"provider": "google_vertex", "http_status": response.status_code},
                )

            body = response.json()
            error = body.get("error")
            if error:
                return VideoGenerationResult(
                    request_id=operation_id,
                    success=False,
                    error_message=error.get("message", "") or f"vertex operation error: {error.get('status', '')}",
                    provider_operation_id=operation_id,
                    metadata={"provider": "google_vertex"},
                )

            if not body.get("done"):
                return VideoGenerationResult(
                    request_id=operation_id,
                    success=True,
                    video_path=None,
                    provider_operation_id=operation_id,
                    metadata={"provider": "google_vertex", "status": "running"},
                )

            return self._download_result(operation_id, body.get("response") or {})
        except Exception as error:  # noqa: BLE001
            return VideoGenerationResult(
                request_id=operation_id,
                success=False,
                error_message=str(error),
                provider_operation_id=operation_id,
                metadata={"provider": "google_vertex"},
            )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _submit_body(self, request: VideoGenerationRequest) -> dict[str, Any]:
        instance: dict[str, Any] = {"prompt": request.prompt}
        if request.reference_image_paths:
            first = Path(request.reference_image_paths[0])
            if first.is_file():
                instance["image"] = {
                    "bytesBase64Encoded": base64.b64encode(first.read_bytes()).decode("ascii"),
                    "mimeType": mime_for(first),
                }

        parameters: dict[str, Any] = {
            "durationSeconds": max(1, int(request.duration_seconds)),
        }
        provider_options = request.provider_options or {}
        if request.aspect_ratio in SUPPORTED_ASPECT_RATIOS:
            parameters["aspectRatio"] = request.aspect_ratio
        for key in ("resolution", "sampleCount", "seed", "enhancePrompt", "generateAudio", "personGeneration", "negativePrompt"):
            if key in provider_options:
                value = provider_options[key]
                if key == "resolution" and value not in SUPPORTED_RESOLUTIONS:
                    continue
                parameters[key] = value

        return {"instances": [instance], "parameters": parameters}

    def _download_result(self, operation_id: str, response: dict) -> VideoGenerationResult:
        videos = response.get("videos") or []
        if videos:
            video = videos[0]
            data = video.get("bytesBase64Encoded")
            if data:
                # operation_id shares a long identical prefix across calls; use
                # the trailing unique segment (UUID) so distinct operations never
                # overwrite each other on disk.
                segment = operation_id.rsplit("/", 1)[-1]
                segment = "".join(c for c in segment if c.isalnum() or c in "-_.") or "video"
                output_path = self.output_dir / f"{segment[:40]}.mp4"
                output_path.write_bytes(base64.b64decode(data))
                return VideoGenerationResult(
                    request_id=operation_id,
                    success=True,
                    video_path=str(output_path),
                    provider_operation_id=operation_id,
                    metadata={"provider": "google_vertex", "status": "completed"},
                )

        # Fallback: provider returned a GCS URI instead of inline bytes
        gcs_uri = response.get("gcsUri") or (videos[0].get("video", {}).get("gcsUri") if videos else None)
        if gcs_uri:
            return VideoGenerationResult(
                request_id=operation_id,
                success=False,
                error_message=f"provider returned gcsUri but GCS download is not configured: {gcs_uri}",
                provider_operation_id=operation_id,
                metadata={"provider": "google_vertex", "gcs_uri": gcs_uri},
            )

        return VideoGenerationResult(
            request_id=operation_id,
            success=False,
            error_message="vertex response contained no video bytes",
            provider_operation_id=operation_id,
            metadata={"provider": "google_vertex"},
        )

    @staticmethod
    def _normalize_error(response: requests.Response) -> str:
        try:
            body = response.json()
            message = body.get("error", {}).get("message", "")
            return f"vertex http {response.status_code}: {message}" if message else f"vertex http {response.status_code}"
        except ValueError:
            return f"vertex http {response.status_code}: non-JSON response (endpoint/model may not exist)"