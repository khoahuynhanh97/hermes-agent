import os
import sys
import json
from pathlib import Path

if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

def sync_index():
    kb_dir = Path(r"D:\work\hermes-agent\knowledge_base")
    index_path = kb_dir / "unified_index.json"
    entries_dir = kb_dir / "entries"
    
    if not index_path.exists():
        print("unified_index.json not found!")
        return
        
    with open(index_path, "r", encoding="utf-8-sig") as f:
        index_data = json.load(f)
        
    existing_ids = {e["id"] for e in index_data.get("entries", [])}
    print(f"Current entries in index: {len(existing_ids)}")
    
    added_count = 0
    for file in os.listdir(entries_dir):
        if file.endswith(".json"):
            filepath = entries_dir / file
            try:
                with open(filepath, "r", encoding="utf-8-sig") as f:
                    data = json.load(f)
                entry_id = data.get("id")
                if not entry_id:
                    continue
                if entry_id not in existing_ids:
                    print(f"Adding entry: {entry_id} ({data.get('title')})")
                    entry_data = {
                        "id": data.get("id"),
                        "slug": data.get("slug"),
                        "source_url": data.get("source_url"),
                        "platform": data.get("platform"),
                        "category": data.get("category"),
                        "status": data.get("status", "pending"),
                        "learned_at": data.get("learned_at"),
                        "approved_at": data.get("approved_at"),
                        "approved_by": data.get("approved_by"),
                        "approval_mode": data.get("approval_mode"),
                        "approval_history": data.get("approval_history") or [],
                        "title": data.get("title"),
                        "hook_type": data.get("hook_type"),
                        "cta_style": data.get("cta_style"),
                        "voice_tone": data.get("voice_tone"),
                        "key_lessons": data.get("key_lessons") or [],
                        "detail_file": data.get("detail_file") or f"entries/{data.get('id')}.json",
                        "job_output_dir": data.get("job_output_dir"),
                        "source": data.get("source", "telegram_job"),
                        "owner_user_id": data.get("owner_user_id"),
                        "updated_at": data.get("updated_at") or data.get("learned_at"),
                    }
                    if "detail" in data:
                        detail = data["detail"]
                        entry_data.update({
                            "title": detail.get("title") or entry_data["title"],
                            "category": detail.get("category") or entry_data["category"],
                            "hook_type": detail.get("hook_type") or entry_data["hook_type"],
                            "cta_style": detail.get("cta_style") or entry_data["cta_style"],
                            "voice_tone": detail.get("voice_tone") or entry_data["voice_tone"],
                            "key_lessons": detail.get("key_lessons") or entry_data["key_lessons"],
                        })
                    index_data["entries"].append(entry_data)
                    existing_ids.add(entry_id)
                    added_count += 1
            except Exception as e:
                print(f"Error reading {file}: {e}")
                
    if added_count > 0:
        with open(index_path, "w", encoding="utf-8") as f:
            json.dump(index_data, f, ensure_ascii=False, indent=2)
        print(f"Successfully synced index! Added {added_count} entries.")
    else:
        print("No new entries to add.")

if __name__ == "__main__":
    sync_index()
