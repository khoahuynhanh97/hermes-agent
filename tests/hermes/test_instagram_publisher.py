"""Instagram publisher tests (all mocked, no real API calls)."""
import os
from unittest import mock

import pytest

from hermes.ports.publisher import PublishRequest
from hermes.integrations.providers.instagram_publisher import (
    InstagramPublisher,
    authorize_url,
    exchange_code,
    exchange_long_lived,
)


@pytest.fixture(autouse=True)
def _block_live_instagram(monkeypatch):
    """Block any real Instagram call from tests."""
    def _block(*a, **k):
        raise RuntimeError("live Instagram call blocked: tests must mock HTTP")
    monkeypatch.setattr("hermes.integrations.providers.instagram_publisher.requests.post", _block)
    monkeypatch.setattr("hermes.integrations.providers.instagram_publisher.requests.get", _block)


def test_authorize_url():
    os.environ["INSTAGRAM_CLIENT_ID"] = "ig123"
    url = authorize_url(state="mystate")
    assert url.startswith("https://www.facebook.com/v18.0/dialog/oauth?")
    assert "client_id=ig123" in url
    assert "state=mystate" in url
    assert "response_type=code" in url


def test_authorize_url_custom_redirect():
    url = authorize_url(client_id="cid", redirect_uri="https://my.app/cb")
    assert "redirect_uri=https%3A%2F%2Fmy.app%2Fcb" in url


def test_requires_access_token():
    os.environ.pop("INSTAGRAM_ACCESS_TOKEN", None)
    os.environ.pop("INSTAGRAM_BUSINESS_ACCOUNT_ID", None)
    pub = InstagramPublisher(access_token="", instagram_business_account_id="")
    r = pub.publish(PublishRequest(project_id="p", owner_user_id="o", video_path="x.mp4", caption="c"))
    assert r.ok is False
    assert "INSTAGRAM_ACCESS_TOKEN_REQUIRED" in r.error_message


def test_requires_business_account_id():
    os.environ["INSTAGRAM_ACCESS_TOKEN"] = "tok"
    os.environ.pop("INSTAGRAM_BUSINESS_ACCOUNT_ID", None)
    pub = InstagramPublisher(access_token="tok", instagram_business_account_id="")
    r = pub.publish(PublishRequest(project_id="p", owner_user_id="o", video_path="x.mp4", caption="c"))
    assert r.ok is False
    assert "INSTAGRAM_BUSINESS_ACCOUNT_ID_REQUIRED" in r.error_message


def test_publish_success():
    pub = InstagramPublisher(access_token="tok", instagram_business_account_id="ig_id_123")

    container_resp = mock.Mock()
    container_resp.json = mock.Mock(return_value={"id": "container_abc"})

    publish_resp = mock.Mock()
    publish_resp.json = mock.Mock(return_value={"id": "media_xyz"})

    def fake_post(url, data=None, **kwargs):
        if "media" in url and "media_publish" not in url:
            return container_resp
        return publish_resp

    with mock.patch("hermes.integrations.providers.instagram_publisher.requests.post", side_effect=fake_post):
        r = pub.publish(PublishRequest(project_id="p", owner_user_id="o", video_path="https://cdn.example.com/video.mp4", caption="test"))

    assert r.ok is True
    assert r.post_id == "media_xyz"
    assert r.status == "processing"


def test_publish_container_error():
    pub = InstagramPublisher(access_token="tok", instagram_business_account_id="ig_id")

    container_resp = mock.Mock()
    container_resp.json = mock.Mock(return_value={
        "error": {"message": "Invalid video url"}
    })

    with mock.patch("hermes.integrations.providers.instagram_publisher.requests.post", return_value=container_resp):
        r = pub.publish(PublishRequest(project_id="p", owner_user_id="o", video_path="bad", caption="c"))

    assert r.ok is False
    assert "Invalid video url" in r.error_message


