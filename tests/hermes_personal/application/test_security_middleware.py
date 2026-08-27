from __future__ import annotations

import pytest
from pydantic import BaseModel
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from hermes_personal.application.middleware import (
    RequestBodySizeLimitMiddleware,
    TokenBucketRateLimiter,
    RateLimitMiddleware,
    configure_security_middleware,
)


class TypedPayload(BaseModel):
    name: str


def test_request_body_size_limit_middleware_declared_content_length():
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


def test_request_body_size_limit_exact_limit_payload_allowed():
    app = FastAPI()
    app.add_middleware(RequestBodySizeLimitMiddleware, max_body_bytes=50)

    @app.post("/test-raw")
    async def upload_raw(request: Request):
        body = await request.body()
        return {"len": len(body)}

    client = TestClient(app)

    # Exact limit (50 bytes) -> allowed 200 OK
    res = client.post("/test-raw", content=b"a" * 50)
    assert res.status_code == 200
    assert res.json()["len"] == 50

    # 51 bytes -> rejected 413
    res_over = client.post("/test-raw", content=b"a" * 51)
    assert res_over.status_code == 413


def test_request_body_size_limit_chunked_streaming_payload_rejected_when_exceeding_limit():
    app = FastAPI()
    app.add_middleware(RequestBodySizeLimitMiddleware, max_body_bytes=60)

    @app.post("/test-stream")
    async def upload_stream(request: Request):
        body = await request.body()
        return {"len": len(body)}

    client = TestClient(app)

    def data_generator_under():
        yield b"chunk1_"
        yield b"chunk2_"

    # Streamed payload totaling 14 bytes (< 60) -> 200 OK
    res_stream_ok = client.post("/test-stream", content=data_generator_under())
    assert res_stream_ok.status_code == 200

    def data_generator_over():
        for _ in range(10):
            yield b"x" * 20  # 200 bytes total

    # Streamed payload totaling 200 bytes (> 60) -> 413 Payload Too Large
    res_stream_over = client.post("/test-stream", content=data_generator_over())
    assert res_stream_over.status_code == 413
    assert res_stream_over.json()["error"] == "Payload Too Large"


def test_request_body_size_limit_typed_json_streaming_rejected_with_413():
    """FastAPI typed endpoint parsing JSON must return 413 (not 400/422) when chunked body exceeds limit."""
    app = FastAPI()
    app.add_middleware(RequestBodySizeLimitMiddleware, max_body_bytes=50)

    endpoint_invoked = False

    @app.post("/test-typed")
    def typed_handler(payload: TypedPayload):
        nonlocal endpoint_invoked
        endpoint_invoked = True
        return {"name": payload.name}

    client = TestClient(app)

    # 1. Normal typed JSON under limit -> 200 OK
    res_ok = client.post("/test-typed", json={"name": "alice"})
    assert res_ok.status_code == 200
    assert res_ok.json()["name"] == "alice"
    assert endpoint_invoked is True

    # 2. Oversized typed JSON chunked stream without Content-Length -> 413 (NOT 400 or 422)
    endpoint_invoked = False

    def chunked_json_generator():
        yield b'{"name": "'
        yield b'a' * 100
        yield b'"}'

    res_stream_typed = client.post(
        "/test-typed",
        content=chunked_json_generator(),
        headers={"Content-Type": "application/json"},
    )
    assert res_stream_typed.status_code == 413
    assert res_stream_typed.json()["error"] == "Payload Too Large"
    assert res_stream_typed.json()["max_bytes"] == 50
    assert endpoint_invoked is False


