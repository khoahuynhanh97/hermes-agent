import os
import json
import dotenv

# Load dotenv to get correct database configurations
dotenv.load_dotenv(override=True)

from hermes.application.core.knowledge_store import get_store

# Get the configured store (which is SQLite based on .env)
store = get_store()
entries = store.list_entries()

# Export all 74 entries to Desktop
output_path = r"C:\Users\ninak\Desktop\knowledge_export_all.json"
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(entries, f, ensure_ascii=False, indent=2)

print(f"Successfully exported {len(entries)} entries from SQLite to {output_path}")

# Filter entries related to 'structure' or 'cấu trúc'
keywords = ["structure", "cấu trúc", "khung", "sườn", "bố cục", "dàn ý"]
matches = []

for entry in entries:
    title = (entry.get("title") or "").lower()
    category = (entry.get("category") or "").lower()
    lessons = " ".join(entry.get("key_lessons") or []).lower()
    
    # Also get details if available
    detail = store.get_entry_detail(entry["id"])
    detail_str = json.dumps(detail, ensure_ascii=False).lower()
    
    match_found = False
    matched_keyword = ""
    for kw in keywords:
        if kw in title or kw in category or kw in lessons or kw in detail_str:
            match_found = True
            matched_keyword = kw
            break
            
    if match_found:
        matches.append({
            "id": entry.get("id"),
            "title": entry.get("title"),
            "category": entry.get("category"),
            "status": entry.get("status"),
            "matched_keyword": matched_keyword,
            "key_lessons": entry.get("key_lessons")
        })

print("\n--- MATCHING ENTRIES ---")
print(json.dumps(matches, ensure_ascii=False, indent=2))