def test_publish_publish_error():
    pub = InstagramPublisher(access_token="tok", instagram_business_account_id="ig_id")

    container_resp = mock.Mock()
    container_resp.json = mock.Mock(return_value={"id": "container_abc"})

    publish_resp = mock.Mock()
    publish_resp.json = mock.Mock(return_value={"error": {"message": "Publishing failed"}})

    def fake_post(url, data=None, **kwargs):
        if "media_publish" in url:
            return publish_resp
        return container_resp

    with mock.patch("hermes.integrations.providers.instagram_publisher.requests.post", side_effect=fake_post):
        r = pub.publish(PublishRequest(project_id="p", owner_user_id="o", video_path="v", caption="c"))

    assert r.ok is False
    assert "Publishing failed" in r.error_message


def test_get_status_success():
    pub = InstagramPublisher(access_token="tok", instagram_business_account_id="ig_id")
    resp = mock.Mock()
    resp.json = mock.Mock(return_value={"status_code": "FINISHED", "media_type": "VIDEO"})
    with mock.patch("hermes.integrations.providers.instagram_publisher.requests.get", return_value=resp):
        r = pub.get_status("media_123")

    assert r.ok is True
    assert r.post_id == "media_123"
    assert r.status == "published"


def test_get_status_processing():
    pub = InstagramPublisher(access_token="tok", instagram_business_account_id="ig_id")
    resp = mock.Mock()
    resp.json = mock.Mock(return_value={"status_code": "IN_PROGRESS", "media_type": "VIDEO"})
    with mock.patch("hermes.integrations.providers.instagram_publisher.requests.get", return_value=resp):
        r = pub.get_status("media_456")

    assert r.ok is True
    assert r.status == "in_progress"


def test_get_status_requires_token():
    os.environ.pop("INSTAGRAM_ACCESS_TOKEN", None)
    pub = InstagramPublisher(access_token="")
    r = pub.get_status("media_1")
    assert r.ok is False
    assert "INSTAGRAM_ACCESS_TOKEN_REQUIRED" in r.error_message


def test_get_status_api_error():
    pub = InstagramPublisher(access_token="tok", instagram_business_account_id="ig_id")
    resp = mock.Mock()
    resp.json = mock.Mock(return_value={"error": {"message": "Invalid token"}})
    with mock.patch("hermes.integrations.providers.instagram_publisher.requests.get", return_value=resp):
        r = pub.get_status("media_err")

    assert r.ok is False
    assert "Invalid token" in r.error_message


def test_exchange_code():
    os.environ["INSTAGRAM_CLIENT_ID"] = "cid"
    os.environ["INSTAGRAM_CLIENT_SECRET"] = "csec"
    resp = mock.Mock()
    resp.json = mock.Mock(return_value={"access_token": "long_tok", "token_type": "bearer"})
    with mock.patch("hermes.integrations.providers.instagram_publisher.requests.get", return_value=resp):
        data = exchange_code("auth_code_123")
    assert data["access_token"] == "long_tok"


def test_exchange_long_lived():
    os.environ["INSTAGRAM_CLIENT_ID"] = "cid"
    os.environ["INSTAGRAM_CLIENT_SECRET"] = "csec"
    resp = mock.Mock()
    resp.json = mock.Mock(return_value={"access_token": "ll_tok", "expires_in": 60})
    with mock.patch("hermes.integrations.providers.instagram_publisher.requests.get", return_value=resp):
        data = exchange_long_lived("short_tok")
    assert data["access_token"] == "ll_tok"


def test_publish_exception_handling():
    pub = InstagramPublisher(access_token="tok", instagram_business_account_id="ig_id")
    with mock.patch("hermes.integrations.providers.instagram_publisher.requests.post", side_effect=ConnectionError("network down")):
        r = pub.publish(PublishRequest(project_id="p", owner_user_id="o", video_path="v", caption="c"))

    assert r.ok is False
    assert "network down" in r.error_message
