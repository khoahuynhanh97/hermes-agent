"""YouTube publisher tests (all mocked, no real API calls)."""
import os
from unittest import mock

import pytest

from hermes.ports.publisher import PublishRequest
from hermes.integrations.providers.youtube_publisher import (
    YouTubePublisher,
    authorize_url,
    exchange_code,
    refresh_access_token,
)


@pytest.fixture(autouse=True)
def _block_live_youtube(monkeypatch):
    """Block any real YouTube call from tests."""
    def _block(*a, **k):
        raise RuntimeError("live YouTube call blocked: tests must mock HTTP")
    monkeypatch.setattr("hermes.integrations.providers.youtube_publisher.requests.post", _block)
    monkeypatch.setattr("hermes.integrations.providers.youtube_publisher.requests.put", _block)
    monkeypatch.setattr("hermes.integrations.providers.youtube_publisher.requests.get", _block)


def test_authorize_url():
    os.environ["YOUTUBE_CLIENT_ID"] = "yk123"
    url = authorize_url(state="mystate")
    assert url.startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    assert "client_id=yk123" in url
    assert "state=mystate" in url
    assert "access_type=offline" in url
    assert "prompt=consent" in url
    assert "scope=https" in url


def test_authorize_url_custom_redirect():
    url = authorize_url(client_id="cid", redirect_uri="https://my.app/cb")
    assert "redirect_uri=https%3A%2F%2Fmy.app%2Fcb" in url


def test_requires_access_token():
    os.environ.pop("YOUTUBE_ACCESS_TOKEN", None)
    pub = YouTubePublisher(access_token="")
    r = pub.publish(PublishRequest(project_id="p", owner_user_id="o", video_path="x.mp4", caption="c"))
    assert r.ok is False
    assert "YOUTUBE_ACCESS_TOKEN_REQUIRED" in r.error_message


def test_publish_success(tmp_path):
    video = tmp_path / "final_video.mp4"
    video.write_bytes(b"fake-mp4-bytes")
    pub = YouTubePublisher(access_token="tok")

    init_resp = mock.Mock(status_code=200, headers={"Location": "https://upload.youtube/x"})
    init_resp.json = mock.Mock(return_value={})

    upload_resp = mock.Mock(status_code=200)
    upload_resp.json = mock.Mock(return_value={"id": "vid_abc123"})

    with mock.patch("hermes.integrations.providers.youtube_publisher.requests.post", return_value=init_resp), \
         mock.patch("hermes.integrations.providers.youtube_publisher.requests.put", return_value=upload_resp):
        r = pub.publish(PublishRequest(project_id="p", owner_user_id="o", video_path=str(video), caption="c"))

    assert r.ok is True
    assert r.post_id == "vid_abc123"
    assert r.status == "processing"


def test_publish_no_upload_url(tmp_path):
    video = tmp_path / "v.mp4"
    video.write_bytes(b"x")
    pub = YouTubePublisher(access_token="tok")

    init_resp = mock.Mock(status_code=200, headers={})
    init_resp.json = mock.Mock(return_value={})

    with mock.patch("hermes.integrations.providers.youtube_publisher.requests.post", return_value=init_resp):
        r = pub.publish(PublishRequest(project_id="p", owner_user_id="o", video_path=str(video), caption="c"))

    assert r.ok is False
    assert "YOUTUBE_NO_UPLOAD_URL" in r.error_message


def test_publish_api_error(tmp_path):
    video = tmp_path / "v.mp4"
    video.write_bytes(b"x")
    pub = YouTubePublisher(access_token="tok")

    init_resp = mock.Mock(status_code=403)
    init_resp.json = mock.Mock(return_value={
        "error": {"code": 403, "message": "quota exceeded", "errors": [{"message": "quota exceeded"}]}
    })

    with mock.patch("hermes.integrations.providers.youtube_publisher.requests.post", return_value=init_resp):
        r = pub.publish(PublishRequest(project_id="p", owner_user_id="o", video_path=str(video), caption="c"))

    assert r.ok is False
    assert "quota exceeded" in r.error_message


def test_get_status_success():
    pub = YouTubePublisher(access_token="tok")
    resp = mock.Mock(status_code=200)
    resp.json = mock.Mock(return_value={
        "items": [{"status": {"uploadStatus": "processed", "privacyStatus": "public"}, "processingDetails": {}}]
    })
    with mock.patch("hermes.integrations.providers.youtube_publisher.requests.get", return_value=resp):
        r = pub.get_status("vid_123")

    assert r.ok is True
    assert r.post_id == "vid_123"
    assert r.status == "published"


def test_get_status_not_found():
    pub = YouTubePublisher(access_token="tok")
    resp = mock.Mock(status_code=200)
    resp.json = mock.Mock(return_value={"items": []})
    with mock.patch("hermes.integrations.providers.youtube_publisher.requests.get", return_value=resp):
        r = pub.get_status("vid_missing")

    assert r.ok is False
    assert "YOUTUBE_VIDEO_NOT_FOUND" in r.error_message


def test_get_status_requires_token():
    os.environ.pop("YOUTUBE_ACCESS_TOKEN", None)
    pub = YouTubePublisher(access_token="")
    r = pub.get_status("vid_1")
    assert r.ok is False
    assert "YOUTUBE_ACCESS_TOKEN_REQUIRED" in r.error_message


def test_exchange_code():
    os.environ["YOUTUBE_CLIENT_ID"] = "cid"
    os.environ["YOUTUBE_CLIENT_SECRET"] = "csec"
    resp = mock.Mock()
    resp.json = mock.Mock(return_value={"access_token": "new_tok", "refresh_token": "ref_tok"})
    with mock.patch("hermes.integrations.providers.youtube_publisher.requests.post", return_value=resp):
        data = exchange_code("auth_code_123")
    assert data["access_token"] == "new_tok"
    assert data["refresh_token"] == "ref_tok"


def test_refresh_access_token():
    os.environ["YOUTUBE_CLIENT_ID"] = "cid"
    os.environ["YOUTUBE_CLIENT_SECRET"] = "csec"
    resp = mock.Mock()
    resp.json = mock.Mock(return_value={"access_token": "refreshed_tok"})
    with mock.patch("hermes.integrations.providers.youtube_publisher.requests.post", return_value=resp):
        data = refresh_access_token("old_refresh")
    assert data["access_token"] == "refreshed_tok"


def test_publish_exception_handling(tmp_path):
    video = tmp_path / "v.mp4"
    video.write_bytes(b"x")
    pub = YouTubePublisher(access_token="tok")

    with mock.patch("hermes.integrations.providers.youtube_publisher.requests.post", side_effect=ConnectionError("network down")):
        r = pub.publish(PublishRequest(project_id="p", owner_user_id="o", video_path=str(video), caption="c"))

    assert r.ok is False
    assert "network down" in r.error_message
