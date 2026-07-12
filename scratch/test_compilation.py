import os
import sys

# Add parent directory to path for imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.project_manager import ProjectManager
from editor.video_editor import build_tiktok_video

def main():
    if sys.platform.startswith('win'):
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except Exception:
            pass
            
    print("=== TEST COMPILATION WITH METADATA ===")
    pm = ProjectManager()
    slug = "gia-do-dien-thoai-co-the-xoay-360-do"
    folders = pm.get_project_folders(slug)
    
    print(f"[*] Project slug: {slug}")
    print(f"[*] Folders: {folders}")
    
    export_path = build_tiktok_video(
        project_folders=folders,
        add_subtitles=True,
        log_callback=print
    )
    
    if export_path and os.path.exists(export_path):
        print(f"[+] Success! Final video: {export_path}")
    else:
        print("[x] Failed to compile video.")

if __name__ == "__main__":
    main()
