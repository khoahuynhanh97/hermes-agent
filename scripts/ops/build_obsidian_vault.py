import os
import re
import json
import shutil
import dotenv
from pathlib import Path

dotenv.load_dotenv(override=True)

from hermes.application.core.knowledge_store import get_store

store = get_store()
entries = store.list_entries()

print(f"Loaded {len(entries)} knowledge entries for Obsidian graph generation.")

# Output directories (stored directly inside hermes-agent workspace)
vault_dir = Path(r"D:\work\hermes-agent\obsidian_vault")
kb_vault_dir = Path(r"D:\work\hermes-agent\knowledge_base\obsidian_vault")

vault_dir.mkdir(parents=True, exist_ok=True)
kb_vault_dir.mkdir(parents=True, exist_ok=True)

# Helper to sanitize filename for Obsidian
def sanitize_filename(title: str) -> str:
    # Remove invalid filename characters
    clean = re.sub(r'[\\/*?:"<>|]', '', title)
    clean = re.sub(r'\s+', ' ', clean).strip()
    return clean[:100] or "Untitled Note"

# Categorize into 6 main knowledge clusters
CLUSTERS = {
    "01 - AI Coding & Software Architecture": {
        "title": "AI Coding & Software Architecture Index",
        "description": "Các bài học về kiến trúc phần mềm (Monorepo, Clean Architecture), quy trình dev bằng AI (Superpowers Workflow, TDD), Sơ đồ tri thức codebase (Graphify, Refify) và tích hợp Claude Code.",
        "keywords": ["monorepo", "architecture", "codebase", "graphify", "refify", "claude code", "tdd", "software", "phần mềm", "lập trình", "code", "dev", "workflow"]
    },
    "02 - AI Writing & Prompt Engineering": {
        "title": "AI Writing & Prompt Engineering Index",
        "description": "Các kỹ thuật Prompting nâng cao, chuỗi prompt biên tập, mô phỏng vai trò chuyên gia, kiểm soát chống bịa đặt (hallucination) và tạo nội dung.",
        "keywords": ["prompt", "writing", "biên tập", "nội dung", "hallucination", "bịa đặt", "chuyên gia", "role", "gpt", "llm"]
    },
    "03 - Video Production & AI Editing": {
        "title": "Video Production & AI Editing Index",
        "description": "Công cụ và quy trình cắt ghép video tự động, WT-Shotclipp, nhận diện khuôn mặt bám sát tỷ lệ 9:16, tạo phụ đề tự động và biên tập kịch bản.",
        "keywords": ["shotclipp", "cắt video", "shorts", "tiktok", "phụ đề", "subtitle", "9:16", "khuôn mặt", "capcut", "video", "biên tập video"]
    },
    "04 - AI Motion & UI Animation Tools": {
        "title": "AI Motion & UI Animation Tools Index",
        "description": "Các công cụ đồ họa, hoạt họa web và UI (Three.js, Flutter Animations, HyperFrames CSS, UI-Animation curves).",
        "keywords": ["three.js", "animation", "ui-animation", "flutter", "css", "hyperframes", "motion", "đồ họa", "3d"]
    },
    "05 - Marketing & Content Strategy": {
        "title": "Marketing & Content Strategy Index",
        "description": "Chiến lược nội dung viral, phân tích điểm rời đi của người xem (Retention rate), tối ưu Hook & CTA, affiliate marketing.",
        "keywords": ["marketing", "affiliate", "retention", "hook", "cta", "người xem", "viral", "nội dung", "chiến lược"]
    },
    "06 - Hermes System & Knowledge Management": {
        "title": "Hermes System & Knowledge Management Index",
        "description": "Cấu trúc quản lý tri thức của Hermes, SQLite FTS5 search, RAG context injection, durable memory và lưu trữ bài học.",
        "keywords": ["hermes", "knowledge base", "fts5", "rag", "memory", "store", "tri thức", "bài học", "duyệt"]
    }
}

def assign_cluster(entry: dict, detail: dict) -> str:
    text = (entry.get("title", "") + " " + entry.get("category", "") + " " + " ".join(entry.get("key_lessons", [])) + " " + json.dumps(detail, ensure_ascii=False)).lower()
    
    scores = {}
    for cluster_name, info in CLUSTERS.items():
        score = sum(1 for kw in info["keywords"] if kw in text)
        scores[cluster_name] = score
        
    best = max(scores, key=scores.get)
    if scores[best] > 0:
        return best
    return "01 - AI Coding & Software Architecture" # Default

cluster_files = {c: [] for c in CLUSTERS}
created_notes = []

