import pytest

from hermes.adapters.sqlite.video_factory_repository import SQLiteVideoFactoryRepository
from hermes.application.video_factory_service import VideoFactoryService
from hermes.db import Database
from hermes.domain.video_factory import (
    AssetReference, CreativeBrief, RawIdea, ResourceIdentity, ResourcePack, Scene, ScenePlan,
)


@pytest.fixture
def service(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "product-a.png").write_bytes(b"image")
    monkeypatch.setenv("HERMES_VIDEO_FACTORY_WORKSPACE", str(workspace))
    return VideoFactoryService(SQLiteVideoFactoryRepository(Database(tmp_path / "f1.sqlite")))


def _pack(owner="owner-a"):
    return ResourcePack("rp-1", owner, (AssetReference("a", "product-a.png"),), "a", "black desk lamp")


def _brief():
    return CreativeBrief("demonstrate", "home workers", "easy light", "direct", "fast", "buy",
                         ("hook", "demo", "cta"))


def test_f1_lifecycle_reaches_ready_for_storyboard(service):
    project = service.create_project("owner-a", "project-1")
    service.save_resource_pack("owner-a", project.id, _pack())
    service.lock_resource_pack("owner-a", project.id, ResourceIdentity("black desk lamp", color="black"))
    service.save_raw_idea("owner-a", project.id, RawIdea("review the lamp", ("desk",), "buy"))
    service.save_creative_brief("owner-a", project.id, _brief())
    service.approve_creative_brief("owner-a", project.id)
    plan = service.save_scene_plan("owner-a", project.id,
                                   ScenePlan((Scene("s1", 1, "Hook", "hook", "show", "place", 3),)))
    assert plan.status.value == "scene_plan_ready"
    final = service.approve_scene_plan("owner-a", project.id)
    assert final.status.value == "ready_for_storyboard"


def test_owner_isolation_and_locked_identity(service):
    project = service.create_project("owner-a", "project-2")
    with pytest.raises(ValueError, match="PROJECT_NOT_FOUND"):
        service.get_project("owner-b", project.id)
    service.save_resource_pack("owner-a", project.id, _pack())
    service.lock_resource_pack("owner-a", project.id, ResourceIdentity("lamp"))
    with pytest.raises(ValueError, match="RESOURCE_IDENTITY_LOCKED"):
        service.save_resource_pack("owner-a", project.id, ResourcePack("rp-2", "owner-a",
            (AssetReference("b", "product-a.png"),), "b", "changed identity"))


def test_local_asset_must_stay_in_workspace(service, tmp_path):
    project = service.create_project("owner-a", "project-3")
    outside = tmp_path / "outside.png"
    outside.write_bytes(b"image")
    with pytest.raises(ValueError, match="UNAUTHORIZED_PATH"):
        service.save_resource_pack("owner-a", project.id,
                                  ResourcePack("rp", "owner-a", (AssetReference("a", str(outside)),), "a", "lamp"))
