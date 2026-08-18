"""Shared Google Cloud Vertex auth + endpoint helpers.

Reused by the Vertex image and video providers. Uses Application Default
Credentials (ADC / service account / gcloud auth). No credentials in code.
"""

from __future__ import annotations

import os

from google.auth import default as google_auth_default
from google.auth.transport import requests as auth_requests

CLOUD_PLATFORM_SCOPE = "https://www.googleapis.com/auth/cloud-platform"

_credentials = None
_credentials_project = None


def get_access_token() -> str:
    """Return a short-lived OAuth2 access token via ADC (cached credentials)."""
    global _credentials, _credentials_project
    if _credentials is None:
        credentials, project = google_auth_default(scopes=[CLOUD_PLATFORM_SCOPE])
        _credentials = credentials
        _credentials_project = project
    if not _credentials.valid:
        _credentials.refresh(auth_requests.Request())
    token = _credentials.token
    if not token:
        raise RuntimeError("google auth returned no access token")
    return token


def vertex_model_endpoint(project: str, location: str, model: str, action: str) -> str:
    """Vertex publisher model endpoint for an action (generateContent, predictLongRunning, ...)."""
    location = location or "us-central1"
    hostname = "aiplatform.googleapis.com" if location == "global" else f"{location}-aiplatform.googleapis.com"
    return (
        f"https://{hostname}/v1/projects/{project}"
        f"/locations/{location}/publishers/google/models/{model}:{action}"
    )


def vertex_required_project() -> str:
    project = (
        os.environ.get("GOOGLE_CLOUD_PROJECT", "").strip()
        or os.environ.get("VERTEX_PROJECT_ID", "").strip()
        or os.environ.get("GCP_PROJECT_ID", "").strip()
    )
    if not project:
        adc_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
        if adc_path and os.path.exists(adc_path):
            try:
                import json
                with open(adc_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    project = data.get("project_id", "").strip()
            except Exception:
                pass
    if not project:
        raise ValueError("GOOGLE_CLOUD_PROJECT, VERTEX_PROJECT_ID, or valid GOOGLE_APPLICATION_CREDENTIALS JSON is required for Vertex AI")
    return project
