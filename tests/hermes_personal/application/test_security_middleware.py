from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from hermes_personal.application.middleware import (
    RequestBodySizeLimitMiddleware,
    TokenBucketRateLimiter,
    RateLimitMiddleware,
    configure_security_middleware,
)


def test_request_body_size_limit_middleware_rejects_oversized_payload():
    app = FastAPI()
    app.add_middleware(RequestBodySizeLimitMiddleware, max_body_bytes=100)

    @app.post("/test-upload")
    def upload(payload: dict):
        return {"status": "ok", "received": len(str(payload))}

    client = TestClient(app)

    # 1. Normal payload under 100 bytes -> 200 OK
    res_ok = client.post("/test-upload", json={"key": "small"})
    assert res_ok.status_code == 200
    assert res_ok.json()["status"] == "ok"

    # 2. Oversized payload over 100 bytes -> 413 Payload Too Large
    large_payload = {"key": "x" * 200}
    res_large = client.post("/test-upload", json=large_payload)
    assert res_large.status_code == 413
    assert res_large.json()["error"] == "Payload Too Large"
    assert res_large.json()["max_bytes"] == 100


def test_token_bucket_rate_limiter_allows_burst_and_enforces_limit():
    # 60 rpm = 1 req/sec, burst capacity = 2 tokens
    limiter = TokenBucketRateLimiter(rate_per_minute=60.0, burst=2)

    # 1st request at t=0 -> allowed
    ok1, _ = limiter.allow("user1", cost=1.0, now=1000.0)
    assert ok1 is True

    # 2nd request at t=0 -> allowed (burst used)
    ok2, _ = limiter.allow("user1", cost=1.0, now=1000.0)
    assert ok2 is True

    # 3rd request at t=0 -> rejected (out of tokens)
    ok3, retry_after = limiter.allow("user1", cost=1.0, now=1000.0)
    assert ok3 is False
    assert retry_after > 0.0

    # Request from different user -> allowed
    ok_user2, _ = limiter.allow("user2", cost=1.0, now=1000.0)
    assert ok_user2 is True

    # After 1.0s, 1 token refilled -> allowed
    ok4, _ = limiter.allow("user1", cost=1.0, now=1001.0)
    assert ok4 is True


def test_rate_limit_middleware_returns_429_with_retry_after():
    app = FastAPI()
    limiter = TokenBucketRateLimiter(rate_per_minute=60.0, burst=2)
    app.add_middleware(RateLimitMiddleware, limiter=limiter)

    @app.get("/api/data")
    def get_data():
        return {"data": "hello"}

    @app.get("/health")
    def health():
        return {"status": "ok"}

    client = TestClient(app)

    # 2 allowed requests
    r1 = client.get("/api/data", headers={"Authorization": "Bearer test_secret_token_123"})
    assert r1.status_code == 200

    r2 = client.get("/api/data", headers={"Authorization": "Bearer test_secret_token_123"})
    assert r2.status_code == 200

    # 3rd request exceeds limit -> 429
    r3 = client.get("/api/data", headers={"Authorization": "Bearer test_secret_token_123"})
    assert r3.status_code == 429
    assert r3.json()["error"] == "Too Many Requests"
    assert "Retry-After" in r3.headers

    # Excluded path (/health) is never rate limited
    r_health = client.get("/health")
    assert r_health.status_code == 200


def test_configure_security_middleware_cors_and_limits():
    app = FastAPI()
    configure_security_middleware(
        app=app,
        max_body_bytes=500,
        rate_per_minute=300.0,
        burst=10,
        cors_allowed_origins=["https://dashboard.example.com"],
    )

    @app.get("/api/items")
    def get_items():
        return {"items": [1, 2, 3]}

    client = TestClient(app)

    # CORS Preflight request
    res = client.options(
        "/api/items",
        headers={
            "Origin": "https://dashboard.example.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert res.status_code == 200
    assert res.headers.get("access-control-allow-origin") == "https://dashboard.example.com"
