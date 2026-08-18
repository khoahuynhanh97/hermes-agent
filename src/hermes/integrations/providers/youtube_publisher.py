"""YouTube Shorts publisher via YouTube Data API v3.

Implements PublisherPort for YouTube Shorts upload:
  authorize_url -> exchange_code -> refresh_access_token -> publish (resumable upload)

Config (env, server-side, never committed):
  YOUTUBE_CLIENT_ID
  YOUTUBE_CLIENT_SECRET
  YOUTUBE_REDIRECT_URI
  YOUTUBE_ACCESS_TOKEN
  YOUTUBE_REFRESH_TOKEN

YouTube Shorts = vertical video (9:16) + #Shorts in title or description.
All HTTP is mockable for tests. No fallback provider.
"""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlencode

import requests

from hermes.ports.publisher import PublishRequest, PublishResult, PublisherPort

_API_BASE = "https://www.googleapis.com/youtube/v3"
_TOKEN_URL = "https://oauth2.googleapis.com/token"
_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_SCOPES = "https://www.googleapis.com/auth/youtube.upload"
_DEFAULT_REDIRECT = "http://localhost:8000/api/publish/youtube/callback"


def _cfg(name: str, default: str = "") -> str:
    return os.environ.get(name, "").strip() or default


def authorize_url(
    client_id: str = "",
    redirect_uri: str = "",
    scope: str = _SCOPES,
    state: str = "",
) -> str:
    params = {
        "client_id": client_id or _cfg("YOUTUBE_CLIENT_ID"),
        "redirect_uri": redirect_uri or _cfg("YOUTUBE_REDIRECT_URI", _DEFAULT_REDIRECT),
        "response_type": "code",
        "scope": scope,
        "access_type": "offline",
        "prompt": "consent",
    }
    if state:
        params["state"] = state
    return f"{_AUTH_URL}?{urlencode(params)}"


def exchange_code(code: str, redirect_uri: str = "", timeout: int = 30) -> dict:
    data = {
        "code": code,
        "client_id": _cfg("YOUTUBE_CLIENT_ID"),
        "client_secret": _cfg("YOUTUBE_CLIENT_SECRET"),
        "redirect_uri": redirect_uri or _cfg("YOUTUBE_REDIRECT_URI", _DEFAULT_REDIRECT),
        "grant_type": "authorization_code",
    }
    resp = requests.post(_TOKEN_URL, data=data, timeout=timeout)
    return resp.json()


def refresh_access_token(refresh_token: str, timeout: int = 30) -> dict:
    data = {
        "client_id": _cfg("YOUTUBE_CLIENT_ID"),
        "client_secret": _cfg("YOUTUBE_CLIENT_SECRET"),
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }
    resp = requests.post(_TOKEN_URL, data=data, timeout=timeout)
    return resp.json()


class YouTubePublisher(PublisherPort):
    def __init__(
        self,
        access_token: str = "",
        refresh_token: str = "",
        timeout: int = 120,
    ):
        self.access_token = access_token or _cfg("YOUTUBE_ACCESS_TOKEN")
        self.refresh_token = refresh_token or _cfg("YOUTUBE_REFRESH_TOKEN")
        self.timeout = int(timeout)

    def publish(self, request: PublishRequest) -> PublishResult:
        if not self.access_token:
            return PublishResult(ok=False, error_message="YOUTUBE_ACCESS_TOKEN_REQUIRED")
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        try:
            body = {
                "snippet": {
                    "title": request.caption[:100],
                    "description": request.caption,
                    "tags": ["Shorts", "short"],
                    "categoryId": "22",
                },
                "status": {
                    "privacyStatus": request.visibility or "public",
                    "selfDeclaredMadeForKids": False,
                },
            }
            init_resp = requests.post(
                f"{_API_BASE}/videos",
                headers=headers,
                json=body,
                params={"part": "snippet,status", "uploadType": "resumable"},
                timeout=self.timeout,
            )
            if init_resp.status_code not in (200, 308):
                return self._err(init_resp)

            upload_url = init_resp.headers.get("Location", "")
            if not upload_url:
                return PublishResult(ok=False, error_message="YOUTUBE_NO_UPLOAD_URL")

            with open(request.video_path, "rb") as f:
                upload_resp = requests.put(
                    upload_url,
                    headers={"Content-Type": "video/*"},
                    data=f,
                    timeout=self.timeout,
                )
            if upload_resp.status_code not in (200, 201):
                return PublishResult(ok=False, error_message=f"upload failed: http {upload_resp.status_code}")

            video_id = upload_resp.json().get("id", "")
            return PublishResult(ok=True, post_id=video_id, status="processing")
        except Exception as error:  # noqa: BLE001
            return PublishResult(ok=False, error_message=str(error))

    def get_status(self, video_id: str) -> PublishResult:
        if not self.access_token:
            return PublishResult(ok=False, error_message="YOUTUBE_ACCESS_TOKEN_REQUIRED")
        try:
            resp = requests.get(
                f"{_API_BASE}/videos",
                headers={"Authorization": f"Bearer {self.access_token}"},
                params={"part": "status,processingDetails", "id": video_id},
                timeout=self.timeout,
            )
            if resp.status_code != 200:
                return self._err(resp)
            items = resp.json().get("items", [])
            if not items:
                return PublishResult(ok=False, error_message="YOUTUBE_VIDEO_NOT_FOUND")
            status_data = items[0].get("status", {})
            processing = items[0].get("processingDetails", {})
            upload_status = status_data.get("uploadStatus", "unknown")
            privacy = status_data.get("privacyStatus", "")
            pub_status = "published" if upload_status == "processed" else upload_status
            return PublishResult(ok=True, post_id=video_id, status=pub_status)
        except Exception as error:  # noqa: BLE001
            return PublishResult(ok=False, error_message=str(error))

    @staticmethod
    def _err(resp: requests.Response) -> PublishResult:
        try:
            body = resp.json()
            error = body.get("error", {})
            errors = error.get("errors", [])
            msg = errors[0].get("message", "") if errors else error.get("message", "")
        except ValueError:
            msg = f"http {resp.status_code}"
        return PublishResult(ok=False, error_message=f"youtube {resp.status_code}: {msg}".strip())
