"""
scripts/test_knowledge_store_safety.py — Safety and reliability tests for UnifiedKnowledgeStore.
"""

import os
import sys
import shutil
import json
from pathlib import Path

# Add root folder to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# 1. Patch the knowledge base directory to use a test folder
import core.knowledge_store
TEST_KB_DIR = Path(__file__).resolve().parent.parent / "knowledge_base_test"
core.knowledge_store.KB_DIR = TEST_KB_DIR
core.knowledge_store.UNIFIED_INDEX_FILE = TEST_KB_DIR / "unified_index.json"
core.knowledge_store.ENTRIES_DIR = TEST_KB_DIR / "entries"

from core.knowledge_store import UnifiedKnowledgeStore

def clean_test_env():
    if TEST_KB_DIR.exists():
        shutil.rmtree(TEST_KB_DIR)

def run_store_tests():
    print("--- 🚀 BẮT ĐẦU CHẠY STORE SAFETY TESTS ---")
    clean_test_env()
    
    # Khởi tạo store
    store = UnifiedKnowledgeStore()
    
    # ----------------------------------------------------
    # Test 1: Tạo mới entry pending
    # ----------------------------------------------------
    print("[*] Test 1: Add new entry pending...")
    entry1 = store.add_entry(
        title="Bài học skincare buổi sáng",
        source_url="https://www.tiktok.com/@beauty/video/111",
        platform="tiktok",
        category="skincare",
        key_lessons=["Rửa mặt bằng nước ấm", "Thoa kem chống nắng"],
        detail_data={"author": "BeautyBlogger"},
        source="telegram_job"
    )
    
    assert entry1["status"] == "pending"
    assert entry1["title"] == "Bài học skincare buổi sáng"
    assert entry1["approved_by"] is None
    
    # Kiểm tra file vật lý tồn tại
    assert core.knowledge_store.UNIFIED_INDEX_FILE.exists()
    assert (core.knowledge_store.ENTRIES_DIR / f"{entry1['id']}.json").exists()
    print("  -> OK: Add new entry pending hoạt động tốt.")

    # ----------------------------------------------------
    # Test 2: Thử add trùng source_url
    # ----------------------------------------------------
    print("[*] Test 2: Add duplicate source_url...")
    # Add trùng khi trạng thái đang là pending -> cập nhật metadata
    entry1_dup = store.add_entry(
        title="Bài học skincare buổi sáng (Cập nhật)",
        source_url="https://www.tiktok.com/@beauty/video/111", # Trùng
        platform="tiktok",
        category="skincare",
        key_lessons=["Rửa mặt bằng nước ấm", "Thoa kem chống nắng", "Thêm serum vitamin C"],
        detail_data={"author": "BeautyBlogger", "updated": True},
        source="telegram_job"
    )
    
    assert entry1_dup["id"] == entry1["id"] # Phải giữ nguyên ID
    assert len(entry1_dup["key_lessons"]) == 3 # Đã cập nhật key lessons
    
    # Cập nhật thành approved
    store.mark_approved(entry1["id"], approved_by="admin_test", approval_mode="manual")
    
    # Add trùng khi trạng thái là approved -> Trả về entry cũ, không thay đổi
    entry1_approved_dup = store.add_entry(
        title="Bài học skincare buổi sáng (Lần 3)",
        source_url="https://www.tiktok.com/@beauty/video/111",
        platform="tiktok",
        category="skincare"
    )
    assert entry1_approved_dup["id"] == entry1["id"]
    assert entry1_approved_dup["status"] == "approved"
    
    # Đảm bảo không sinh thêm entry mới trong index
    assert len(store.list_entries()) == 1
    print("  -> OK: Chống trùng và cập nhật duplicate URL hoạt động tốt.")

    # ----------------------------------------------------
    # Test 3: Phê duyệt (Approve) bằng ID và check fallback slug
    # ----------------------------------------------------
    print("[*] Test 3: Approve by ID and fallback slug...")
    entry2 = store.add_entry(
        title="Mẹo nấu ăn ngon",
        source_url="https://www.youtube.com/watch?v=cooking123",
        platform="youtube",
        category="cooking"
    )
    
    # Approve bằng ID
    approved = store.mark_approved(entry2["id"], approved_by="chef_user", approval_mode="manual")
    assert approved is not None
    assert approved["status"] == "approved"
    assert approved["approved_by"] == "chef_user"
    assert approved["approval_mode"] == "manual"
    
    # Khởi tạo entry 3 để test fallback slug
    entry3 = store.add_entry(
        title="Đánh giá iPhone 18 Pro",
        source_url="https://www.youtube.com/watch?v=iphone18",
        platform="youtube",
        category="tech"
    )
    # Approve bằng slug
    approved_slug = store.mark_approved(entry3["slug"], approved_by="tech_reviewer", approval_mode="manual")
    assert approved_slug is not None
    assert approved_slug["id"] == entry3["id"]
    assert approved_slug["status"] == "approved"
    print("  -> OK: Approve bằng ID và fallback slug thành công.")

    # ----------------------------------------------------
    # Test 4: Từ chối (Reject) bằng ID
    # ----------------------------------------------------
    print("[*] Test 4: Reject by ID...")
    entry4 = store.add_entry(
        title="Tin tức rác",
        source_url="https://www.tiktok.com/@spam/video/999",
        platform="tiktok",
        category="spam"
    )
    rejected = store.mark_rejected(entry4["id"], rejected_by="moderator", rejection_reason="Nội dung spam quảng cáo")
    assert rejected is not None
    assert rejected["status"] == "rejected"
    assert rejected["rejected_by"] == "moderator"
    assert rejected.get("rejection_reason") == "Nội dung spam quảng cáo"
    print("  -> OK: Reject bằng ID thành công.")

    # ----------------------------------------------------
    # Test 5: Khôi phục khi file index bị hỏng JSON
    # ----------------------------------------------------
    print("[*] Test 5: Fallback to backup when index is corrupted...")
    # Đảm bảo backup file đã được tạo
    backup_file = TEST_KB_DIR / "unified_index.backup.json"
    assert backup_file.exists()
    
    # Cố tình ghi đè phá hỏng file chính
    core.knowledge_store.UNIFIED_INDEX_FILE.write_text("{ corrupted json ...", encoding="utf-8")
    
    # Khởi tạo store mới (nó sẽ load_index)
    store_recovery = UnifiedKnowledgeStore()
    recovered_entries = store_recovery.list_entries()
    
    # Phải khôi phục lại được các entry từ backup
    assert len(recovered_entries) > 0
    print(f"  -> OK: Đã khôi phục thành công {len(recovered_entries)} entries từ backup.")

    # Dọn dẹp
    clean_test_env()
    print("✨ --- TẤT CẢ STORE SAFETY TESTS ĐỀU ĐẠT (PASS) --- ✨")

if __name__ == "__main__":
    run_store_tests()