@pytest.mark.anyio
async def test_request_body_size_limit_direct_asgi_rejection_at_crossing_chunk_no_further_read():
    """Direct ASGI execution proves rejection at crossing chunk with no further chunk reads and no endpoint execution."""
    endpoint_invoked = False

    async def sample_app(scope, receive, send):
        nonlocal endpoint_invoked
        # Consume all chunks in request body
        while True:
            msg = await receive()
            if not msg.get("more_body", False):
                break
        endpoint_invoked = True
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    middleware = RequestBodySizeLimitMiddleware(sample_app, max_body_bytes=30)

    chunks = [
        {"type": "http.request", "body": b"1234567890", "more_body": True},   # 10 bytes (< 30)
        {"type": "http.request", "body": b"1234567890", "more_body": True},   # 20 bytes (< 30)
        {"type": "http.request", "body": b"123456789012345", "more_body": True}, # 35 bytes (> 30 -> CROSSING)
        {"type": "http.request", "body": b"should_not_be_read", "more_body": True}, # 4th chunk
        {"type": "http.request", "body": b"should_not_be_read_either", "more_body": False}, # 5th chunk
    ]

    read_count = 0

    async def mock_receive():
        nonlocal read_count
        if read_count < len(chunks):
            chunk = chunks[read_count]
            read_count += 1
            return chunk
        return {"type": "http.request", "body": b"", "more_body": False}

    sent_messages = []

    async def mock_send(message):
        sent_messages.append(message)

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/direct-asgi",
        "headers": [],
    }

    await middleware(scope, mock_receive, mock_send)

    # Assert exactly 3 chunks were read (stopped at crossing chunk)
    assert read_count == 3
    assert endpoint_invoked is False

    # Assert response sent was 413
    assert sent_messages[0]["type"] == "http.response.start"
    assert sent_messages[0]["status"] == 413


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


def test_token_bucket_purge_stale_buckets():
    limiter = TokenBucketRateLimiter(
        rate_per_minute=60.0,
        burst=2,
        max_buckets=2,
        bucket_ttl_seconds=10.0,
    )
    # Populate bucket 1 at t=100
    limiter.allow("user1", cost=1.0, now=100.0)
    # Populate bucket 2 at t=100
    limiter.allow("user2", cost=1.0, now=100.0)
    assert len(limiter._buckets) == 2

    # At t=115, bucket 1 and 2 are older than TTL (10s)
    limiter.allow("user3", cost=1.0, now=115.0)
    # user1 and user2 should be purged
    assert "user1" not in limiter._buckets
    assert "user2" not in limiter._buckets
    assert "user3" in limiter._buckets


def test_rate_limiting_unauthenticated_token_rotation_shares_ip_bucket_and_throttles():
    """Rotating unverified Bearer tokens cannot bypass IP rate limit."""
    app = FastAPI()
    limiter = TokenBucketRateLimiter(rate_per_minute=60.0, burst=2)
    app.add_middleware(RateLimitMiddleware, limiter=limiter)

    @app.get("/api/data")
    def get_data():
        return {"data": "hello"}

    client = TestClient(app)

    # 1st request with token_A -> allowed
    r1 = client.get("/api/data", headers={"Authorization": "Bearer random_token_A"})
    assert r1.status_code == 200

    # 2nd request with token_B -> allowed (burst = 2 used for this IP)
    r2 = client.get("/api/data", headers={"Authorization": "Bearer random_token_B"})
    assert r2.status_code == 200

    # 3rd request with token_C -> REJECTED (429) because both share the same IP bucket
    r3 = client.get("/api/data", headers={"Authorization": "Bearer random_token_C"})
    assert r3.status_code == 429
    assert r3.json()["error"] == "Too Many Requests"
    assert "Retry-After" in r3.headers


def test_rate_limiting_authenticated_owner_throttles_per_owner():
    app = FastAPI()
    limiter = TokenBucketRateLimiter(rate_per_minute=60.0, burst=1)

    def extract_owner(request: Request) -> str:
        auth = request.headers.get("authorization", "")
        if auth == "Bearer alice_secret":
            return "owner:user_alice"
        elif auth == "Bearer bob_secret":
            return "owner:user_bob"
        return f"ip:{request.client.host if request.client else 'unknown'}"

    app.add_middleware(RateLimitMiddleware, limiter=limiter, key_func=extract_owner)

    @app.get("/api/profile")
    def profile():
        return {"status": "ok"}

    client = TestClient(app)

    # Alice request 1 -> allowed
    r_a1 = client.get("/api/profile", headers={"Authorization": "Bearer alice_secret"})
    assert r_a1.status_code == 200

    # Alice request 2 -> rejected (429)
    r_a2 = client.get("/api/profile", headers={"Authorization": "Bearer alice_secret"})
    assert r_a2.status_code == 429

    # Bob request 1 -> allowed (independent owner bucket)
    r_b1 = client.get("/api/profile", headers={"Authorization": "Bearer bob_secret"})
    assert r_b1.status_code == 200


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
