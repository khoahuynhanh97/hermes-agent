import os
import sys
import re

# Thêm thư mục hiện tại vào Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import config
from tools.video_downloader import download_video
from tools.video_analyser import analyze_video, init_gemini
from tools.script_generator import generate_tiktok_script, check_ollama

def clean_filename(filename):
    """Lọc ký tự đặc biệt để tạo tên file an toàn"""
    return re.sub(r'[\\/*?:"<>| ]', '_', filename)

def list_downloaded_files(directory="downloads"):
    """Liệt kê danh sách các file đã tải xuống để người dùng chọn nhanh"""
    if not os.path.exists(directory):
        return []
    files = [f for f in os.listdir(directory) if os.path.isfile(os.path.join(directory, f))]
    return files

def list_report_files(directory="reports"):
    """Liệt kê danh sách các báo cáo phân tích đã lưu"""
    if not os.path.exists(directory):
        return []
    files = [f for f in os.listdir(directory) if f.endswith(".md") or f.endswith(".txt")]
    return files

def check_system_status():
    """Kiểm tra sức khỏe kết nối Ollama và API Key Gemini"""
    print("\n" + "="*50)
    print("      KIỂM TRA CẤU HÌNH HỆ THỐNG AGENT")
    print("="*50)
    
    # 1. Kiểm tra Ollama
    print("[*] Đang kiểm tra Ollama...")
    is_ollama_ok, is_model_installed, installed_models = check_ollama()
    model_name = getattr(config, "DEFAULT_LOCAL_MODEL", "llama3.2:3b")
    
    if is_ollama_ok:
        print(f"  [+] Kết nối Ollama: THÀNH CÔNG (tại {getattr(config, 'OLLAMA_API_URL')})")
        if is_model_installed:
            print(f"  [+] Mô hình '{model_name}': ĐÃ SẴN SÀNG (Đầy đủ điều kiện chạy local)")
        else:
            print(f"  [-] Mô hình '{model_name}': CHƯA CÀI ĐẶT")
            print(f"      (Hãy mở terminal chạy: 'ollama pull {model_name}')")
        print(f"  [i] Các mô hình hiện có: {', '.join(installed_models) if installed_models else 'Trống'}")
    else:
        print("  [x] Kết nối Ollama: THẤT BẠI (Vui lòng khởi động phần mềm Ollama trên máy)")
        
    # 2. Kiểm tra Gemini
    print("\n[*] Đang kiểm tra Google Gemini API Key...")
    gemini_key = getattr(config, "GEMINI_API_KEY", "")
    if gemini_key and gemini_key != "YOUR_GEMINI_API_KEY_HERE":
        print("  [+] API Key: Đã được điền cấu hình (Sẵn sàng phân tích video bằng Vision API)")
    else:
        print("  [-] API Key: CHƯA ĐƯỢC CẤU HÌNH (Gặp lỗi 'YOUR_GEMINI_API_KEY_HERE')")
        print("      (Bạn có thể chỉnh sửa file config.py để điền key và dùng tính năng xem video)")
        
    print("="*50)
    input("\nNhấn Enter để quay lại Menu chính...")

def run_download_option():
    print("\n" + "="*50)
    print("      1. TẢI VIDEO/AUDIO TỪ MẠNG XÃ HỘI")
    print("="*50)
    url = input("Nhập link video (TikTok, YouTube Shorts, Douyin...): ").strip()
    if not url:
        print("[!] URL không hợp lệ!")
        return
        
    print("\nTùy chọn tải về:")
    print("1. Tải toàn bộ video (mp4)")
    print("2. Chỉ tải âm thanh tách nhạc (mp3)")
    choice = input("Lựa chọn của bạn (1-2): ").strip()
    
    audio_only = (choice == "2")
    filepath = download_video(url, audio_only=audio_only)
    
    if filepath:
        print(f"\n[+] Thành công! File được lưu tại: {filepath}")
    else:
        print("\n[x] Tải file thất bại. Kiểm tra lại đường dẫn hoặc cài đặt ffmpeg.")
    input("\nNhấn Enter để tiếp tục...")

