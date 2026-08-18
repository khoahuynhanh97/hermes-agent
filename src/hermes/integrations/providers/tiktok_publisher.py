"""TikTok Content Posting API publisher (Publishing1).

Implements PublisherPort for the TikTok Direct Post flow:
  creator_info/query -> video/init (FILE_UPLOAD) -> PUT upload_url -> status/fetch

Config (env, server-side, never committed):
  TIKTOK_CLIENT_KEY
  TIKTOK_CLIENT_SECRET
  TIKTOK_REDIRECT_URI
  TIKTOK_ACCESS_TOKEN      (24h, from user OAuth authorization)
  TIKTOK_REFRESH_TOKEN     (365d, rotating)

Auth helpers live here so the UI/server can build the authorize URL and
exchange/refresh tokens; the publisher itself only needs a valid access token.
All HTTP is mockable for tests. No fallback provider.
"""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlencode

import requests

from hermes.ports.publisher import PublishRequest, PublishResult, PublisherPort

BASE = "https://open.tiktokapis.com"
AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"


def _cfg(name: str, default: str = "") -> str:
    return os.environ.get(name, "").strip() or default


def authorize_url(redirect_uri: str, scope: str = "video.publish", state: str = "") -> str:
    params = {
        "client_key": _cfg("TIKTOK_CLIENT_KEY"),
        "response_type": "code",
        "scope": scope,
        "redirect_uri": redirect_uri,
        "state": state,
    }
    return f"{AUTH_URL}?{urlencode(params)}"


def exchange_code(code: str, redirect_uri: str, timeout: int = 30) -> dict:
    """Exchange authorization code for access/refresh tokens."""
    data = {
        "client_key": _cfg("TIKTOK_CLIENT_KEY"),
        "client_secret": _cfg("TIKTOK_CLIENT_SECRET"),
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri,
    }
    resp = requests.post(f"{BASE}/v2/oauth/token/", data=data, timeout=timeout)
    return resp.json()


def refresh_token(token: str, timeout: int = 30) -> dict:
    data = {
        "client_key": _cfg("TIKTOK_CLIENT_KEY"),
        "client_secret": _cfg("TIKTOK_CLIENT_SECRET"),
        "grant_type": "refresh_token",
        "refresh_token": token,
    }
    resp = requests.post(f"{BASE}/v2/oauth/token/", data=data, timeout=timeout)
    return resp.json()


class TikTokPublisher(PublisherPort):
    def __init__(self, access_token: str | None = None, timeout: int = 120):
        self.access_token = access_token or _cfg("TIKTOK_ACCESS_TOKEN")
        self.timeout = int(timeout)

    def publish(self, request: PublishRequest) -> PublishResult:
        if not self.access_token:
            return PublishResult(ok=False, error_message="TIKTOK_ACCESS_TOKEN_REQUIRED")
        headers = {"Authorization": f"Bearer {self.access_token}", "Content-Type": "application/json"}
        try:
            init = requests.post(
                f"{BASE}/v2/post/publish/video/init/",
                headers=headers,
                json={
                    "post_info": {"title": request.caption[:2200], "privacy_level": request.visibility},
                    "source_info": {"source": "FILE_UPLOAD", "video_size": self._file_size(request.video_path)},
                },
                timeout=self.timeout,
            ).json()
            if init.get("error", {}).get("code"):
                return self._err(init)
            upload_url = init["data"]["upload_url"]
            publish_id = init["data"]["publish_id"]

            with open(request.video_path, "rb") as f:
                put = requests.put(upload_url, data=f, timeout=self.timeout)
            if put.status_code != 200:
                return PublishResult(ok=False, error_message=f"upload failed: http {put.status_code}")

            return PublishResult(ok=True, post_id=publish_id, status="processing")
        except Exception as error:  # noqa: BLE001
            return PublishResult(ok=False, error_message=str(error))

    def get_status(self, publish_id: str) -> PublishResult:
        if not self.access_token:
            return PublishResult(ok=False, error_message="TIKTOK_ACCESS_TOKEN_REQUIRED")
        headers = {"Authorization": f"Bearer {self.access_token}", "Content-Type": "application/json"}
        try:
            resp = requests.post(
                f"{BASE}/v2/post/publish/status/fetch/",
                headers=headers,
                json={"publish_id": publish_id},
                timeout=self.timeout,
            ).json()
            status = resp.get("data", {}).get("status", "")
            error = resp.get("error", {})
            if error.get("code"):
                return self._err(resp)
            return PublishResult(ok=True, post_id=publish_id, status=status)
        except Exception as error:  # noqa: BLE001
            return PublishResult(ok=False, error_message=str(error))

    @staticmethod
    def _file_size(path: str) -> int:
        try:
            return os.path.getsize(path)
        except OSError:
            return 0

    @staticmethod
    def _err(body: dict[str, Any]) -> PublishResult:
        error = body.get("error", {})
        return PublishResult(
            ok=False,
            error_message=f"tiktok {error.get('code', '')}: {error.get('message', '')}".strip(),
        )
