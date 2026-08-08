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
    return (
        f"https://{location}-aiplatform.googleapis.com/v1/projects/{project}"
        f"/locations/{location}/publishers/google/models/{model}:{action}"
    )


def vertex_required_project() -> str:
    project = os.environ.get("GOOGLE_CLOUD_PROJECT", "").strip()
    if not project:
        raise ValueError("GOOGLE_CLOUD_PROJECT is required")
    return project