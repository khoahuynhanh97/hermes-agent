"""
scripts/test_script_generator_knowledge_injection.py — Verify knowledge injection logic in script generation (approved only).
"""

import os
import sys
import shutil
import json
from pathlib import Path

# Add root folder to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Patch core.knowledge_store and core.script_generator to use test KB
import core.knowledge_store
import core.style_profiler
TEST_KB_DIR = Path(__file__).resolve().parent.parent / "knowledge_base_test"
core.knowledge_store.KB_DIR = TEST_KB_DIR
core.knowledge_store.UNIFIED_INDEX_FILE = TEST_KB_DIR / "unified_index.json"
core.knowledge_store.ENTRIES_DIR = TEST_KB_DIR / "entries"
core.style_profiler.KB_DIR = str(TEST_KB_DIR)
core.style_profiler.PROFILES_FILE = str(TEST_KB_DIR / 'style_profiles.json')

from core.knowledge_store import UnifiedKnowledgeStore
from core.script_generator import generate_script

# Mock requests.post to avoid hitting real Gemini API endpoints
import core.script_generator
import requests

class MockResponse:
    def __init__(self, json_data, status_code):
        self.json_data = json_data
        self.status_code = status_code

    def json(self):
        return self.json_data

    @property
    def text(self):
        return json.dumps(self.json_data)

last_captured_prompt = ""

def mock_post(url, headers=None, json=None, timeout=None):
    global last_captured_prompt
    if json and "contents" in json:
        last_captured_prompt = json["contents"][0]["parts"][0]["text"]
        
    mock_data = {
        "candidates": [{
            "content": {
                "parts": [{
                    "text": '{"voice_script": "Dòng 1 lời đọc kịch bản", "caption": "Caption hay", "hashtags": "#test"}'
                }]
            }
        }]
    }
    return MockResponse(mock_data, 200)

requests.post = mock_post
core.script_generator.requests.post = mock_post

def clean_test_env():
    if TEST_KB_DIR.exists():
        shutil.rmtree(TEST_KB_DIR)

def run_script_generator_tests():
    global last_captured_prompt
    print("--- 🚀 BẮT ĐẦU CHẠY SCRIPT GENERATOR KNOWLEDGE INJECTION TESTS ---")
    clean_test_env()
    
    # 1. Khởi tạo Test Store
    store = UnifiedKnowledgeStore()
    
    # ----------------------------------------------------
    # Test 1: Không có approved entry -> vẫn generate bình thường
    # ----------------------------------------------------
    print("[*] Test 1: No approved entries...")
    last_captured_prompt = ""
    res = generate_script(
        product_name="Kem dưỡng ẩm",
        description="Cấp ẩm cho da khô",
        price="250.000đ",
        selling_points="Thành phần tự nhiên",
        target_audience="Nữ da khô",
        pain_points="Da bong tróc nứt nẻ",
        style="Mở đầu tò mò"
    )
    
    assert "error" not in res
    assert "[KIẾN THỨC ĐÃ HỌC" not in last_captured_prompt
    print("  -> OK: Không có approved entry vẫn hoạt động bình thường.")

    # ----------------------------------------------------
    # Test 2: Có pending/rejected entries -> không được inject
    # ----------------------------------------------------
    print("[*] Test 2: Pending and rejected entries are not injected...")
    
    # Tạo pending entry
    store.add_entry(
        title="Công thức skincare của hot girl",
        source_url="https://www.tiktok.com/@hotgirl/video/1",
        platform="tiktok",
        category="skincare",
        key_lessons=["Bôi kem 2 lần một ngày"],
        detail_data={"text": "skincare review detail"}
    )
    
    # Tạo rejected entry
    entry_rej = store.add_entry(
        title="Mẹo trị mụn sai lầm",
        source_url="https://www.tiktok.com/@badadvice/video/2",
        platform="tiktok",
        category="skincare",
        key_lessons=["Dùng kem đánh răng bôi lên mụn"]
    )
    store.mark_rejected(entry_rej["id"])
    
    last_captured_prompt = ""
    res = generate_script(
        product_name="Kem dưỡng ẩm",
        description="Cấp ẩm cho da khô",
        price="250.000đ"
    )
    
    assert "[KIẾN THỨC ĐÃ HỌC" not in last_captured_prompt
    assert "Bôi kem 2 lần một ngày" not in last_captured_prompt
    assert "Dùng kem đánh răng bôi lên mụn" not in last_captured_prompt
    print("  -> OK: Pending & Rejected entries không bị rò rỉ vào prompt.")

    # ----------------------------------------------------
    # Test 3: Có approved entry -> Được inject đúng quy tắc
    # ----------------------------------------------------
    print("[*] Test 3: Approved entry is correctly injected with safety instructions...")
    
    # Tạo approved entry
    entry_app = store.add_entry(
        title="Công thức skincare khoa học thực tế",
        source_url="https://www.tiktok.com/@doctor/video/555",
        platform="tiktok",
        category="skincare",
        key_lessons=["Bôi kem chống nắng phổ rộng", "Dùng sữa rửa mặt dịu nhẹ"]
    )
    store.mark_approved(entry_app["id"], approved_by="doctor_editor", approval_mode="manual")
    
    last_captured_prompt = ""
    res = generate_script(
        product_name="Kem chống nắng Sunblocker",
        description="Chống nắng toàn diện SPF50+",
        price="300.000đ"
    )
    
    assert "[KIẾN THỨC ĐÃ HỌC" in last_captured_prompt
    assert "Bôi kem chống nắng phổ rộng" in last_captured_prompt
    assert "HƯỚNG DẪN SỬ DỤNG BÀI HỌC (AN TOÀN SÁNG TẠO)" in last_captured_prompt
    assert "Do not copy exact wording" in last_captured_prompt
    print("  -> OK: Approved entry được inject thành công kèm hướng dẫn an toàn sáng tạo.")

    # Dọn dẹp
    clean_test_env()
    print("✨ --- TẤT CẢ SCRIPT GENERATOR TESTS ĐỀU ĐẠT (PASS) --- ✨")

if __name__ == "__main__":
    run_script_generator_tests()
