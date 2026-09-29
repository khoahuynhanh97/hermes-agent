#!/usr/bin/env python3
"""Pre-existing working-tree preservation manifest generator."""

import hashlib
import json
import subprocess
from pathlib import Path

repo_root = Path(__file__).resolve().parents[3]
out_dir = repo_root / "reports" / "runtime-truth" / "gate-0-1"
out_dir.mkdir(parents=True, exist_ok=True)

res = subprocess.run(
    ["git", "status", "--porcelain", "--untracked-files=all"],
    capture_output=True,
    text=True,
    check=True,
    cwd=repo_root,
)
lines = res.stdout.splitlines()

manifest_items = []

for line in lines:
    if not line:
        continue
    status_code = line[:2]
    rel_path_str = line[3:].strip().strip('"')
    file_path = repo_root / rel_path_str

    # Ignore newly created audit output directory
    rel_norm = rel_path_str.replace("\\", "/")
    if rel_norm.startswith("reports/runtime-truth"):
        continue

    if not file_path.is_file():
        continue

    is_tracked = status_code != "??"
    status_label = "tracked_modified" if is_tracked else "untracked"

    content = file_path.read_bytes()
    size = len(content)
    digest = hashlib.sha256(content).hexdigest()

    manifest_items.append({
        "path": rel_norm,
        "status": status_label,
        "git_status_code": status_code,
        "size_bytes": size,
        "sha256": digest,
    })

manifest_items.sort(key=lambda x: x["path"])

out_file = out_dir / "preservation_manifest_start.json"
out_file.write_text(json.dumps({"item_count": len(manifest_items), "items": manifest_items}, indent=2), encoding="utf-8")
print(f"Preservation manifest start created with {len(manifest_items)} items:")
for item in manifest_items:
    print(f"  [{item['status']:16}] {item['path']:55} ({item['size_bytes']} bytes, sha256: {item['sha256'][:12]}..)")
