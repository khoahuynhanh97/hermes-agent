import os
import json
import dotenv

dotenv.load_dotenv(override=True)

from hermes.application.core.knowledge_store import get_store

store = get_store()
entries = store.list_entries()

print(f"Total entries scanned: {len(entries)}")

error_list = []

for entry in entries:
    entry_id = entry.get("id")
    title = entry.get("title", "")
    category = entry.get("category", "")
    lessons = entry.get("key_lessons", [])
    status = entry.get("status", "")
    source_url = entry.get("source_url", "")
    
    detail = store.get_entry_detail(entry_id)
    
    reasons = []
    if category == "error":
        reasons.append("Category is 'error'")
    if entry.get("needs_reanalysis") or detail.get("needs_reanalysis"):
        reasons.append("Flagged needs_reanalysis")
    if not lessons:
        reasons.append("Empty key_lessons")
    if "error" in title.lower() or "lỗi" in title.lower() or "failed" in title.lower():
        reasons.append("Title contains error keyword")
    if detail.get("validation_error"):
        reasons.append(f"Validation error: {detail.get('validation_error')}")
    if not detail:
        reasons.append("Missing detail JSON payload")
        
    if reasons:
        error_list.append({
            "id": entry_id,
            "title": title,
            "category": category,
            "status": status,
            "source_url": source_url,
            "reasons": reasons,
            "detail": detail
        })

print(f"\n--- FOUND {len(error_list)} PROBLEMATIC / ERROR ENTRIES ---")
for item in error_list:
    print(f"\nID: {item['id']}")
    print(f"Title: {item['title']}")
    print(f"Category: {item['category']} | Status: {item['status']}")
    print(f"URL: {item['source_url']}")
    print(f"Reasons: {', '.join(item['reasons'])}")

# Save diagnostic output
with open(r"d:\work\hermes-agent\diagnose_errors.json", "w", encoding="utf-8") as f:
    json.dump(error_list, f, ensure_ascii=False, indent=2)

print(f"\nDiagnostic saved to d:\\work\\hermes-agent\\diagnose_errors.json")
