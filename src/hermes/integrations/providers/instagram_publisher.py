"""Instagram Reels publisher via Meta Graph API.

Implements PublisherPort for Instagram Reels upload:
  authorize_url -> exchange_code -> publish (container + publish)

Config (env, server-side, never committed):
  INSTAGRAM_CLIENT_ID
  INSTAGRAM_CLIENT_SECRET
  INSTAGRAM_REDIRECT_URI
  INSTAGRAM_ACCESS_TOKEN
  INSTAGRAM_BUSINESS_ACCOUNT_ID

All HTTP is mockable for tests. No fallback provider.
"""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlencode

import requests

from hermes.ports.publisher import PublishRequest, PublishResult, PublisherPort

_API_BASE = "https://graph.facebook.com/v18.0"
_AUTH_URL = "https://www.facebook.com/v18.0/dialog/oauth"
_TOKEN_URL = "https://graph.facebook.com/v18.0/oauth/access_token"
_SCOPES = "instagram_basic,instagram_content_publish,pages_read_engagement"
_DEFAULT_REDIRECT = "http://localhost:8000/api/publish/instagram/callback"


def _cfg(name: str, default: str = "") -> str:
    return os.environ.get(name, "").strip() or default


def authorize_url(
    client_id: str = "",
    redirect_uri: str = "",
    scope: str = _SCOPES,
    state: str = "",
) -> str:
    params = {
        "client_id": client_id or _cfg("INSTAGRAM_CLIENT_ID"),
        "redirect_uri": redirect_uri or _cfg("INSTAGRAM_REDIRECT_URI", _DEFAULT_REDIRECT),
        "scope": scope,
        "response_type": "code",
    }
    if state:
        params["state"] = state
    return f"{_AUTH_URL}?{urlencode(params)}"


def exchange_code(code: str, redirect_uri: str = "", timeout: int = 30) -> dict:
    params = {
        "client_id": _cfg("INSTAGRAM_CLIENT_ID"),
        "client_secret": _cfg("INSTAGRAM_CLIENT_SECRET"),
        "redirect_uri": redirect_uri or _cfg("INSTAGRAM_REDIRECT_URI", _DEFAULT_REDIRECT),
        "code": code,
    }
    resp = requests.get(_TOKEN_URL, params=params, timeout=timeout)
    return resp.json()


def exchange_long_lived(short_token: str, timeout: int = 30) -> dict:
    params = {
        "grant_type": "fb_exchange_token",
        "client_id": _cfg("INSTAGRAM_CLIENT_ID"),
        "client_secret": _cfg("INSTAGRAM_CLIENT_SECRET"),
        "fb_exchange_token": short_token,
    }
    resp = requests.get(_TOKEN_URL, params=params, timeout=timeout)
    return resp.json()


class InstagramPublisher(PublisherPort):
    def __init__(
        self,
        access_token: str = "",
        instagram_business_account_id: str = "",
        timeout: int = 120,
    ):
        self.access_token = access_token or _cfg("INSTAGRAM_ACCESS_TOKEN")
        self.ig_account_id = instagram_business_account_id or _cfg("INSTAGRAM_BUSINESS_ACCOUNT_ID")
        self.timeout = int(timeout)

    def publish(self, request: PublishRequest) -> PublishResult:
        if not self.access_token:
            return PublishResult(ok=False, error_message="INSTAGRAM_ACCESS_TOKEN_REQUIRED")
        if not self.ig_account_id:
            return PublishResult(ok=False, error_message="INSTAGRAM_BUSINESS_ACCOUNT_ID_REQUIRED")
        try:
            container_resp = requests.post(
                f"{_API_BASE}/{self.ig_account_id}/media",
                data={
                    "media_type": "REELS",
                    "video_url": request.video_path,
                    "caption": request.caption,
                    "share_to_feed": "true",
                    "access_token": self.access_token,
                },
                timeout=self.timeout,
            )
            container = container_resp.json()
            container_id = container.get("id", "")
            error = container.get("error", {})
            if error.get("message"):
                return PublishResult(ok=False, error_message=f"instagram container: {error.get('message', '')}")

            publish_resp = requests.post(
                f"{_API_BASE}/{self.ig_account_id}/media_publish",
                data={
                    "creation_id": container_id,
                    "access_token": self.access_token,
                },
                timeout=self.timeout,
            )
            publish_data = publish_resp.json()
            media_id = publish_data.get("id", "")
            pub_error = publish_data.get("error", {})
            if pub_error.get("message"):
                return PublishResult(ok=False, error_message=f"instagram publish: {pub_error.get('message', '')}")

            return PublishResult(ok=True, post_id=media_id, status="processing")
        except Exception as error:  # noqa: BLE001
            return PublishResult(ok=False, error_message=str(error))

    def get_status(self, media_id: str) -> PublishResult:
        if not self.access_token:
            return PublishResult(ok=False, error_message="INSTAGRAM_ACCESS_TOKEN_REQUIRED")
        try:
            resp = requests.get(
                f"{_API_BASE}/{media_id}",
                params={
                    "fields": "status_code,media_type",
                    "access_token": self.access_token,
                },
                timeout=self.timeout,
            )
            data = resp.json()
            error = data.get("error", {})
            if error.get("message"):
                return PublishResult(ok=False, error_message=f"instagram status: {error.get('message', '')}")
            status_code = data.get("status_code", "unknown")
            pub_status = "published" if status_code == "FINISHED" else status_code.lower()
            return PublishResult(ok=True, post_id=media_id, status=pub_status)
        except Exception as error:  # noqa: BLE001
            return PublishResult(ok=False, error_message=str(error))
