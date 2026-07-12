import os
import sys
import random
import json

# Add parent directory to path for imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import config

# Configure custom FFmpeg binary path before importing moviepy
if getattr(config, "FFMPEG_PATH", "") and os.path.exists(config.FFMPEG_PATH):
    os.environ["IMAGEIO_DICT"] = "{}"  # Avoid imageio override issues
    os.environ["FFMPEG_BINARY"] = config.FFMPEG_PATH

from moviepy.editor import VideoFileClip, AudioFileClip, concatenate_videoclips, CompositeVideoClip, ImageClip
import moviepy.video.fx.all as vfx

from editor.subtitle_generator import generate_subtitles_from_script, create_subtitle_overlays
from editor.audio_helper import get_audio_duration
from editor.clip_analyzer import verify_final_video

def crop_to_9_16(clip):
    """Crops a VideoClip to 9:16 vertical ratio and resizes to 1080x1920."""
    w, h = clip.size
    target_ratio = 9.0 / 16.0
    current_ratio = w / h
    
    if current_ratio > target_ratio:
        # Landscape: crop width
        new_w = int(h * target_ratio)
        new_h = h
    else:
        # Extra portrait: crop height
        new_w = w
        new_h = int(w / target_ratio)
        
    # Ensure dimensions are even for H.264 video codec compatibility
    new_w = (new_w // 2) * 2
    new_h = (new_h // 2) * 2
    
    # Crop to center
    cropped = vfx.crop(clip, x_center=w/2, y_center=h/2, width=new_w, height=new_h)
    
    # Resize to standard TikTok vertical size
    return cropped.resize(newsize=(1080, 1920))

def build_tiktok_video(project_folders, add_subtitles=True, log_callback=None):
    """
    Auto-edits materials/ into final_video.mp4 aligned with voice.mp3.
    """
    def log(msg):
        if log_callback:
            log_callback(msg)
        else:
            print(msg)

    materials_dir = project_folders["materials"]
    audio_dir = project_folders["audio"]
    scripts_dir = project_folders["scripts"]
    exports_dir = project_folders["exports"]
    
    # 1. Verify Audio (Optional)
    audio_path = os.path.join(audio_dir, "voice.mp3")
    audio_exists = os.path.exists(audio_path)
    
    if audio_exists:
        audio_duration = get_audio_duration(audio_path)
        if audio_duration <= 0:
            log("[x] File âm thanh thuyết minh bị lỗi hoặc thời lượng bằng 0.")
            return None
        log(f"[*] Xác nhận âm thanh thuyết minh: {audio_duration:.2f} giây.")
    else:
        # Estimate duration from script or default
        script_path = os.path.join(scripts_dir, "voice_script.txt")
        estimated = 20.0
        if os.path.exists(script_path):
            try:
                with open(script_path, 'r', encoding='utf-8') as f:
                    text = f.read().strip()
                if text:
                    # Estimate ~13 characters per second for Vietnamese
                    estimated = max(10.0, min(90.0, len(text) * 0.075))
                    log(f"[*] Không tìm thấy file âm thanh. Ước tính thời lượng kịch bản ({len(text)} ký tự): {estimated:.2f} giây.")
            except Exception as e:
                log(f"[!] Lỗi đọc kịch bản để ước tính thời lượng: {e}")
        else:
            log(f"[*] Không có kịch bản và âm thanh. Sử dụng thời lượng mặc định: {estimated:.2f} giây.")
            
        audio_duration = estimated

    # 2. Verify and Load Video/Image Materials or Scored Clips
    valid_video_exts = {'.mp4', '.mkv', '.avi', '.mov', '.webm', '.m4v'}
    valid_image_exts = {'.png', '.jpg', '.jpeg', '.webp'}
    
    # Try loading metadata to find scored clips
    metadata = {}
    meta_path = project_folders.get("metadata_file")
    if meta_path and os.path.exists(meta_path):
        try:
            with open(meta_path, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
        except Exception as e:
            log(f"[!] Lỗi đọc tệp metadata: {e}")

    clips_list = metadata.get("clips", [])
    valid_clips = []
    clips_dir = project_folders.get("clips")
    
    if clips_dir and os.path.exists(clips_dir):
        for c in clips_list:
            if c.get("status") == "Generated" and not c.get("deleted", False):
                file_path = c.get("file_path", "")
                # Resolve relative or absolute path
                if file_path:
                    abs_path = os.path.abspath(os.path.join(project_folders["root"], "..", "..", file_path)) if not os.path.isabs(file_path) else file_path
                    if not os.path.exists(abs_path):
                        abs_path = os.path.abspath(os.path.join(project_folders["root"], os.path.basename(file_path)))
                    if not os.path.exists(abs_path):
                        abs_path = os.path.abspath(os.path.join(clips_dir, os.path.basename(file_path)))
                        
                    if os.path.exists(abs_path):
                        c["abs_path"] = abs_path
                        valid_clips.append(c)
                        
        # Fallback: check if there are clips physically on disk but not in metadata
        if not valid_clips:
            for f in os.listdir(clips_dir):
                if os.path.splitext(f)[1].lower() in valid_video_exts:
                    abs_path = os.path.abspath(os.path.join(clips_dir, f))
                    valid_clips.append({
                        "abs_path": abs_path,
                        "file_path": f"projects/{os.path.basename(project_folders['root'])}/clips/{f}",
                        "recommendation": "Okay",
                        "overall_score": 50.0
                    })
                    
    material_files = []
    image_files = []
    if os.path.exists(materials_dir):
        for f in os.listdir(materials_dir):
            ext = os.path.splitext(f)[1].lower()
            if ext in valid_video_exts:
                material_files.append(os.path.join(materials_dir, f))
            elif ext in valid_image_exts:
                image_files.append(os.path.join(materials_dir, f))
                
    if not valid_clips and not material_files and not image_files:
        log("[x] Không tìm thấy phôi video, hình ảnh hay clip đã cắt nào.")
        return None
        
    # Setup selection lists
    use_precut_clips = False
    use_images = False
    prioritized_clips = []
    clip_index = 0
    material_index = 0
    image_index = 0
    
    if valid_clips:
        log(f"[*] Phát hiện {len(valid_clips)} clip phôi đã cắt. Sử dụng làm nguồn dựng chính.")
        use_precut_clips = True
        # Prioritize: Good > Okay > Reject
        good_clips = [c for c in valid_clips if c.get("recommendation") == "Good"]
        okay_clips = [c for c in valid_clips if c.get("recommendation") == "Okay"]
        reject_clips = [c for c in valid_clips if c.get("recommendation") == "Reject"]
        
        random.shuffle(good_clips)
        random.shuffle(okay_clips)
        random.shuffle(reject_clips)
        
        prioritized_clips = good_clips + okay_clips + reject_clips
    elif material_files:
        log(f"[*] Tìm thấy {len(material_files)} phôi video sẵn có trong thư mục Phoi/.")
        random.shuffle(material_files)
    elif image_files:
        log(f"[*] Tìm thấy {len(image_files)} hình ảnh sẵn có trong thư mục Phoi/. Tiến hành dựng video từ ảnh.")
        use_images = True
        random.shuffle(image_files)

    # 3. Assemble clips to match audio duration
    log("[*] Đang biên tập và ráp khớp các phân đoạn video...")
    current_time = 0.0
    assembled_clips = []
    reader_clips_to_close = []
    
    try:
        while current_time < audio_duration:
            # Determine clip cut duration
            if current_time < 4.0:
                clip_dur = random.uniform(1.2, 1.6)
            else:
                clip_dur = random.uniform(1.8, 3.0)
                
            # Clamp duration to remaining audio length
            clip_dur = min(clip_dur, audio_duration - current_time)
            
            if use_precut_clips:
                clip_meta = prioritized_clips[clip_index % len(prioritized_clips)]
                clip_index += 1
                video_path = clip_meta["abs_path"]
                rec_val = clip_meta.get("recommendation", "Okay")
                score_val = clip_meta.get("overall_score", 50.0)
                log_tag = f"Clip đã cắt ({rec_val}, điểm {score_val})"
                
                try:
                    video_clip = VideoFileClip(video_path)
                    reader_clips_to_close.append(video_clip)
                    v_dur = video_clip.duration
                    take_dur = min(v_dur, clip_dur)
                    max_start = max(0.0, v_dur - take_dur)
                    start_p = random.uniform(0.0, max_start)
                    
                    sub_clip = video_clip.subclip(start_p, start_p + take_dur).without_audio()
                    processed_clip = crop_to_9_16(sub_clip)
                    assembled_clips.append(processed_clip)
                    current_time += take_dur
                    log(f"  - Đã ráp {take_dur:.1f}s từ {log_tag}: {os.path.basename(video_path)}")
                except Exception as e:
                    log(f"[!] Bỏ qua lỗi đọc file clip {os.path.basename(video_path)}: {e}")
                    
            elif use_images:
                img_path = image_files[image_index % len(image_files)]
                image_index += 1
                
                try:
                    # Create ImageClip
                    img_clip = ImageClip(img_path).set_duration(clip_dur)
                    processed_clip = crop_to_9_16(img_clip)
                    # Add fade in/out transitions
                    processed_clip = processed_clip.fadein(0.3).fadeout(0.3)
                    
                    assembled_clips.append(processed_clip)
                    current_time += clip_dur
                    log(f"  - Đã ráp {clip_dur:.1f}s từ Ảnh: {os.path.basename(img_path)}")
                except Exception as e:
                    log(f"[!] Bỏ qua lỗi đọc file ảnh {os.path.basename(img_path)}: {e}")
                    if len(image_files) == 1 and current_time == 0.0:
                        raise Exception("Không thể đọc ảnh duy nhất khả dụng.")
            else:
                video_path = material_files[material_index % len(material_files)]
                material_index += 1
                log_tag = "Phôi gốc"
                
                try:
                    video_clip = VideoFileClip(video_path)
                    reader_clips_to_close.append(video_clip)
                    v_dur = video_clip.duration
                    take_dur = min(v_dur, clip_dur)
                    max_start = max(0.0, v_dur - take_dur)
                    start_p = random.uniform(0.0, max_start)
                    
                    sub_clip = video_clip.subclip(start_p, start_p + take_dur).without_audio()
                    processed_clip = crop_to_9_16(sub_clip)
                    assembled_clips.append(processed_clip)
                    current_time += take_dur
                    log(f"  - Đã ráp {take_dur:.1f}s từ {log_tag}: {os.path.basename(video_path)}")
                except Exception as e:
                    log(f"[!] Bỏ qua lỗi đọc file phôi {os.path.basename(video_path)}: {e}")
                    if len(material_files) == 1 and current_time == 0.0:
                        raise Exception("Không thể đọc phôi duy nhất khả dụng.")
                    
        if not assembled_clips:
            log("[x] Không thể biên tập bất kỳ clip nào.")
            return None
            
        # 4. Concatenate and load audio
        log("[*] Đang ghép nối các đoạn clip...")
        final_video = concatenate_videoclips(assembled_clips, method="compose")
        
        if audio_exists:
            audio_clip = AudioFileClip(audio_path)
            # Force final video duration to match audio length exactly
            final_video = final_video.set_audio(audio_clip)
            final_video = final_video.set_duration(audio_clip.duration)
        else:
            final_video = final_video.set_duration(audio_duration)
        
        # 5. Burn subtitles if enabled
        script_path = os.path.join(scripts_dir, "voice_script.txt")
        if add_subtitles and os.path.exists(script_path):
            log("[*] Đang sinh và chèn phụ đề chữ...")
            subs = generate_subtitles_from_script(script_path, audio_duration, video_size=(1080, 1920), log_callback=log)
            if subs:
                sub_clips = create_subtitle_overlays(subs, video_size=(1080, 1920))
                # final composite
                final_video = CompositeVideoClip([final_video] + sub_clips)
                log(f"[+] Đã chèn {len(subs)} câu phụ đề vào video.")
                
        # 6. Export video
        os.makedirs(exports_dir, exist_ok=True)
        export_path = os.path.abspath(os.path.join(exports_dir, "final_video.mp4"))
        
        log(f"[*] Bắt đầu render video chất lượng cao (libx264, 24fps) về: {export_path}")
        
        write_opts = {
            "fps": 24,
            "codec": "libx264",
            "logger": None
        }
        if audio_exists:
            write_opts["audio_codec"] = "aac"
            write_opts["temp_audiofile"] = os.path.join(exports_dir, "temp_audio.m4a")
            write_opts["remove_temp"] = True
        else:
            write_opts["audio"] = False # Export video only (silent video)
            
        final_video.write_videofile(export_path, **write_opts)
        
        log("[+] Xuất video TikTok thành công!")
        
        # Cleanup
        if audio_exists:
            audio_clip.close()
        final_video.close()
        for c in reader_clips_to_close:
            c.close()
            
        # Run Quality Gate Verification
        try:
            verify_final_video(export_path, log_callback=log)
        except Exception as e:
            log(f"[!] Lỗi khi chạy Quality Gate kiểm định video: {e}")
            
        return export_path
        
    except Exception as e:
        log(f"[x] Lỗi trong quá trình xử lý video: {e}")
        # Make sure we try to release resources anyway
        for c in reader_clips_to_close:
            try:
                c.close()
            except Exception:
                pass
        return None
