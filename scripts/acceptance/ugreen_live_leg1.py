"""UGREEN live run - Leg 1: canonical project + B1 resources + B2 idea + B3 brief.

Stops at Creative Brief HITL gate. Real product images copied from the G: drive
into the canonical workspace. NO paid generation yet.
"""
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(r"D:\work\hermes-agent")
sys.path.insert(0, str(ROOT))

# canonical data root
DATA_ROOT = Path(r"D:\work\hermes-agent-data")
DB_PATH = DATA_ROOT / "db" / "video_factory.sqlite"
WORKSPACE = DATA_ROOT / "workspaces" / "video-factory"
os.environ["HERMES_VIDEO_FACTORY_DB_PATH"] = str(DB_PATH)
os.environ["HERMES_VIDEO_FACTORY_WORKSPACE"] = str(WORKSPACE)

OWNER = "ninak"
PROJECT_ID = "ugreen-nexode-robot-uno-live"

# real product images (source: authorized product, G: drive)
SRC_DIR = Path(r"G:\My Drive\TIKTOK\sac-ugreen")
PRODUCT_IMAGES = [
    "vn-11134201-81ztc-mrffmjlnrabp6b.png",   # hero shot (primary)
    "vn-11134103-81ztc-mlftjsv9wa2o51.png",   # lifestyle/detail
    "vn-11134258-81ztc-mr05p0axubr996.png",   # box/product
]
PRIMARY = PRODUCT_IMAGES[0]

from hermes.adapters.sqlite.video_factory_repository import SQLiteVideoFactoryRepository
from hermes.application.video_factory_service import VideoFactoryService
from hermes.db import Database
from hermes.domain.video_factory import (
    AssetReference, CreativeBrief, RawIdea, ResourceIdentity, ResourcePack,
)

WORKSPACE.mkdir(parents=True, exist_ok=True)
(DB_PATH.parent).mkdir(parents=True, exist_ok=True)
prod_dir = WORKSPACE / "products"
prod_dir.mkdir(parents=True, exist_ok=True)
copied = {}
for name in PRODUCT_IMAGES:
    src = SRC_DIR / name
    if src.is_file():
        dst = prod_dir / name
        shutil.copy2(src, dst)
        copied[name] = dst
        print("copied:", name, dst.stat().st_size)
    else:
        print("MISSING source:", src)

service = VideoFactoryService(SQLiteVideoFactoryRepository(Database(DB_PATH)))

# idempotent create / reuse
project = service.repository.get_owned(PROJECT_ID, OWNER)
if project is None:
    project = service.create_project(OWNER, PROJECT_ID)
print("project:", project.id, "status:", project.status.value)

# B1 resource pack + lock (use real product image as reference, asset:// semantics)
refs = tuple(AssetReference(f"ugreen_img_{i}", f"asset://products/{name}", {"role": "primary" if name == PRIMARY else "detail"})
             for i, name in enumerate(PRODUCT_IMAGES))
pack = ResourcePack(
    id="pack_ugreen_live",
    owner_user_id=OWNER,
    product_references=refs,
    primary_product_asset_id=f"ugreen_img_{PRODUCT_IMAGES.index(PRIMARY)}",
    product_identity_description="UGREEN Nexode Robot UNO GaN charger (30W/65W), robot face design",
    context="clean desk, soft studio lighting, product-focused",
    visual_style="minimal, bright, 9:16 vertical",
)
project = service.save_resource_pack(OWNER, PROJECT_ID, pack)
project = service.lock_resource_pack(OWNER, PROJECT_ID, ResourceIdentity(
    description="UGREEN Nexode Robot UNO GaN charger with robot face, white/black body, USB-C",
    distinctive_features=("robot face LED display", "two USB-C ports", "foldable plug"),
))
print("resource pack locked:", bool(project.resource_pack.locked_at))

# B2 raw idea
project = service.save_raw_idea(OWNER, PROJECT_ID, RawIdea(
    text="Giới thiệu củ sạc GaN UGREEN Nexode Robot UNO: hero shot, dùng thật, close-up",
    required_elements=("charger visible", "clean desk", "soft light"),
    target_duration_seconds=12,
    platform="tiktok",
    aspect_ratio="9:16",
))

# B3 creative brief (no unsupported claims)
brief = CreativeBrief(
    objective="Visually present the UGREEN Nexode Robot UNO GaN charger",
    target_audience="tech buyers on TikTok",
    core_message="A compact GaN charger with a robot face",
    tone="clean, modern, energetic",
    pace="brisk",
    cta="",
    content_blocks=("hero", "usage", "close-up"),
    verified_selling_points=(),  # no claims
    restrictions=("no sales claims", "no wattage/speed promises unless evidenced", "no text overlays"),
    required_content=("charger clearly visible in every scene",),
    platform="tiktok",
    aspect_ratio="9:16",
    target_duration_seconds=12,
)
project = service.save_creative_brief(OWNER, PROJECT_ID, brief)
print("brief saved, approval:", project.brief_approval)
print("PROJECT_ID:", PROJECT_ID)
print("OWNER:", OWNER)