def run_analysis_option():
    print("\n" + "="*50)
    print("      2. PHÂN TÍCH VIDEO MẪU (BẰNG GEMINI VISION)")
    print("="*50)
    
    print("Bạn muốn phân tích file nào?")
    print("1. Chọn từ các file đã tải về trong thư mục 'downloads'")
    print("2. Nhập đường dẫn file trực tiếp từ máy tính")
    choice = input("Lựa chọn của bạn (1-2): ").strip()
    
    filepath = ""
    if choice == "1":
        downloaded = list_downloaded_files()
        if not downloaded:
            print("[!] Không tìm thấy file nào trong thư mục 'downloads'. Vui lòng tải trước.")
            input("\nNhấn Enter để quay lại...")
            return
            
        print("\nDanh sách file sẵn có:")
        for idx, file in enumerate(downloaded, 1):
            print(f"{idx}. {file}")
            
        file_idx = input(f"Chọn số thứ tự file (1-{len(downloaded)}): ").strip()
        try:
            selected_file = downloaded[int(file_idx) - 1]
            filepath = os.path.join("downloads", selected_file)
        except Exception:
            print("[!] Chọn sai thứ tự.")
            return
    else:
        filepath = input("Nhập đường dẫn tuyệt đối của file video/audio: ").strip(' "\'')
        
    if not filepath or not os.path.exists(filepath):
        print(f"[!] File không tồn tại: {filepath}")
        input("\nNhấn Enter để quay lại...")
        return
        
    print("\n[*] Bắt đầu gửi video lên AI Gemini để xem và phân tích...")
    result = analyze_video(filepath)
    
    print("\n=== KẾT QUẢ PHÂN TÍCH TỪ GEMINI ===")
    print(result)
    
    # Hỏi lưu báo cáo
    save_report = input("\nBạn có muốn lưu báo cáo này thành file Markdown (.md) không? (y/n): ").strip().lower()
    if save_report == 'y':
        os.makedirs("reports", exist_ok=True)
        base_name = os.path.splitext(os.path.basename(filepath))[0]
        report_path = os.path.join("reports", f"analysis_{clean_filename(base_name)}.md")
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(f"# Báo cáo phân tích video: {os.path.basename(filepath)}\n\n")
            f.write(result)
        print(f"[+] Đã lưu báo cáo tại: {os.path.abspath(report_path)}")
        
    input("\nNhấn Enter để tiếp tục...")

def run_script_generation_option():
    print("\n" + "="*50)
    print("      3. SINH KỊCH BẢN TIKTOK MỚI (OLLAMA LOCAL)")
    print("="*50)
    
    topic = input("Nhập chủ đề/Ý tưởng video mới: ").strip()
    if not topic:
        print("[!] Chủ đề không được để trống.")
        return
        
    style = input("Nhập phong cách (ví dụ: chia sẻ kiến thức, giật gân, hài hước, tâm sự) [Mặc định: chia sẻ kiến thức]: ").strip()
    if not style:
        style = "chia sẻ kiến thức, bánh cuốn"
        
    duration = input("Thời lượng video mong muốn (ví dụ: 30s, 60s, 90s) [Mặc định: 60s]: ").strip()
    if not duration:
        duration = "60s"
        
    # Hỏi xem có muốn học hỏi từ báo cáo phân tích video mẫu nào không
    reference_content = None
    use_ref = input("Bạn có muốn sinh kịch bản học theo cấu trúc của video mẫu đã phân tích trước đó không? (y/n): ").strip().lower()
    if use_ref == 'y':
        reports = list_report_files()
        if not reports:
            print("[!] Không tìm thấy báo cáo nào trong thư mục 'reports'.")
        else:
            print("\nDanh sách báo cáo sẵn có:")
            for idx, r in enumerate(reports, 1):
                print(f"{idx}. {r}")
            r_idx = input(f"Chọn báo cáo tham khảo (1-{len(reports)}): ").strip()
            try:
                selected_report = reports[int(r_idx) - 1]
                with open(os.path.join("reports", selected_report), "r", encoding="utf-8") as f:
                    reference_content = f.read()
                print(f"[+] Đã tải nội dung tham khảo từ: {selected_report}")
            except Exception:
                print("[!] Lựa chọn sai, sẽ sinh kịch bản thường không có tài liệu tham khảo.")
                
    print("\n[*] Đang gửi yêu cầu cho Ollama Local Model sinh kịch bản...")
    script = generate_tiktok_script(topic, style, duration, reference_content)
    
    print("\n=== KỊCH BẢN DO LOCAL AI TẠO RA ===")
    print(script)
    
    # Hỏi lưu kịch bản
    save_script = input("\nBạn có muốn lưu kịch bản này thành file không? (y/n): ").strip().lower()
    if save_script == 'y':
        os.makedirs("scripts", exist_ok=True)
        script_path = os.path.join("scripts", f"script_{clean_filename(topic[:20])}.md")
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(f"# Kịch bản TikTok: {topic}\n")
            f.write(f"- Phong cách: {style}\n")
            f.write(f"- Thời lượng: {duration}\n\n")
            f.write(script)
        print(f"[+] Đã lưu kịch bản tại: {os.path.abspath(script_path)}")
        
    input("\nNhấn Enter để tiếp tục...")

