"""VF-E2E path migration: %TEMP% -> D:\\work\\hermes-agent-data\\acceptance\\vf-e2e.

Copies existing DB + workspace (preserves B1-B4 state incl. approved brief),
keeps asset:// containment semantics, verifies state after copy.
"""
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

OLD_ROOT = Path(r"C:\Users\ninak\AppData\Local\Temp\opencode\vfe2e")
NEW_ROOT = Path(r"D:\work\hermes-agent-data\acceptance\vf-e2e")
OWNER = "e2e_owner"
PROJECT_ID = "vfe2e_project"

NEW_ROOT.mkdir(parents=True, exist_ok=True)
NEW_WORKSPACE = NEW_ROOT / "workspace"
NEW_WORKSPACE.mkdir(parents=True, exist_ok=True)

# Copy DB if not already there
new_db = NEW_ROOT / "e2e.db"
if not new_db.exists() and (OLD_ROOT / "e2e.db").exists():
    shutil.copy2(OLD_ROOT / "e2e.db", new_db)
    print("DB copied ->", new_db)

# Copy workspace assets (product reference)
old_ws = OLD_ROOT / "workspace"
for f in old_ws.glob("*"):
    if f.is_file():
        shutil.copy2(f, NEW_WORKSPACE / f.name)
print("workspace files:", [f.name for f in NEW_WORKSPACE.glob('*') if f.is_file()])

os.environ["HERMES_VIDEO_FACTORY_WORKSPACE"] = str(NEW_WORKSPACE)

from hermes.adapters.sqlite.video_factory_repository import SQLiteVideoFactoryRepository
from hermes.application.video_factory_service import VideoFactoryService
from hermes.db import Database

service = VideoFactoryService(SQLiteVideoFactoryRepository(Database(new_db)))
project = service.get_project(OWNER, PROJECT_ID)
print("status:", project.status.value)
print("brief_approval:", project.brief_approval)
print("resource locked:", bool(project.resource_pack.locked_at) if project.resource_pack else False)
print("idea_version:", project.idea_version, "brief_version:", project.brief_version)
print("NEW_DB:", new_db)
print("NEW_WORKSPACE:", NEW_WORKSPACE)
