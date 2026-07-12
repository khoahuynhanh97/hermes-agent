import os
import sys
import shutil
import subprocess

# Add parent directory to path for imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import config
from core.project_manager import ProjectManager
from editor.clip_cutter import cut_materials_into_clips
from editor.video_editor import build_tiktok_video

def main():
    if sys.platform.startswith('win'):
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except Exception:
            pass
            
    print("=== BẮT ĐẦU CHẠY WORKFLOW CHO SẢN PHẨM ===")
    
    product_name = "Giá đỡ điện thoại có thể xoay 360 độ"
    source_dir = r"C:\Users\TeamSol\Downloads\TIKTOK\gia_do_dien_thoai"
    
    # 1. Khởi tạo dự án
    print("[*] Đang khởi tạo dự án...")
    pm = ProjectManager()
    project_dir, slug = pm.initialize_project(
        product_name=product_name,
        description="Giá đỡ điện thoại xoay 360 độ, chất liệu kim loại cao cấp, chống rung tốt.",
        price="150.000đ",
        selling_points="Xoay 360 độ tiện lợi, gấp gọn bỏ túi, chân đế kim loại chắc chắn",
        target_audience="Người dùng xem phim, livestreamer, dân văn phòng quay dựng clip",
        pain_points="Giá đỡ nhựa ọp ẹp dễ gãy, không xoay được các góc, mỏi cổ khi cúi xem"
    )
    
    folders = pm.get_project_folders(slug)
    print(f"  [+] Đã khởi tạo dự án slug: {slug}")
    print(f"  [+] Thư mục dự án: {project_dir}")
    
    # 2. Sao chép phôi từ thư mục mẫu của người dùng
    print("[*] Đang sao chép các tệp phôi .mp4 từ nguồn...")
    if not os.path.exists(source_dir):
        print(f"[x] LỖI: Thư mục nguồn không tồn tại: {source_dir}")
        sys.exit(1)
        
    copied_count = 0
    for file in os.listdir(source_dir):
        if file.lower().endswith(".mp4"):
            src_file_path = os.path.join(source_dir, file)
            dest_file_path = os.path.join(folders["materials"], file)
            print(f"  - Sao chép: {file} -> materials/")
            shutil.copy2(src_file_path, dest_file_path)
            copied_count += 1
            
    print(f"  [+] Đã sao chép {copied_count} tệp phôi vào thư mục materials.")
    if copied_count == 0:
        print("[x] LỖI: Không tìm thấy phôi video .mp4 nào để tiếp tục.")
        sys.exit(1)
        
    # 3. Tạo kịch bản mẫu phụ đề (để ghi phụ đề chữ)
    print("[*] Đang tạo kịch bản voice_script.txt làm phụ đề...")
    subtitles_text = """Giá đỡ điện thoại xoay 360 độ thông minh.
Thiết kế hoàn toàn bằng hợp kim nhôm siêu chắc chắn.
Dễ dàng xoay chuyển mọi góc độ theo ý thích của bạn.
Có thể gấp gọn bỏ túi tiện lợi mang đi bất cứ đâu.
Chân đế đệm cao su chống trơn trượt hiệu quả tuyệt đối.
Độ cao nâng hạ linh hoạt giúp chống mỏi cổ mỏi vai gáy.
Sản phẩm cực kỳ lý tưởng để livestream và học online.
Nhấn vào giỏ hàng bên dưới để sở hữu ngay hôm nay nhé!"""
    
    script_file_path = os.path.join(folders["scripts"], "voice_script.txt")
    with open(script_file_path, "w", encoding="utf-8") as f:
        f.write(subtitles_text.strip())
    print("  [+] Đã lưu kịch bản phụ đề.")
    
    # 4. Sinh file âm thanh câm (silent audio) dài 24s làm âm thanh nền
    print("[*] Đang tạo file âm thanh voice.mp3 câm (24 giây)...")
    ffmpeg_bin = config.FFMPEG_PATH if config.FFMPEG_PATH else "ffmpeg"
    audio_output_path = os.path.join(folders["audio"], "voice.mp3")
    
    # Lệnh ffmpeg tạo silent audio dài 24 giây
    cmd = [
        ffmpeg_bin,
        "-y",
        "-f", "lavfi",
        "-i", "anullsrc=r=44100:cl=mono",
        "-t", "24",
        "-q:a", "9",
        "-acodec", "libmp3lame",
        audio_output_path
    ]
    
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=15)
        if res.returncode == 0:
            print("  [+] Đã tạo thành công file âm thanh câm voice.mp3 (24s).")
        else:
            print(f"  [x] Lỗi ffmpeg sinh audio: {res.stderr}")
            sys.exit(1)
    except Exception as e:
        print(f"  [x] Lỗi thực thi lệnh sinh audio: {e}")
        sys.exit(1)
        
    # 5. Cắt phôi thành các clip dọc 9:16 và phân tích chất lượng bằng OpenCV
    print("[*] Đang tiến hành cắt clip phôi & chấm điểm chất lượng OpenCV...")
    
    # Thực hiện cắt
    clip_results = cut_materials_into_clips(
        materials_dir=folders["materials"],
        clips_dir=folders["clips"],
        product_slug=slug,
        clip_duration=2.5,          # Cắt mỗi clip dài 2.5s
        skip_start_seconds=1.0,     # Bỏ qua 1s đầu của phôi
        max_clips_per_video=6,      # Tối đa 6 clip từ một phôi gốc
        export_vertical=True,       # Cắt dọc 9:16
        mute_audio=True,            # Loại bỏ âm thanh phôi gốc
        analyze_quality=True,       # Phân tích chất lượng
        reject_bad_clips=False      # Giữ lại các clip kể cả điểm thấp (mặc định)
    )
    
    print(f"  [+] Đã cắt thành công {len(clip_results)} clips.")
    
    # Cập nhật metadata
    metadata = pm.get_metadata(slug)
    metadata["clips"] = clip_results
    pm.save_metadata(slug, metadata)
    print("  [+] Đã lưu thông tin clips vào metadata.json.")
    
    # 6. Ghép nối clip, chèn phụ đề chữ, xuất video TikTok hoàn chỉnh
    print("[*] Đang bắt đầu dựng và render video TikTok hoàn chỉnh...")
    
    export_path = build_tiktok_video(
        project_folders=folders,
        add_subtitles=True,
        log_callback=print
    )
    
    if export_path and os.path.exists(export_path):
        print("\n" + "="*50)
        print("      DỰNG VIDEO THÀNH CÔNG!")
        print("="*50)
        print(f"[+] Video thành phẩm: {export_path}")
        
        # Cập nhật kết quả vào metadata
        metadata = pm.get_metadata(slug)
        metadata["exports"] = {
            "final_video_path": export_path,
            "created_at": datetime_str()
        }
        pm.save_metadata(slug, metadata)
        print("[+] Đã lưu đường dẫn xuất video vào metadata.json.")
    else:
        print("\n[x] LỖI: Dựng video thất bại.")
        sys.exit(1)

def datetime_str():
    import datetime
    return datetime.datetime.now().isoformat()

if __name__ == "__main__":
    main()
