import sys
import json
import os
from pathlib import Path

SETTINGS_PATH = Path("scratch/agent_settings.json")

def main():
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    if len(sys.argv) < 2:
        print("\n⚙️ BỘ ĐIỀU KHIỂN TÁC NHÂN LẬP TRÌNH (AGENT CONTROL):")
        print("----------------------------------------------------------------------")
        print("Sử dụng các lệnh sau trong terminal của bạn:")
        print("  python scripts/agent_control.py start   - Bật tự động quét và chạy job")
        print("  python scripts/agent_control.py stop    - Tắt tự động quét và chạy job")
        print("  python scripts/agent_control.py status  - Kiểm tra trạng thái hiện tại")
        print("----------------------------------------------------------------------\n")
        return
        
    cmd = sys.argv[1].lower()
    
    # Load current settings
    settings = {"enabled": True}
    if SETTINGS_PATH.exists():
        try:
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                settings = json.load(f)
        except Exception:
            pass
            
    if cmd == "start":
        settings["enabled"] = True
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2)
        print("✅ Đã BẬT chế độ tự động quét và xử lý job lập trình ngầm (Mỗi 2 phút).")
    elif cmd == "stop":
        settings["enabled"] = False
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2)
        print("⏸️ Đã TẮT/TẠM DỪNG chế độ tự động quét và xử lý job lập trình ngầm.")
    elif cmd == "status":
        status = "ĐANG HOẠT ĐỘNG (Active)" if settings.get("enabled", True) else "ĐANG TẠM DỪNG (Paused)"
        print(f"Trạng thái quét Job ngầm của AI: {status}")
    else:
        print(f"Lệnh không hợp lệ: {cmd}")

if __name__ == "__main__":
    main()
