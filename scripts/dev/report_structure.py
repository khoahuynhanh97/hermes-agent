import os
import json
import dotenv

dotenv.load_dotenv(override=True)

from hermes.application.core.knowledge_store import get_store

store = get_store()
entries = store.list_entries()

keywords = ["structure", "cấu trúc", "khung", "sườn", "bố cục", "dàn ý"]
matches = []

for entry in entries:
    title = entry.get("title") or ""
    category = entry.get("category") or ""
    lessons = entry.get("key_lessons") or []
    lessons_str = " ".join(lessons)
    
    detail = store.get_entry_detail(entry["id"])
    detail_str = json.dumps(detail, ensure_ascii=False)
    
    matched_kws = [kw for kw in keywords if (
        kw in title.lower() or 
        kw in category.lower() or 
        kw in lessons_str.lower() or 
        kw in detail_str.lower()
    )]
    
    if matched_kws:
        matches.append({
            "entry": entry,
            "detail": detail,
            "matched_keywords": matched_kws
        })

# Write a beautiful markdown report to desktop
output_file = r"C:\Users\ninak\Desktop\kienthuc_cautruc.md"

with open(output_file, "w", encoding="utf-8") as f:
    f.write("# DANH SÁCH KIẾN THỨC LIÊN QUAN ĐẾN CẤU TRÚC / STRUCTURE\n\n")
    f.write(f"Tìm thấy **{len(matches)}** bài học trên tổng số **{len(entries)}** bài học.\n\n")
    
    for i, match in enumerate(matches, 1):
        e = match["entry"]
        d = match["detail"]
        kws = ", ".join(match["matched_keywords"])
        
        f.write(f"## {i}. {e.get('title')}\n")
        f.write(f"- **ID:** `{e.get('id')}`\n")
        f.write(f"- **Chuyên mục (Category):** {e.get('category')}\n")
        f.write(f"- **Trạng thái:** `{e.get('status')}`\n")
        f.write(f"- **Từ khóa khớp:** `{kws}`\n")
        
        if e.get("source_url"):
            f.write(f"- **Nguồn:** [{e.get('platform') or 'Link'}]({e.get('source_url')})\n")
            
        f.write("\n### Bài học cốt lõi:\n")
        for lesson in e.get("key_lessons", []):
            f.write(f"- {lesson}\n")
            
        # Add summary or details if available
        summary = d.get("summary")
        if summary:
            f.write(f"\n### Tóm tắt chi tiết:\n{summary}\n")
            
        how_to_use = d.get("how_to_use_in_hermes") or d.get("hermes_applications")
        if how_to_use:
            f.write(f"\n### Ứng dụng trong Hermes:\n{how_to_use}\n")
            
        f.write("\n" + "-"*40 + "\n\n")

print(f"Successfully generated markdown report at: {output_file}")
