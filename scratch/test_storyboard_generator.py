import os
import sys
import json

# Add parent directory to path for imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import config
from core.storyboard_generator import generate_storyboard

def main():
    if sys.platform.startswith('win'):
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except Exception:
            pass
            
    print("=== KIỂM THỬ BỘ SINH STORYBOARD AI ===")
    
    # Check if Gemini key is available
    api_key = getattr(config, "GEMINI_API_KEY", "")
    if not api_key or api_key == "YOUR_GEMINI_API_KEY_HERE":
        print("[!] LỖI: Chưa cấu hình GEMINI_API_KEY trong file .env hoặc config.py.")
        print("[!] Hướng dẫn: Vui lòng mở tệp .env và thêm GEMINI_API_KEY trước khi chạy.")
        sys.exit(0)
        
    print(f"[*] Đang yêu cầu sinh Storyboard qua model: {config.GEMINI_MODEL}...")
    
    product_name = "Giá đỡ điện thoại gấp gọn màu trắng"
    product_desc = "Thiết kế nhôm nguyên khối bền bỉ, có khả năng xếp gọn bỏ túi, xoay 360 độ linh hoạt"
    usp = "Xoay xoay 360 độ mượt mà, chân đế cao su chống trượt tốt, nâng hạ chiều cao tùy thích"
    audience = "Học sinh học online, streamer, dân văn phòng làm việc đa nhiệm"
    pain = "Mỏi cổ khi cúi xem điện thoại lâu, giá đỡ nhựa ọp ẹp dễ lật đổ làm xước máy"
    style = "TikTok review sản phẩm chân thật, quay cận cảnh thao tác tay, ánh sáng sáng sạch, nhịp nhanh"
    bg = "Góc bàn làm việc gỗ thông tối giản, sáng sủa, có chậu sen đá nhỏ phía sau"
    img_note = "Giá đỡ bằng nhôm sơn tĩnh điện màu trắng mờ sang trọng, chân đế có đệm silicon xám"
    bg_note = "Mặt bàn gỗ vân sáng tự nhiên"
    
    result = generate_storyboard(
        product_name,
        product_desc,
        usp,
        audience,
        pain,
        style,
        bg,
        img_note,
        bg_note,
        duration_seconds=24,
        scene_count=6,
        prompt_target="Google Labs / Veo"
    )
    
    if "error" in result:
        print(f"[x] Lỗi từ Gemini API: {result['error']}")
        sys.exit(1)
        
    print("\n=== KẾT QUẢ STORYBOARD TẠO THÀNH CÔNG ===")
    print(f"Tiêu đề: {result.get('title')}")
    print(f"Ý tưởng chủ đạo: {result.get('concept_summary')}")
    print(f"Thời lượng: {result.get('video_duration')} giây | Số phân cảnh: {result.get('scene_count')}")
    
    scenes = result.get("scenes", [])
    print(f"Số phân cảnh thực tế nhận được: {len(scenes)}")
    
    if scenes:
        s1 = scenes[0]
        print(f"\n--- CHI TIẾT PHÂN CẢNH 1 ({s1.get('time_range')} | {s1.get('scene_purpose')}) ---")
        print(f"Mô tả hình ảnh: {s1.get('visual_description')}")
        print(f"Thao tác hành động: {s1.get('action_description')}")
        print(f"Góc máy: {s1.get('camera_angle')} | Chuyển động: {s1.get('camera_movement')}")
        print(f"Ánh sáng: {s1.get('lighting')} | Background: {s1.get('background')}")
        print(f"Voiceover: {s1.get('voiceover_line')}")
        print(f"Text màn hình: {s1.get('on_screen_text')}")
        print(f"\n[PROMPT ẢNH TIẾNG ANH - COPY SANG AI IMAGE]:\n{s1.get('image_prompt_en')}")
        print(f"\n[PROMPT VIDEO TIẾNG ANH - COPY SANG AI VIDEO]:\n{s1.get('video_prompt_en')}")
        print(f"\n[NEGATIVE PROMPT]:\n{s1.get('negative_prompt')}")
        
    print("\n[+] Kiểm thử hoàn thành thành công!")

if __name__ == "__main__":
    main()
