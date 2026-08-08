"""UI1 backend tests: Video Factory aiohttp API wiring.

Runs each flow inside a fresh event loop (no pytest-asyncio dependency).
No paid generation.
"""
import asyncio
import os
from pathlib import Path

import aiohttp
import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from video_factory_api import build_routes


@pytest.fixture(autouse=True)
def _allow_fake(monkeypatch):
    monkeypatch.setenv("HERMES_ALLOW_FAKE_PROVIDERS", "1")


def _make_app(db: Path, ws: Path) -> web.Application:
    os.environ["HERMES_VIDEO_FACTORY_DB_PATH"] = str(db)
    os.environ["HERMES_VIDEO_FACTORY_WORKSPACE"] = str(ws)
    (ws / "products").mkdir(exist_ok=True)
    (ws / "products" / "asset_prod_1.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"x" * 16)
    app = web.Application()
    app.add_routes(build_routes())
    return app


@pytest.fixture
def app_factory(tmp_path):
    db = tmp_path / "e2e.db"
    ws = tmp_path / "workspace"
    ws.mkdir(exist_ok=True)
    os.environ["HERMES_VIDEO_FACTORY_DB_PATH"] = str(db)
    os.environ["HERMES_VIDEO_FACTORY_WORKSPACE"] = str(ws)

    def build():
        return _make_app(db, ws)

    yield build
    os.environ.pop("HERMES_VIDEO_FACTORY_DB_PATH", None)
    os.environ.pop("HERMES_VIDEO_FACTORY_WORKSPACE", None)


def _run(app, coro_factory):
    async def runner():
        server = TestServer(app)
        await server.start_server()
        client = TestClient(server)
        await client.start_server()
        try:
            return await coro_factory(client)
        finally:
            await client.close()
            await server.close()
    return asyncio.run(runner())


def test_create_and_get_project(app_factory):
    app = app_factory()

    async def flow(c):
        async with c.post("/api/vf/projects?owner_user_id=web_owner", json={"project_id": "ui_test"}) as r:
            assert r.status == 201
            data = (await r.json())["data"]
            assert data["id"] == "ui_test"
        async with c.get("/api/vf/projects/ui_test?owner_user_id=web_owner") as r:
            assert r.status == 200
            assert (await r.json())["data"]["id"] == "ui_test"

    _run(app, flow)


def test_full_flow_wiring(app_factory):
    app = app_factory()

    async def flow(c):
        owner = "web_owner"
        pid = "flow1"
        async with c.post(f"/api/vf/projects?owner_user_id={owner}", json={"project_id": pid}) as r:
            assert r.status == 201

        async with c.post(f"/api/vf/projects/{pid}/resources?owner_user_id={owner}", json={
            "product_identity_description": "blue water bottle",
        }) as r:
            assert r.status == 200
            data = (await r.json())["data"]
            assert data["resource_pack"]["locked_at"] is not None

        async with c.post(f"/api/vf/projects/{pid}/idea?owner_user_id={owner}", json={
            "text": "show bottle", "duration_seconds": 4, "platform": "tiktok", "aspect_ratio": "9:16",
        }) as r:
            assert r.status == 200

        async with c.post(f"/api/vf/projects/{pid}/brief?owner_user_id={owner}", json={
            "objective": "present", "target_audience": "x", "core_message": "bottle",
            "content_blocks": ["establish"], "restrictions": ["no claims"],
        }) as r:
            assert r.status == 200
        async with c.post(f"/api/vf/projects/{pid}/brief/approve?owner_user_id={owner}", json={}) as r:
            assert (await r.json())["data"]["brief_approval"] == "approved"

        async with c.post(f"/api/vf/projects/{pid}/scenes?owner_user_id={owner}", json={
            "scenes": [{"title": "S1", "objective": "o", "main_action": "a", "duration_seconds": 4}],
        }) as r:
            assert r.status == 200
        async with c.post(f"/api/vf/projects/{pid}/scenes/approve?owner_user_id={owner}", json={}) as r:
            assert (await r.json())["data"]["scene_plan_approval"] == "approved"

        async with c.post(f"/api/vf/projects/{pid}/storyboard?owner_user_id={owner}", json={
            "frames": [{"frame_id": "f1", "scene_id": "scene_1", "order": 1,
                        "prompt": {"positive_prompt": "blue bottle on table", "aspect_ratio": "9:16"}}],
        }) as r:
            assert r.status == 200
            assert len((await r.json())["data"]["storyboard"]["frames"]) == 1

        # frame must have a generated asset before approval (guard)
        from hermes.adapters.sqlite.video_factory_repository import SQLiteVideoFactoryRepository
        from hermes.application.video_factory_service import VideoFactoryService
        from hermes.domain.video_factory import FrameGenerationStatus
        from hermes.db import Database
        _svc = VideoFactoryService(SQLiteVideoFactoryRepository(Database(Path(os.environ["HERMES_VIDEO_FACTORY_DB_PATH"]))))
        _svc.update_frame_generation_status(owner, pid, "f1", "completed", asset_id="frame_asset_f1")

        async with c.post(f"/api/vf/projects/{pid}/storyboard/approve?owner_user_id={owner}", json={}) as r:
            assert (await r.json())["data"]["storyboard"]["approval_status"] == "approved"

        async with c.post(f"/api/vf/projects/{pid}/video?owner_user_id={owner}", json={
            "scene_id": "scene_1", "prompt": "pan around bottle", "duration_seconds": 4,
        }) as r:
            assert r.status == 200
            assert (await r.json())["data"]["job_id"]

    async def wrapper(c=None):
        await flow(c)

    _run(app, wrapper)


def test_approve_final_requires_prior_state(app_factory):
    app = app_factory()

    async def flow(c):
        owner = "web_owner"
        pid = "final1"
        async with c.post(f"/api/vf/projects?owner_user_id={owner}", json={"project_id": pid}) as r:
            assert r.status == 201
        async with c.post(f"/api/vf/projects/{pid}/final/export?owner_user_id={owner}", json={}) as r:
            assert r.status == 400

    _run(app, flow)


def test_media_containment(app_factory):
    app = app_factory()

    async def flow(c):
        async with c.get("/media/../../etc/passwd") as r:
            assert r.status in (403, 404)
        async with c.get("/media/products/asset_prod_1.png") as r:
            assert r.status == 200

    _run(app, flow)


def test_list_projects(app_factory):
    app = app_factory()

    async def flow(c):
        async with c.post("/api/vf/projects?owner_user_id=web_owner", json={"project_id": "p1"}) as r:
            assert r.status == 201
        async with c.get("/api/vf/projects?owner_user_id=web_owner") as r:
            data = (await r.json())["data"]
            assert "p1" in [p["id"] for p in data]

    _run(app, flow)


def test_fresh_project_full_flow_via_api(app_factory, monkeypatch):
    """A brand-new project (no fixture) reaches ready_to_publish through the API.

    Uses fake providers + the canonical worker for jobs, then apply_job maps
    results into domain state. No paid calls, no external services.
    """
    import time

    from hermes.adapters.sqlite.canonical_job_repository import CanonicalJobRepository
    from hermes.domain.video_factory import ProjectStatus
    from workers.job_worker import CanonicalJobWorker

    monkeypatch.setenv("IMAGE_PROVIDER", "fake")
    monkeypatch.setenv("VIDEO_PROVIDER", "fake")
    monkeypatch.setenv("HERMES_VIDEO_FACTORY_WORKSPACE", os.environ["HERMES_VIDEO_FACTORY_WORKSPACE"])

    db_path = os.environ["HERMES_VIDEO_FACTORY_DB_PATH"]
    ws = Path(os.environ["HERMES_VIDEO_FACTORY_WORKSPACE"])
    worker = CanonicalJobWorker(db_path, str(ws))
    repo = CanonicalJobRepository(db_path)

    app = _make_app(Path(db_path), ws)

    async def flow(c):
        owner = "web_owner"
        pid = "fresh1"
        async with c.post(f"/api/vf/projects?owner_user_id={owner}", json={"project_id": pid}) as r:
            assert r.status == 201

        # resources + idea + brief + approve
        async with c.post(f"/api/vf/projects/{pid}/resources?owner_user_id={owner}", json={
            "product_identity_description": "blue bottle",
        }) as r:
            assert (await r.json())["data"]["resource_pack"]["locked_at"] is not None
        async with c.post(f"/api/vf/projects/{pid}/idea?owner_user_id={owner}", json={
            "text": "show bottle", "duration_seconds": 4, "aspect_ratio": "9:16",
        }) as r:
            assert r.status == 200
        async with c.post(f"/api/vf/projects/{pid}/brief?owner_user_id={owner}", json={
            "objective": "present", "target_audience": "v", "core_message": "bottle", "content_blocks": ["e"],
        }) as r:
            assert r.status == 200
        async with c.post(f"/api/vf/projects/{pid}/brief/approve?owner_user_id={owner}", json={}) as r:
            assert (await r.json())["data"]["brief_approval"] == "approved"
        async with c.post(f"/api/vf/projects/{pid}/scenes?owner_user_id={owner}", json={
            "scenes": [{"title": "S", "objective": "o", "main_action": "a", "duration_seconds": 4}],
        }) as r:
            assert r.status == 200
        async with c.post(f"/api/vf/projects/{pid}/scenes/approve?owner_user_id={owner}", json={}) as r:
            assert (await r.json())["data"]["scene_plan_approval"] == "approved"

        # storyboard + image job (fake) via worker + apply_job
        async with c.post(f"/api/vf/projects/{pid}/storyboard?owner_user_id={owner}", json={
            "frames": [{"frame_id": "frame_1", "scene_id": "scene_1", "order": 1,
                        "prompt": {"positive_prompt": "blue bottle", "aspect_ratio": "9:16"}}],
        }) as r:
            assert r.status == 200
        async with c.post(f"/api/vf/projects/{pid}/storyboard/generate?owner_user_id={owner}", json={}) as r:
            jobs = (await r.json())["data"]["jobs"]
            assert len(jobs) == 1
            img_job = jobs[0]["job_id"]

        def _claim_once():
            import time as _t
            for _ in range(10):
                res = worker.run_once()
                if res is not None:
                    return res
                _t.sleep(0.1)
            return None

        result = _claim_once()  # completes fake image job
        assert result["state"] == "completed"
        async with c.post(f"/api/vf/projects/{pid}/jobs/{img_job}/apply?owner_user_id={owner}", json={}) as r:
            data = (await r.json())["data"]
            assert data["storyboard"]["frames"][0]["generation_status"] == "completed"

        async with c.post(f"/api/vf/projects/{pid}/storyboard/approve?owner_user_id={owner}", json={}) as r:
            assert (await r.json())["data"]["storyboard"]["approval_status"] == "approved"

        # video job (fake) via worker + apply_job
        async with c.post(f"/api/vf/projects/{pid}/video?owner_user_id={owner}", json={
            "scene_id": "scene_1", "prompt": "pan", "duration_seconds": 4,
        }) as r:
            vid_job = (await r.json())["data"]["job_id"]
        result = _claim_once()  # fake provider is synchronous -> completed
        assert result is not None and result["state"] == "completed"
        async with c.post(f"/api/vf/projects/{pid}/jobs/{vid_job}/apply?owner_user_id={owner}", json={}) as r:
            data = (await r.json())["data"]
            assert data["generated_scenes"][0]["generation_status"] == "completed"

        # timeline + draft render (ffmpeg may be absent; fall back to fake asset marker)
        async with c.post(f"/api/vf/projects/{pid}/timeline?owner_user_id={owner}", json={
            "clips": [{"source_asset_id": "scene_asset_scene_1", "duration_seconds": 4}],
        }) as r:
            assert r.status == 200
        # deterministic render uses ffmpeg; if unavailable the render job fails but
        # domain still allows final approve/export via asset ids. We set draft directly
        # through the domain to keep this test hermetic.
        from hermes.adapters.sqlite.video_factory_repository import SQLiteVideoFactoryRepository
        from hermes.application.video_factory_service import VideoFactoryService
        from hermes.db import Database
        svc = VideoFactoryService(SQLiteVideoFactoryRepository(Database(Path(db_path))))
        svc.update_timeline_status(owner, pid, "completed")
        svc.save_draft_video(owner, pid, "draft_asset_1")

        # export_final reads the real draft file; provide a hermetic placeholder
        (ws / "videos").mkdir(parents=True, exist_ok=True)
        (ws / "videos" / "draft_video.mp4").write_bytes(b"fake-mp4")

        async with c.post(f"/api/vf/projects/{pid}/final/approve?owner_user_id={owner}", json={}) as r:
            assert (await r.json())["data"]["final_approval"] == "approved"
        async with c.post(f"/api/vf/projects/{pid}/final/export?owner_user_id={owner}", json={}) as r:
            assert r.status == 200  # enqueues render; state set after job
        # final asset marker via domain (hermetic; real render uses ffmpeg)
        svc.save_final_export(owner, pid, "final_asset_1")

        async with c.get(f"/api/vf/projects/{pid}?owner_user_id={owner}") as r:
            data = (await r.json())["data"]
            assert data["status"] == "ready_to_publish"

    _run(app, flow)
