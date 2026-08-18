"""TikTok publishing integration tests: API routes, publication store, error handling."""
from __future__ import annotations

import os
from unittest import mock

import pytest
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient

from hermes.adapters.sqlite.publisher_repository import SQLitePublicationStore
from hermes.db import Database
from hermes.domain.publisher import Publication, PublicationStatus
from hermes.integrations.providers.tiktok_publisher import TikTokPublisher, authorize_url
from hermes.ports.publisher import PublishRequest


@pytest.fixture(autouse=True)
def _no_live_tiktok(monkeypatch):
    """Block any real TikTok call from tests."""
    def _block(*a, **k):
        raise RuntimeError("live TikTok call blocked: tests must mock HTTP")
    monkeypatch.setattr("hermes.integrations.providers.tiktok_publisher.requests.post", _block)
    monkeypatch.setattr("hermes.integrations.providers.tiktok_publisher.requests.put", _block)


@pytest.fixture()
def _env(monkeypatch):
    monkeypatch.setenv("TIKTOK_CLIENT_KEY", "test_ck")
    monkeypatch.setenv("TIKTOK_CLIENT_SECRET", "test_cs")
    monkeypatch.setenv("TIKTOK_REDIRECT_URI", "http://127.0.0.1:3000/tiktok-callback")


@pytest.fixture()
def db(tmp_path):
    return Database(tmp_path / "pub_test.db")


@pytest.fixture()
def store(db):
    return SQLitePublicationStore(db)