for idx, entry in enumerate(entries, 1):
    entry_id = entry.get("id", f"kb_{idx:03d}")
    raw_title = entry.get("title") or f"Bài học {entry_id}"
    safe_title = sanitize_filename(raw_title)
    
    detail = store.get_entry_detail(entry_id)
    cluster = assign_cluster(entry, detail)
    
    note_filename = f"{safe_title}.md"
    
    # Content of individual note
    content = []
    content.append("---")
    content.append(f"id: \"{entry_id}\"")
    content.append(f"title: \"{raw_title}\"")
    content.append(f"category: \"{entry.get('category', 'General')}\"")
    content.append(f"status: \"{entry.get('status', 'pending')}\"")
    content.append(f"cluster: \"{cluster}\"")
    content.append(f"learned_at: \"{entry.get('learned_at', '')}\"")
    content.append(f"source_url: \"{entry.get('source_url', '')}\"")
    content.append("tags:")
    content.append(f"  - hermes/knowledge")
    content.append(f"  - {entry.get('category', 'general').lower().replace(' ', '-')}")
    content.append("---\n")
    
    content.append(f"# {raw_title}\n")
    content.append(f"**ID Bài học:** `{entry_id}` | **Trạng thái:** `{entry.get('status')}` | **Nền tảng:** `{entry.get('platform') or 'Link'}`\n")
    
    if entry.get("source_url"):
        content.append(f"🔗 **Link nguồn:** [{entry.get('source_url')}]({entry.get('source_url')})\n")
        
    content.append(f"📌 **Thuộc nhóm kiến thức:** [[{CLUSTERS[cluster]['title']}]]\n")
    content.append("## 🎯 Bài Học Cốt Lõi\n")
    for lesson in entry.get("key_lessons", []):
        content.append(f"- {lesson}")
    content.append("")
    
    summary = detail.get("summary")
    if summary:
        content.append("## 📝 Tóm Tắt Chi Tiết\n")
        content.append(f"{summary}\n")
        
    deep = detail.get("deep_analysis")
    if deep:
        content.append("## 🔬 Phân Tích Chuyên Sâu\n")
        content.append(f"{deep}\n")
        
    how_to = detail.get("how_to_use_in_hermes") or detail.get("hermes_applications")
    if how_to:
        content.append("## ⚡ Ứng Dụng Trong Hermes Agent\n")
        content.append(f"{how_to}\n")
        
    content.append("\n---\n")
    content.append("## 🔗 Liên Kết Đồ Thị (Graph Wikilinks)\n")
    content.append(f"- **Nhóm chủ đề:** [[{CLUSTERS[cluster]['title']}]]")
    content.append(f"- **Master Index:** [[Hermes Knowledge Master Graph Index]]")
    
    # Save note file
    note_path = vault_dir / note_filename
    note_path.write_text("\n".join(content), encoding="utf-8")
    
    cluster_files[cluster].append({
        "id": entry_id,
        "title": raw_title,
        "filename": safe_title,
        "status": entry.get("status")
    })
    
    created_notes.append(note_filename)

# Create 6 Cluster Index Notes
for cluster_name, info in CLUSTERS.items():
    cluster_title = info["title"]
    idx_content = []
    idx_content.append("---")
    idx_content.append(f"type: \"index_note\"")
    idx_content.append(f"cluster: \"{cluster_name}\"")
    idx_content.append("tags:")
    idx_content.append("  - hermes/index")
    idx_content.append("---\n")
    
    idx_content.append(f"# 📂 {cluster_title}\n")
    idx_content.append(f"{info['description']}\n\n")
    idx_content.append(f"**Tổng số bài học trong nhóm này:** {len(cluster_files[cluster_name])} bài.\n\n")
    idx_content.append("## 📜 Danh Sách Bài Học (Graph Nodes)\n\n")
    
    for i, item in enumerate(cluster_files[cluster_name], 1):
        icon = "✅" if item["status"] == "approved" else "⏳"
        idx_content.append(f"{i}. {icon} [[{item['filename']}]] (`{item['id']}`)")
        
    idx_content.append("\n---\n")
    idx_content.append("🔗 **Trở về:** [[Hermes Knowledge Master Graph Index]]")
    
    (vault_dir / f"{cluster_title}.md").write_text("\n".join(idx_content), encoding="utf-8")

# Create Master Index Note
master_content = []
master_content.append("---")
master_content.append("type: \"master_index\"")
master_content.append("tags:")
master_content.append("  - hermes/master_index")
master_content.append("---\n")

master_content.append("# 🌐 HERMES KNOWLEDGE GRAPH MASTER INDEX\n")
master_content.append("Sơ đồ tri thức tổng hợp toàn bộ các bài học trong hệ thống Hermes Agent.\n\n")
master_content.append(f"📊 **Tổng số node bài học:** `{len(entries)}` bài học.\n\n")
master_content.append("## 🧩 Các Nhóm Tri Thức Chính (Cluster Index Nodes)\n\n")

for cluster_name, info in CLUSTERS.items():
    count = len(cluster_files[cluster_name])
    master_content.append(f"### 📁 [[{info['title']}]] ({count} bài)")
    master_content.append(f"{info['description']}\n")

master_content.append("---\n")
master_content.append("## 📌 Hướng dẫn xem Graph trong Obsidian\n")
master_content.append("1. Mở phần mềm Obsidian.\n")
master_content.append(f"2. Mở thư mục Vault: `{vault_dir}`.\n")
master_content.append("3. Nhấn tổ hợp phím `Ctrl + G` (hoặc mở thanh sidebar trái -> chọn Graph View) để xem sơ đồ liên kết node tri thức.\n")

(vault_dir / "Hermes Knowledge Master Graph Index.md").write_text("\n".join(master_content), encoding="utf-8")

# Copy vault to knowledge_base/obsidian_vault as well
for file in vault_dir.glob("*.md"):
    shutil.copy2(file, kb_vault_dir / file.name)

print(f"Successfully generated {len(created_notes)} lesson notes + 6 cluster indexes + 1 master index in:")
print(f" - Workspace Vault path: {vault_dir}")
print(f" - Knowledge Base Vault: {kb_vault_dir}")
