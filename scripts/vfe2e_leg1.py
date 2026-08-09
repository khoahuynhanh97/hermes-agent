"""VF-E2E Leg 1: B1-B3. Create project, lock resource pack, raw idea, save brief.

Stops before business approval (HITL). Idempotent: rerunning continues from
persisted state.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

E2E_ROOT = Path(r"C:\Users\ninak\AppData\Local\Temp\opencode\vfe2e")
E2E_ROOT.mkdir(parents=True, exist_ok=True)
DB_PATH = E2E_ROOT / "e2e.db"
WORKSPACE = E2E_ROOT / "workspace"
OWNER = "e2e_owner"
PROJECT_ID = "vfe2e_project"
PRODUCT_REF = Path(r"C:\Users\ninak\AppData\Local\Temp\opencode\vf-ws\dbg3.png")

os.environ["HERMES_VIDEO_FACTORY_WORKSPACE"] = str(WORKSPACE)

# ensure product reference inside workspace (workspace containment for resources)
WORKSPACE.mkdir(parents=True, exist_ok=True)
import shutil
ref_in_ws = WORKSPACE / "product_ref.png"
if PRODUCT_REF.is_file():
    shutil.copy2(PRODUCT_REF, ref_in_ws)

from hermes.adapters.sqlite.video_factory_repository import SQLiteVideoFactoryRepository
from hermes.application.video_factory_service import VideoFactoryService
from hermes.db import Database
from hermes.domain.video_factory import (
    AssetReference, CreativeBrief, RawIdea, ResourceIdentity, ResourcePack,
)

service = VideoFactoryService(SQLiteVideoFactoryRepository(Database(DB_PATH)))

project = service.get_project(OWNER, PROJECT_ID) if service.repository.get_owned(PROJECT_ID, OWNER) else service.create_project(OWNER, PROJECT_ID)
print("project:", project.id, "status:", project.status.value)

pack = ResourcePack(
    id="pack_e2e",
    owner_user_id=OWNER,
    product_references=(AssetReference("asset_prod_1", "asset://product_ref.png", {"role": "primary"}),),
    primary_product_asset_id="asset_prod_1",
    product_identity_description="A blue water bottle",
    context="clean table, soft studio lighting",
    visual_style="product-focused, minimal, 9:16",
)
project = service.save_resource_pack(OWNER, PROJECT_ID, pack)
project = service.lock_resource_pack(
    OWNER, PROJECT_ID,
    ResourceIdentity(
        description="A single blue water bottle, clean minimal design",
        color="blue",
        distinctive_features=("smooth minimal body", "simple cap"),
    ),
)
print("resource pack locked:", bool(project.resource_pack.locked_at))

idea = RawIdea(
    text="Show the blue water bottle on a clean table",
    required_elements=("bottle visible", "clean table", "soft light"),
    required_cta="",
    target_duration_seconds=4,
    platform="tiktok",
    aspect_ratio="9:16",
)
project = service.save_raw_idea(OWNER, PROJECT_ID, idea)
print("raw idea saved, idea_version:", project.idea_version)

brief = CreativeBrief(
    objective="Visually present the blue water bottle on a clean table",
    target_audience="general viewers",
    core_message="A blue water bottle on a clean table",
    tone="clean, calm",
    pace="slow",
    cta="",
    content_blocks=("establish bottle",),
    verified_selling_points=(),  # no sales claims
    restrictions=("no sales claims", "no text overlays"),
    required_content=("bottle clearly visible",),
    platform="tiktok",
    aspect_ratio="9:16",
    target_duration_seconds=4,
)
project = service.save_creative_brief(OWNER, PROJECT_ID, brief)
print("brief saved, brief_approval:", project.brief_approval, "status:", project.status.value)
print("PROJECT_ID:", PROJECT_ID)
print("OWNER:", OWNER)