@pytest.fixture()
def _app(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_DB_PATH", str(tmp_path / "app_pub.db"))
    monkeypatch.setenv("HERMES_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("TIKTOK_CLIENT_KEY", "test_ck")
    monkeypatch.setenv("TIKTOK_CLIENT_SECRET", "test_cs")
    monkeypatch.setenv("TIKTOK_REDIRECT_URI", "http://127.0.0.1:3000/tiktok-callback")

    from hermes.security.principal import PrincipalContext, set_current_principal, current_principal

    mock_principal = PrincipalContext(
        actor_id="test_actor",
        owner_user_id="test_owner",
        platform="web",
        session_id="test_session",
        roles=(),
    )

    test_app = FastAPI()

    @test_app.middleware("http")
    async def _set_principal(request, call_next):
        token = set_current_principal(mock_principal)
        try:
            return await call_next(request)
        finally:
            current_principal.reset(token)

    from hermes.channels.api.routes.publishing import router
    test_app.include_router(router, prefix="/api/publish")
    return test_app


# ── OAuth URL Generation ───────────────────────────────────────────────

def test_authorize_url_contains_required_params():
    os.environ["TIKTOK_CLIENT_KEY"] = "ck_abc"
    url = authorize_url("https://app.example/cb", scope="video.publish", state="u1")
    assert url.startswith("https://www.tiktok.com/v2/auth/authorize/")
    assert "client_key=ck_abc" in url
    assert "scope=video.publish" in url
    assert "state=u1" in url
    assert "response_type=code" in url


def test_authorize_url_encodes_redirect_uri():
    url = authorize_url("https://app.example/my path", scope="video.publish")
    assert "my" in url and "path" in url
    assert "+" in url or "%20" in url


# ── Publication Store ──────────────────────────────────────────────────

def test_store_upsert_creates_publication(store):
    p = Publication(
        publication_id="pub_1", project_id="proj_1", owner_user_id="owner_1",
        platform="tiktok", status=PublicationStatus.UPLOADING, caption="test cap",
        created_at="2025-01-01T00:00:00Z", updated_at="2025-01-01T00:00:00Z",
    )
    saved = store.upsert(p)
    assert saved.publication_id == "pub_1"
    got = store.get("owner_1", "proj_1", "tiktok")
    assert got is not None
    assert got.status == PublicationStatus.UPLOADING


def test_store_upsert_updates_existing(store):
    p1 = Publication(
        publication_id="pub_1", project_id="proj_1", owner_user_id="o",
        platform="tiktok", status=PublicationStatus.UPLOADING,
        created_at="2025-01-01T00:00:00Z", updated_at="2025-01-01T00:00:00Z",
    )
    store.upsert(p1)
    p2 = Publication(
        publication_id="pub_1", project_id="proj_1", owner_user_id="o",
        platform="tiktok", status=PublicationStatus.PROCESSING, post_id="tt_999",
        created_at="2025-01-01T00:00:00Z", updated_at="2025-01-01T00:00:00Z",
    )
    store.upsert(p2)
    got = store.get("o", "proj_1", "tiktok")
    assert got.status == PublicationStatus.PROCESSING
    assert got.post_id == "tt_999"


def test_store_update_status_sets_published_at(store):
    p = Publication(
        publication_id="pub_2", project_id="proj_2", owner_user_id="o",
        platform="tiktok", status=PublicationStatus.PROCESSING,
        created_at="2025-01-01T00:00:00Z", updated_at="2025-01-01T00:00:00Z",
    )
    store.upsert(p)
    store.update_status("o", "proj_2", "tiktok", PublicationStatus.PUBLISHED, post_id="tt_ok")
    got = store.get("o", "proj_2", "tiktok")
    assert got.status == PublicationStatus.PUBLISHED
    assert got.published_at is not None


def test_store_update_status_sets_error(store):
    p = Publication(
        publication_id="pub_3", project_id="proj_3", owner_user_id="o",
        platform="tiktok", status=PublicationStatus.UPLOADING,
        created_at="2025-01-01T00:00:00Z", updated_at="2025-01-01T00:00:00Z",
    )
    store.upsert(p)
    store.update_status("o", "proj_3", "tiktok", PublicationStatus.FAILED, last_error="upload timeout")
    got = store.get("o", "proj_3", "tiktok")
    assert got.status == PublicationStatus.FAILED
    assert got.last_error == "upload timeout"


def test_store_list_by_owner(store):
    for i in range(3):
        store.upsert(Publication(
            publication_id=f"pub_{i}", project_id=f"proj_{i}", owner_user_id="owner_1",
            platform="tiktok", status=PublicationStatus.PROCESSING,
            created_at=f"2025-01-0{i+1}T00:00:00Z", updated_at=f"2025-01-0{i+1}T00:00:00Z",
        ))
    pubs = store.list_by_owner("owner_1")
    assert len(pubs) == 3
    assert all(p.owner_user_id == "owner_1" for p in pubs)


def test_store_list_by_owner_empty(store):
    pubs = store.list_by_owner("nonexistent")
    assert pubs == []


# ── TikTok Publisher Integration ───────────────────────────────────────

def test_tiktok_publish_success(tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"fake-mp4")
    pub = TikTokPublisher(access_token="tok")

    def fake_post(url, headers=None, json=None, data=None, timeout=None):
        if "video/init" in url:
            return mock.Mock(status_code=200, json=lambda: {
                "data": {"upload_url": "https://upload.example/x", "publish_id": "pub_tk_123"}
            })
        return mock.Mock(status_code=200, json=lambda: {"error": {}})

    with mock.patch("hermes.integrations.providers.tiktok_publisher.requests.post", side_effect=fake_post), \
         mock.patch("hermes.integrations.providers.tiktok_publisher.requests.put") as put_mock:
        put_mock.return_value.status_code = 200
        r = pub.publish(PublishRequest(
            project_id="p1", owner_user_id="o1", video_path=str(video), caption="test",
        ))

    assert r.ok is True
    assert r.post_id == "pub_tk_123"
    assert r.status == "processing"


def test_tiktok_publish_no_token():
    os.environ.pop("TIKTOK_ACCESS_TOKEN", None)
    pub = TikTokPublisher(access_token="")
    r = pub.publish(PublishRequest(project_id="p", owner_user_id="o", video_path="x.mp4", caption="c"))
    assert r.ok is False
    assert "TIKTOK_ACCESS_TOKEN_REQUIRED" in r.error_message


def test_tiktok_get_status(tmp_path):
    pub = TikTokPublisher(access_token="tok")

    def fake_post(url, headers=None, json=None, data=None, timeout=None):
        return mock.Mock(status_code=200, json=lambda: {
            "data": {"status": "publish_complete"},
            "error": {},
        })

    with mock.patch("hermes.integrations.providers.tiktok_publisher.requests.post", side_effect=fake_post):
        r = pub.get_status("pub_123")

    assert r.ok is True
    assert r.status == "publish_complete"


# ── API Route Tests ────────────────────────────────────────────────────

def test_api_auth_url(_app):
    client = TestClient(_app)
    resp = client.get("/api/publish/tiktok/auth-url")
    assert resp.status_code == 200
    body = resp.json()
    assert "auth_url" in body
    assert "tiktok.com" in body["auth_url"]


def test_api_tiktok_status_disconnected(_app):
    os.environ.pop("TIKTOK_ACCESS_TOKEN", None)
    client = TestClient(_app)
    resp = client.get("/api/publish/tiktok/status")
    assert resp.status_code == 200
    assert resp.json()["connected"] is False


def test_api_tiktok_status_connected(_app):
    os.environ["TIKTOK_ACCESS_TOKEN"] = "test_token"
    client = TestClient(_app)
    resp = client.get("/api/publish/tiktok/status")
    assert resp.status_code == 200
    assert resp.json()["connected"] is True
    os.environ.pop("TIKTOK_ACCESS_TOKEN", None)


def test_api_publish_no_token(_app):
    os.environ.pop("TIKTOK_ACCESS_TOKEN", None)
    client = TestClient(_app)
    resp = client.post("/api/publish/tiktok", json={
        "project_id": "p1", "asset_id": "a1", "caption": "test",
    })
    assert resp.status_code == 400
    assert "not connected" in resp.json()["detail"].lower()


def test_api_youtube_status(_app):
    client = TestClient(_app)
    resp = client.get("/api/publish/youtube/status", params={"video_id": "test_vid"})
    assert resp.status_code in (200, 502)


def test_api_youtube_publish_no_video(_app):
    client = TestClient(_app)
    resp = client.post("/api/publish/youtube", params={
        "project_id": "p1", "video_path": "missing.mp4",
    })
    assert resp.status_code == 502


def test_api_instagram_status(_app):
    client = TestClient(_app)
    resp = client.get("/api/publish/instagram/status", params={"media_id": "test_media"})
    assert resp.status_code in (200, 502)


def test_api_instagram_publish_no_video(_app):
    client = TestClient(_app)
    resp = client.post("/api/publish/instagram", params={
        "project_id": "p1", "video_path": "missing.mp4",
    })
    assert resp.status_code == 502


def test_api_history_empty(_app):
    client = TestClient(_app)
    resp = client.get("/api/publish/history")
    assert resp.status_code == 200
    assert resp.json()["publications"] == []


def test_api_get_publication_not_found(_app):
    client = TestClient(_app)
    resp = client.get("/api/publish/tiktok/nonexistent_pub")
    assert resp.status_code == 404


def test_api_callback_exchange_error(_app, monkeypatch):
    def fake_exchange(code, redirect, timeout=30):
        return {"error": {"code": "invalid_code", "message": "bad code"}}
    monkeypatch.setattr("hermes.channels.api.routes.publishing.tiktok_exchange", fake_exchange)
    client = TestClient(_app)
    resp = client.post("/api/publish/tiktok/callback", json={"code": "bad", "state": ""})
    assert resp.status_code == 400
    assert "tiktok oauth error" in resp.json()["detail"].lower()


def test_api_callback_exchange_success(_app, monkeypatch):
    def fake_exchange(code, redirect, timeout=30):
        return {"data": {"access_token": "new_tok", "refresh_token": "ref", "expires_in": 86400, "scope": "video.publish"}}
    monkeypatch.setattr("hermes.channels.api.routes.publishing.tiktok_exchange", fake_exchange)
    client = TestClient(_app)
    resp = client.post("/api/publish/tiktok/callback", json={"code": "good", "state": ""})
    assert resp.status_code == 200
    body = resp.json()
    assert body["connected"] is True
    assert body["access_token"] == "new_tok"
