import os
import json
import dotenv

dotenv.load_dotenv(override=True)

from hermes.application.core.knowledge_store import get_store

store = get_store()

target_ids = [
    "kb_a039616cec32",
    "kb_a145dccdb564",
    "kb_fda69222a0e6",
    "kb_1b58275338f6",
    "kb_ba444d96ba1f",
    "kb_d04f51ec26e4",
    "kb_d2cef7091e43"
]

print("--- DEEP INSPECTION OF 7 BROKEN ENTRIES ---")

for id_str in target_ids:
    entry = store.get_entry(id_str)
    if not entry:
        print(f"ID {id_str} not found!")
        continue
        
    detail = store.get_entry_detail(id_str)
    
    print(f"\nID: {entry.get('id')}")
    print(f"Title: {entry.get('title')}")
    print(f"URL: {entry.get('source_url')}")
    print(f"Category: {entry.get('category')} | Status: {entry.get('status')}")
    print(f"Detail File: {entry.get('detail_file')}")
    print(f"Job Output Dir: {entry.get('job_output_dir')}")
    
    # Check if local video/image file exists in source metadata
    evidence = detail.get("evidence") or []
    source_metadata = detail.get("source_metadata") or {}
    local_path = source_metadata.get("local_path") or ""
    
    print(f"Local Path in metadata: {local_path} -> Exists: {os.path.exists(local_path) if local_path else False}")