def run_pipeline_option():
    print("\n" + "="*50)
    print("      4. QUY TRÌNH TỰ ĐỘNG TOÀN DIỆN (VIRAL PIPELINE)")
    print("      (Tải video mẫu -> Phân tích cấu trúc -> Tạo kịch bản mới)")
    print("="*50)
    
    url = input("Bước 1: Nhập link video TikTok/Reels/Shorts mẫu thành công: ").strip()
    if not url:
        print("[!] Link không hợp lệ!")
        return
        
    print("\n[*] Đang tải video mẫu về...")
    filepath = download_video(url, audio_only=False)
    if not filepath:
        print("[x] Không thể tải video. Hủy quy trình.")
        input("\nNhấn Enter để quay lại...")
        return
        
    print("\n[*] Bước 2: Tải lên Gemini để phân tích cấu trúc thành công...")
    analysis_result = analyze_video(filepath)
    print("\n--- KẾT QUẢ PHÂN TÍCH VIDEO MẪU ---")
    print(analysis_result[:800] + "\n...[Xem chi tiết báo cáo đã lưu]...")
    
    # Lưu báo cáo tự động
    os.makedirs("reports", exist_ok=True)
    base_name = os.path.splitext(os.path.basename(filepath))[0]
    report_path = os.path.join("reports", f"analysis_{clean_filename(base_name)}.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(analysis_result)
    print(f"[+] Đã lưu cấu trúc video mẫu tại: {report_path}")
    
    print("\n" + "-"*30)
    topic = input("Bước 3: Nhập chủ đề video mới của BẠN (muốn viết dựa trên cấu trúc mẫu này): ").strip()
    if not topic:
        print("[!] Chủ đề không được bỏ trống. Hủy bước viết kịch bản.")
        input("\nNhấn Enter để kết thúc...")
        return
        
    style = input("Nhập phong cách diễn đạt mới [Mặc định: Học theo cấu trúc mẫu]: ").strip()
    if not style:
        style = "Học theo cấu trúc và năng lượng của video mẫu"
        
    print("\n[*] Bước 4: Chạy Ollama sinh kịch bản mới kết hợp kiến thức từ video mẫu...")
    script = generate_tiktok_script(topic, style, "60s", analysis_result)
    
    print("\n=== KỊCH BẢN TIKTOK HOÀN CHỈNH CHO VIDEO MỚI ===")
    print(script)
    
    # Lưu kịch bản tự động
    os.makedirs("scripts", exist_ok=True)
    script_path = os.path.join("scripts", f"script_cloned_{clean_filename(topic[:20])}.md")
    with open(script_path, "w", encoding="utf-8") as f:
        f.write(f"# Kịch bản clone dựa trên video mẫu: {os.path.basename(filepath)}\n")
        f.write(f"# Chủ đề mới: {topic}\n\n")
        f.write(script)
    print(f"[+] Đã tự động lưu kịch bản mới tại: {os.path.abspath(script_path)}")
    
    input("\nQuy trình hoàn tất! Nhấn Enter để quay lại Menu chính...")

def main():
    while True:
        clear_screen()
        print("="*60)
        print("           HỆ THỐNG HERMES TIKTOK CREATING AGENT")
        print("      Hỗ trợ tải video mẫu, Phân tích thị giác & Sinh kịch bản")
        print("="*60)
        print(" 1. Tải video/âm thanh từ mạng xã hội (TikTok, Shorts, Douyin...)")
        print(" 2. Phân tích video mẫu (Xem hình ảnh, ghi lời thoại bằng Gemini)")
        print(" 3. Sinh kịch bản TikTok mới (Sử dụng Ollama Local Model)")
        print(" 4. Quy trình tự động toàn diện (Tải mẫu -> Phân tích -> Viết kịch bản mới)")
        print(" 5. Kiểm tra kết nối và cấu hình hệ thống (Ollama & Gemini)")
        print(" 6. Thoát")
        print("="*60)
        
        choice = input("Vui lòng chọn chức năng (1-6): ").strip()
        
        if choice == "1":
            run_download_option()
        elif choice == "2":
            run_analysis_option()
        elif choice == "3":
            run_script_generation_option()
        elif choice == "4":
            run_pipeline_option()
        elif choice == "5":
            check_system_status()
        elif choice == "6":
            print("\nCảm ơn bạn đã sử dụng Hermes TikTok Agent. Tạm biệt!")
            break
        else:
            input("\nLựa chọn không hợp lệ. Nhấn Enter để chọn lại...")

if __name__ == "__main__":
    main()
