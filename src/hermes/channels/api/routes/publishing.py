"""FastAPI routes for social publishing (TikTok, YouTube Shorts, Instagram Reels)."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel

from hermes.channels.api.dependencies import get_authenticated_principal_context, verify_owner_match
from hermes.security.principal import PrincipalContext
from hermes.db import Database, utc_now
from hermes.config import get_data_path
from hermes.adapters.sqlite.publisher_repository import SQLitePublicationStore
from hermes.domain.publisher import Publication, PublicationStatus
from hermes.ports.publisher import PublishRequest
from hermes.integrations.providers.tiktok_publisher import (
    TikTokPublisher,
    authorize_url as tiktok_auth_url,
    exchange_code as tiktok_exchange,
)
from hermes.integrations.providers.youtube_publisher import (
    authorize_url as youtube_auth_url,
    exchange_code as youtube_exchange,
    refresh_access_token as youtube_refresh,
    YouTubePublisher,
)
from hermes.integrations.providers.instagram_publisher import (
    authorize_url as instagram_auth_url,
    exchange_code as instagram_exchange,
    InstagramPublisher,
)

router = APIRouter()


def _db_path() -> Path:
    configured = os.environ.get("HERMES_DB_PATH", "").strip()
    return Path(configured).expanduser().resolve() if configured else get_data_path("db", "hermes.db")


def _pub_store() -> SQLitePublicationStore:
    db = Database(str(_db_path()))
    return SQLitePublicationStore(db)


def _new_id(prefix: str = "pub") -> str:
    import uuid
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def _redirect_uri() -> str:
    return os.environ.get("TIKTOK_REDIRECT_URI", "http://127.0.0.1:3000/tiktok-callback")


# ── TikTok ──────────────────────────────────────────────────────────────

@router.get("/tiktok/auth-url")
def tiktok_get_auth_url(
    principal: PrincipalContext = Depends(get_authenticated_principal_context),
) -> dict:
    redirect = _redirect_uri()
    url = tiktok_auth_url(redirect_uri=redirect, state=principal.owner_user_id)
    return {"status": "ok", "auth_url": url, "redirect_uri": redirect}


class TikTokCallbackRequest(BaseModel):
    code: str
    state: str = ""


@router.post("/tiktok/callback")
def tiktok_callback(
    body: TikTokCallbackRequest,
    principal: PrincipalContext = Depends(get_authenticated_principal_context),
) -> dict:
    redirect = _redirect_uri()
    try:
        data = tiktok_exchange(body.code, redirect)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"TIKTOK_TOKEN_EXCHANGE_FAILED: {e}")
    resp_data = data.get("data", {})
    error = data.get("error", {})
    if error.get("code"):
        raise HTTPException(status_code=400, detail=f"TikTok OAuth error: {error.get('message', 'unknown')}")
    access_token = resp_data.get("access_token", "")
    if not access_token:
        raise HTTPException(status_code=400, detail="No access token returned from TikTok")
    return {
        "status": "ok",
        "connected": True,
        "access_token": access_token,
        "refresh_token": resp_data.get("refresh_token", ""),
        "expires_in": resp_data.get("expires_in", 0),
        "scopes": resp_data.get("scope", "").split(",") if resp_data.get("scope") else [],
    }


@router.get("/tiktok/status")
def tiktok_status(
    principal: PrincipalContext = Depends(get_authenticated_principal_context),
) -> dict:
    publisher = TikTokPublisher()
    connected = bool(publisher.access_token)
    return {"status": "ok", "connected": connected}


class PublishTikTokRequest(BaseModel):
    project_id: str
    asset_id: str
    video_path: str = ""
    caption: str = ""
    visibility: str = "public"


@router.post("/tiktok")
def publish_to_tiktok(
    body: PublishTikTokRequest,
    principal: PrincipalContext = Depends(get_authenticated_principal_context),
) -> dict:
    publisher = TikTokPublisher()
    if not publisher.access_token:
        raise HTTPException(status_code=400, detail="TikTok not connected. Complete OAuth first.")

    pub_id = _new_id("pub")
    now = utc_now()
    publication = Publication(
        publication_id=pub_id,
        project_id=body.project_id,
        owner_user_id=principal.owner_user_id,
        platform="tiktok",
        status=PublicationStatus.UPLOADING,
        caption=body.caption,
        created_at=now,
        updated_at=now,
    )
    store = _pub_store()
    store.upsert(publication)

    request = PublishRequest(
        project_id=body.project_id,
        owner_user_id=principal.owner_user_id,
        video_path=body.video_path,
        caption=body.caption,
        visibility=body.visibility,
    )
    result = publisher.publish(request)

    if result.ok:
        store.update_status(
            principal.owner_user_id, body.project_id, "tiktok",
            PublicationStatus.PROCESSING, post_id=result.post_id,
        )
        return {
            "status": "ok",
            "publication_id": pub_id,
            "platform_post_id": result.post_id,
            "publication_status": "processing",
        }
    else:
        store.update_status(
            principal.owner_user_id, body.project_id, "tiktok",
            PublicationStatus.FAILED, last_error=result.error_message,
        )
        raise HTTPException(status_code=502, detail=f"TikTok publish failed: {result.error_message}")


@router.get("/tiktok/{publication_id}")
def get_tiktok_publication(
    publication_id: str,
    principal: PrincipalContext = Depends(get_authenticated_principal_context),
) -> dict:
    store = _pub_store()
    with store._database.connect() as conn:
        row = conn.execute(
            "SELECT * FROM publications WHERE publication_id=? AND owner_user_id=?",
            (publication_id, principal.owner_user_id),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Publication not found")
    return {
        "status": "ok",
        "publication": {
            "id": row["publication_id"],
            "platform": row["platform"],
            "project_id": row["project_id"],
            "status": row["status"],
            "platform_post_id": row["post_id"],
            "caption": row["caption"],
            "published_at": row["published_at"],
            "last_error": row["last_error"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        },
    }


# ── Publication History ─────────────────────────────────────────────────

@router.get("/history")
def publication_history(
    project_id: Optional[str] = Query(None),
    principal: PrincipalContext = Depends(get_authenticated_principal_context),
) -> dict:
    store = _pub_store()
    with store._database.connect() as conn:
        if project_id:
            rows = conn.execute(
                "SELECT * FROM publications WHERE owner_user_id=? AND project_id=? ORDER BY updated_at DESC",
                (principal.owner_user_id, project_id),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM publications WHERE owner_user_id=? ORDER BY updated_at DESC",
                (principal.owner_user_id,),
            ).fetchall()
    publications = [
        {
            "id": row["publication_id"],
            "platform": row["platform"],
            "project_id": row["project_id"],
            "status": row["status"],
            "platform_post_id": row["post_id"],
            "caption": row["caption"],
            "published_at": row["published_at"],
            "last_error": row["last_error"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
        for row in rows
    ]
    return {"status": "ok", "publications": publications}


# ── YouTube Shorts ──────────────────────────────────────────────────────


@router.get("/youtube/auth-url")
def youtube_get_auth_url(
    state: str = "",
    principal: PrincipalContext = Depends(get_authenticated_principal_context),
) -> Dict[str, Any]:
    url = youtube_auth_url(state=state)
    return {"status": "ok", "auth_url": url}


class YouTubeCallbackRequest(BaseModel):
    code: str
    redirect_uri: str = ""


@router.post("/youtube/callback")
def youtube_callback(
    body: YouTubeCallbackRequest,
    principal: PrincipalContext = Depends(get_authenticated_principal_context),
) -> Dict[str, Any]:
    try:
        data = youtube_exchange(body.code, redirect_uri=body.redirect_uri)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"YOUTUBE_TOKEN_EXCHANGE_FAILED: {e}")
    if "error" in data:
        raise HTTPException(status_code=400, detail=f"YOUTUBE_OAUTH_ERROR: {data['error']}")
    return {"status": "ok", "data": data}


@router.post("/youtube")
def youtube_publish(
    project_id: str,
    video_path: str,
    caption: str = "",
    visibility: str = "public",
    owner_user_id: Optional[str] = None,
    principal: PrincipalContext = Depends(get_authenticated_principal_context),
) -> Dict[str, Any]:
    owner = verify_owner_match(owner_user_id, principal)
    publisher = YouTubePublisher()
    result = publisher.publish(
        PublishRequest(
            project_id=project_id,
            owner_user_id=owner,
            video_path=video_path,
            caption=caption,
            visibility=visibility,
        )
    )
    if not result.ok:
        raise HTTPException(status_code=502, detail=result.error_message)
    return {"status": "ok", "post_id": result.post_id, "publish_status": result.status}


@router.get("/youtube/status")
def youtube_status(
    video_id: str,
    principal: PrincipalContext = Depends(get_authenticated_principal_context),
) -> Dict[str, Any]:
    publisher = YouTubePublisher()
    result = publisher.get_status(video_id)
    if not result.ok:
        raise HTTPException(status_code=502, detail=result.error_message)
    return {"status": "ok", "post_id": result.post_id, "publish_status": result.status}


# ── Instagram Reels ─────────────────────────────────────────────────────


@router.get("/instagram/auth-url")
def instagram_get_auth_url(
    state: str = "",
    principal: PrincipalContext = Depends(get_authenticated_principal_context),
) -> Dict[str, Any]:
    url = instagram_auth_url(state=state)
    return {"status": "ok", "auth_url": url}


class InstagramCallbackRequest(BaseModel):
    code: str
    redirect_uri: str = ""


@router.post("/instagram/callback")
def instagram_callback(
    body: InstagramCallbackRequest,
    principal: PrincipalContext = Depends(get_authenticated_principal_context),
) -> Dict[str, Any]:
    try:
        data = instagram_exchange(body.code, redirect_uri=body.redirect_uri)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"INSTAGRAM_TOKEN_EXCHANGE_FAILED: {e}")
    if "error" in data:
        raise HTTPException(status_code=400, detail=f"INSTAGRAM_OAUTH_ERROR: {data['error']}")
    return {"status": "ok", "data": data}


@router.post("/instagram")
def instagram_publish(
    project_id: str,
    video_path: str,
    caption: str = "",
    owner_user_id: Optional[str] = None,
    principal: PrincipalContext = Depends(get_authenticated_principal_context),
) -> Dict[str, Any]:
    owner = verify_owner_match(owner_user_id, principal)
    publisher = InstagramPublisher()
    result = publisher.publish(
        PublishRequest(
            project_id=project_id,
            owner_user_id=owner,
            video_path=video_path,
            caption=caption,
        )
    )
    if not result.ok:
        raise HTTPException(status_code=502, detail=result.error_message)
    return {"status": "ok", "post_id": result.post_id, "publish_status": result.status}


@router.get("/instagram/status")
def instagram_status(
    media_id: str,
    principal: PrincipalContext = Depends(get_authenticated_principal_context),
) -> Dict[str, Any]:
    publisher = InstagramPublisher()
    result = publisher.get_status(media_id)
    if not result.ok:
        raise HTTPException(status_code=502, detail=result.error_message)
    return {"status": "ok", "post_id": result.post_id, "publish_status": result.status}
