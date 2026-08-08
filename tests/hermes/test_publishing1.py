"""Publishing1 tests: TikTok publisher + publication store (all mocked, no real calls)."""
import asyncio
import os
from pathlib import Path
from unittest import mock

import pytest

from hermes.adapters.sqlite.publisher_repository import SQLitePublicationStore
from hermes.db import Database
from hermes.domain.publisher import Publication, PublicationStatus
from hermes.ports.publisher import PublishRequest
from providers.tiktok_publisher import TikTokPublisher


@pytest.fixture(autouse=True)
def _no_live_tiktok(monkeypatch):
    """Block any real TikTok call from tests."""
    def _block(*a, **k):
        raise RuntimeError("live TikTok call blocked: tests must mock HTTP")
    monkeypatch.setattr("providers.tiktok_publisher.requests.post", _block)
    monkeypatch.setattr("providers.tiktok_publisher.requests.put", _block)


def test_requires_access_token(tmp_path):
    os.environ.pop("TIKTOK_ACCESS_TOKEN", None)
    pub = TikTokPublisher(access_token="")
    r = pub.publish(PublishRequest(project_id="p", owner_user_id="o", video_path="x.mp4", caption="c"))
    assert r.ok is False
    assert "TIKTOK_ACCESS_TOKEN_REQUIRED" in r.error_message


def test_publish_flow_init_upload(tmp_path):
    video = tmp_path / "final_video.mp4"
    video.write_bytes(b"fake-mp4-bytes")
    pub = TikTokPublisher(access_token="tok")

    def fake_post(url, headers=None, json=None, data=None, timeout=None):
        if "video/init" in url:
            return mock.Mock(status_code=200, json=lambda: {
                "data": {"upload_url": "https://upload.example/x", "publish_id": "pub_123"}
            })
        return mock.Mock(status_code=200, json=lambda: {"error": {}})

    with mock.patch("providers.tiktok_publisher.requests.post", side_effect=fake_post), \
         mock.patch("providers.tiktok_publisher.requests.put") as put_mock:
        put_mock.return_value.status_code = 200
        r = pub.publish(PublishRequest(project_id="p", owner_user_id="o", video_path=str(video), caption="caption"))

    assert r.ok is True
    assert r.post_id == "pub_123"
    assert r.status == "processing"


def test_publish_api_error(tmp_path):
    video = tmp_path / "v.mp4"
    video.write_bytes(b"x")

    def fake_post(url, headers=None, json=None, data=None, timeout=None):
        return mock.Mock(status_code=200, json=lambda: {
            "error": {"code": "unaudited_client_can_only_post_to_private_accounts", "message": "audit required"}
        })

    pub = TikTokPublisher(access_token="tok")
    with mock.patch("providers.tiktok_publisher.requests.post", side_effect=fake_post):
        r = pub.publish(PublishRequest(project_id="p", owner_user_id="o", video_path=str(video), caption="c"))
    assert r.ok is False
    assert "audit required" in r.error_message


def test_publication_store_roundtrip(tmp_path):
    db = Database(tmp_path / "pub.db")
    store = SQLitePublicationStore(db)
    p = Publication(publication_id="pub_1", project_id="proj", owner_user_id="owner", platform="tiktok",
                    status=PublicationStatus.PROCESSING, post_id="t_1", caption="hi")
    store.upsert(p)
    got = store.get("owner", "proj", "tiktok")
    assert got is not None and got.status == PublicationStatus.PROCESSING and got.post_id == "t_1"
    store.update_status("owner", "proj", "tiktok", PublicationStatus.PUBLISHED, post_id="t_1")
    updated = store.get("owner", "proj", "tiktok")
    assert updated.status == PublicationStatus.PUBLISHED
    assert updated.published_at is not None


def test_api_publish_requires_ready_state(tmp_path):
    from aiohttp import web
    from aiohttp.test_utils import TestClient, TestServer
    from video_factory_api import build_routes

    os.environ["HERMES_VIDEO_FACTORY_DB_PATH"] = str(tmp_path / "t.db")
    os.environ["HERMES_VIDEO_FACTORY_WORKSPACE"] = str(tmp_path / "ws")
    app = web.Application()
    app.add_routes(build_routes())

    async def flow(c):
        async with c.post("/api/vf/projects?owner_user_id=web_owner", json={"project_id": "p1"}) as r:
            assert r.status == 201
        # draft project -> publish must be rejected (not ready_to_publish)
        async with c.post("/api/vf/projects/p1/publish?owner_user_id=web_owner", json={"caption": "c"}) as r:
            assert r.status == 400

    async def runner():
        s = TestServer(app)
        await s.start_server()
        c = TestClient(s)
        await c.start_server()
        try:
            await flow(c)
        finally:
            await c.close()
            await s.close()

    asyncio.run(runner())


def test_authorize_url():
    os.environ["TIKTOK_CLIENT_KEY"] = "ck"
    from providers.tiktok_publisher import authorize_url
    url = authorize_url("https://app.example/cb", scope="video.publish", state="abc")
    assert url.startswith("https://www.tiktok.com/v2/auth/authorize/")
    assert "client_key=ck" in url
    assert "redirect_uri=https%3A%2F%2Fapp.example%2Fcb" in url
