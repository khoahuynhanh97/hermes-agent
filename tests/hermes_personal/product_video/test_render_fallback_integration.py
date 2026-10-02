"""Verify render_handler wires the multi-provider fallback chain."""
from __future__ import annotations

import sqlite3
import sys
import types
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from hermes_personal.product_video.job_contracts import JobContext, JobFailed, JobSucceeded, TerminalJobError
from hermes_personal.product_video.handlers.render_handler import render_job


class _FakeRepo:
    """Minimal workflow repository double."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def get_workflow(self, workflow_id: str) -> tuple[dict[str, Any], int]:
        return (
            {
                "owner_user_id": "owner-1",
                "state": "rendering",
                "project_id": "proj-1",
                "render_dispatch_status": None,
            },
            1,
        )

    def commit_workflow(self, **_kwargs: Any) -> None:
        return None


@pytest.fixture
def conn() -> sqlite3.Connection:
    from hermes_personal.storage.sqlite import connect
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        connection = connect(Path(tmpdir) / "fallback.db")
        yield connection
        connection.close()


def _make_handler(video_client: Any, repo: _FakeRepo) -> Any:
    """Build a handler double exposing only what render_job needs."""
    handler = types.SimpleNamespace()
    handler.video_client = video_client
    handler.workflow_repository = repo
    handler.provider_mode = "fake"
    handler._idempotency_cache = {}
    handler._validate_state_and_version = lambda *a, **k: None
    return handler


def test_render_handler_falls_back_when_primary_provider_fails(
    conn: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Primary provider failure must be caught and the next provider dispatched."""
    monkeypatch.setattr(
        "hermes_personal.product_video.handlers.render_handler.reserve_budget",
        lambda *_a, **_k: types.SimpleNamespace(reservation_id="res-1", state="reserved"),
    )
    monkeypatch.setattr(
        "hermes_personal.product_video.handlers.render_handler.commit_budget",
        lambda _alloc: None,
    )
    monkeypatch.setattr(
        "hermes_personal.product_video.handlers.render_handler.release_budget",
        lambda _alloc: None,
    )

    seen_providers: list[str] = []

    class FlakyClient:
        def render_video(self, _story: Any, render_params: dict | None = None, **_kwargs: Any) -> dict:
            provider = (render_params or {}).get("provider_kind")
            seen_providers.append(provider)
            if provider == "google_flow":
                raise TerminalJobError("provider timeout", code="PROVIDER_TIMEOUT")
            return {"status": "completed", "provider": provider}

    handler = _make_handler(FlakyClient(), _FakeRepo(conn))
    result = render_job(
        handler,
        JobContext(workflow_id="wf-fallback", job_id="job-1", idempotency_key="idem-1"),
        {"scene_id": "scene-1"},
    )

    assert isinstance(result, JobSucceeded)
    assert seen_providers[0] == "google_flow"
    assert seen_providers[1] == "kling"
    assert result.artifact_ref["provider"] == "kling"


def test_render_handler_fails_closed_when_chain_exhausted(
    conn: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every provider failing must surface a terminal failure, not a silent success."""
    monkeypatch.setattr(
        "hermes_personal.product_video.handlers.render_handler.reserve_budget",
        lambda *_a, **_k: types.SimpleNamespace(reservation_id="res-2", state="reserved"),
    )
    monkeypatch.setattr(
        "hermes_personal.product_video.handlers.render_handler.commit_budget",
        lambda _alloc: None,
    )
    monkeypatch.setattr(
        "hermes_personal.product_video.handlers.render_handler.release_budget",
        lambda _alloc: None,
    )

    attempts: list[str] = []

    class DeadClient:
        def render_video(self, _story: Any, render_params: dict | None = None, **_kwargs: Any) -> dict:
            provider = (render_params or {}).get("provider_kind")
            attempts.append(provider)
            raise TerminalJobError(f"{provider} down", code="PROVIDER_UNAVAILABLE")

    handler = _make_handler(DeadClient(), _FakeRepo(conn))
    result = render_job(
        handler,
        JobContext(workflow_id="wf-exhausted", job_id="job-2", idempotency_key="idem-2"),
        {"scene_id": "scene-1"},
    )

    assert isinstance(result, JobFailed)
    assert result.retryable is False
    assert result.code == "ALL_PROVIDERS_EXHAUSTED"
    assert len(attempts) == 4
