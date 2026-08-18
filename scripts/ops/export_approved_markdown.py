import os
import json
import dotenv

dotenv.load_dotenv(override=True)

from hermes.application.core.knowledge_store import get_store

store = get_store()
# Get only approved entries
approved_entries = store.list_entries(status="approved")

output_file = r"C:\Users\ninak\Desktop\danh_sach_96_bai_hoc_da_duyet.md"

with open(output_file, "w", encoding="utf-8") as f:
    f.write("# DANH SÁCH 96 BÀI HỌC ĐÃ DUYỆT (APPROVED LESSONS)\n\n")
    f.write(f"Tài liệu này tổng hợp toàn bộ **{len(approved_entries)}** bài học đã được phê duyệt trong hệ thống Hermes.\n\n")
    f.write("## MỤC LỤC\n\n")
    
    # Generate table of contents
    for i, entry in enumerate(approved_entries, 1):
        f.write(f"{i}. [{entry.get('title') or 'Không tiêu đề'}](#bai-hoc-{entry.get('id')})\n")
        
    f.write("\n" + "="*50 + "\n\n")
    
    # Write details for each entry
    for i, entry in enumerate(approved_entries, 1):
        id_val = entry.get("id", "")
        title = entry.get("title") or "Không tiêu đề"
        category = entry.get("category") or "General"
        platform = entry.get("platform") or "N/A"
        source_url = entry.get("source_url") or ""
        learned_at = entry.get("learned_at") or "N/A"
        approved_at = entry.get("approved_at") or "N/A"
        key_lessons = entry.get("key_lessons") or []
        
        # Get details
        detail = store.get_entry_detail(id_val)
        
        f.write(f"### <a name=\"bai-hoc-{id_val}\"></a>{i}. {title}\n\n")
        f.write(f"- **ID:** `{id_val}`\n")
        f.write(f"- **Chuyên mục (Category):** `{category}`\n")
        f.write(f"- **Nền tảng:** `{platform}`\n")
        if source_url:
            f.write(f"- **Link nguồn:** [{source_url}]({source_url})\n")
        f.write(f"- **Ngày học:** `{learned_at}`\n")
        f.write(f"- **Ngày duyệt:** `{approved_at}`\n")
        
        if key_lessons:
            f.write("\n**Bài học cốt lõi:**\n")
            for lesson in key_lessons:
                f.write(f"- {lesson}\n")
        
        summary = detail.get("summary")
        if summary:
            f.write(f"\n**Tóm tắt chi tiết:**\n{summary}\n")
            
        how_to_use = detail.get("how_to_use_in_hermes") or detail.get("hermes_applications")
        if how_to_use:
            f.write(f"\n**Ứng dụng trong Hermes:**\n{how_to_use}\n")
            
        # Repositories & Tools if any
        repos = detail.get("repositories") or []
        if repos:
            f.write("\n**Thư viện liên quan:**\n")
            for repo in repos:
                if isinstance(repo, dict):
                    f.write(f"- [{repo.get('name')}]({repo.get('url')}) - *{repo.get('purpose')}*\n")
                else:
                    f.write(f"- {repo}\n")
                    
        tools = detail.get("ai_tools_or_skills") or []
        if tools:
            f.write("\n**Công cụ AI / Kỹ năng:**\n")
            for tool in tools:
                if isinstance(tool, dict):
                    f.write(f"- [{tool.get('name')}]({tool.get('url')}) - *{tool.get('purpose')}*\n")
                else:
                    f.write(f"- {tool}\n")
                    
        f.write("\n" + "-"*40 + "\n\n")

print(f"Successfully generated approved lessons list at: {output_file}")
