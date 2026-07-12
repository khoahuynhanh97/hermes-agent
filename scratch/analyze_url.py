import os
import sys

# Thêm thư mục gốc vào Python path để import các core module
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Force stdout to UTF-8 on Windows
if sys.platform.startswith('win'):
    try:
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from core.knowledge_base import learn_from_url, KB_DIR, load_learned_list

def main():
    url = "https://www.youtube.com/watch?v=1pkCg35aLeU"
    print(f"🚀 Bắt đầu tải và phân tích video từ: {url}")
    
    # Callback log ra màn hình
    def log_callback(msg):
        print(msg)
        
    result = learn_from_url(url, category="Review", log_callback=log_callback)
    
    if "error" in result:
        print(f"\n❌ Thất bại: {result['error']}")
        sys.exit(1)
        
    slug = result["slug"]
    title = result["title"]
    print(f"\n✅ Thành công! Đã học hỏi được video: '{title}' (Slug: {slug})")
    
    # Đọc lại nội dung file Markdown đã lưu để in ra console cho người dùng
    md_path = os.path.join(KB_DIR, f"{slug}.md")
    if os.path.exists(md_path):
        print("\n--- BÁO CÁO PHÂN TÍCH ---")
        with open(md_path, 'r', encoding='utf-8') as f:
            print(f.read())
        print("-------------------------")

if __name__ == "__main__":
    main()
