import os
import sys
import re
import datetime
from pathlib import Path

# Configure custom FFmpeg binary path before importing moviepy
import config
if getattr(config, "FFMPEG_PATH", "") and os.path.exists(config.FFMPEG_PATH):
    os.environ["IMAGEIO_DICT"] = "{}"
    os.environ["FFMPEG_BINARY"] = config.FFMPEG_PATH

from moviepy.editor import VideoFileClip, ImageClip
import moviepy.video.fx.all as vfx

from editor.clip_analyzer import analyze_clip

def crop_to_9_16_vertical(clip, width=720, height=1280):
    """Crops a VideoClip to 9:16 vertical ratio and resizes to target resolution (720x1280 default)."""
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
    
    # Resize to target vertical size
    return cropped.resize(newsize=(width, height))

def get_next_clip_index(clips_dir, product_slug):
    """Scans clips_dir and returns the next index for clip naming."""
    existing_indices = []
    pattern = re.compile(rf"^{re.escape(product_slug)}_clip_(\d+)\.mp4$")
    if os.path.exists(clips_dir):
        for filename in os.listdir(clips_dir):
            match = pattern.match(filename)
            if match:
                existing_indices.append(int(match.group(1)))
    return max(existing_indices) + 1 if existing_indices else 1

def cut_materials_into_clips(
    materials_dir,
    clips_dir,
    product_slug,
    clip_duration=2.0,
    skip_start_seconds=1.0,
    max_clips_per_video=8,
    export_vertical=True,
    mute_audio=True,
    analyze_quality=True,
    reject_bad_clips=False,
    progress_callback=None
):
    """
    Cuts video files in materials_dir into short clips, crops/resizes them,
    runs quality analysis, and saves them to clips_dir.
    """
    def log(msg):
        if progress_callback:
            progress_callback(msg)
        else:
            print(msg)

    os.makedirs(clips_dir, exist_ok=True)
    
    # 1. Scan materials
    valid_video_exts = {'.mp4', '.mov', '.m4v', '.webm', '.avi', '.mkv'}
    valid_image_exts = {'.png', '.jpg', '.jpeg', '.webp'}
    material_files = []
    image_files = []
    if os.path.exists(materials_dir):
        for f in os.listdir(materials_dir):
            ext = os.path.splitext(f)[1].lower()
            if ext in valid_video_exts:
                material_files.append(os.path.join(materials_dir, f))
            elif ext in valid_image_exts:
                image_files.append(os.path.join(materials_dir, f))
                
    if not material_files and not image_files:
        log("[!] Không tìm thấy phôi video hay hình ảnh nào trong thư mục materials/ để cắt.")
        return []
        
    log(f"[*] Tìm thấy {len(material_files)} phôi video và {len(image_files)} hình ảnh sản phẩm. Bắt đầu xử lý clip {clip_duration}s...")
    results = []
    
    for mat_path in material_files:
        mat_name = os.path.basename(mat_path)
        log(f"\n[*] Đang xử lý file: {mat_name}...")
        
        try:
            # Open video file
            clip = VideoFileClip(mat_path)
            v_dur = clip.duration
            
            # Check available duration
            available_dur = v_dur - skip_start_seconds
            if available_dur < clip_duration:
                log(f"[-] Video {mat_name} quá ngắn (Tổng {v_dur:.1f}s), không đủ thời lượng cắt.")
                clip.close()
                continue
                
            num_clips = int(available_dur // clip_duration)
            target_clips = min(num_clips, max_clips_per_video)
            
            log(f"[*] Sẽ cắt {target_clips} clip từ video này (Bỏ qua {skip_start_seconds}s đầu).")
            
            for i in range(target_clips):
                start_t = skip_start_seconds + i * clip_duration
                end_t = start_t + clip_duration
                
                # Get next clip filename index
                next_idx = get_next_clip_index(clips_dir, product_slug)
                clip_filename = f"{product_slug}_clip_{next_idx:03d}.mp4"
                clip_filepath = os.path.join(clips_dir, clip_filename)
                
                log(f"  - Đang xuất clip {i+1}/{target_clips} -> {clip_filename} ({start_t:.1f}s - {end_t:.1f}s)...")
                
                try:
                    # 2. Extract and format subclip
                    sub = clip.subclip(start_t, end_t)
                    
                    if mute_audio:
                        sub = sub.without_audio()
                        
                    if export_vertical:
                        sub = crop_to_9_16_vertical(sub, width=720, height=1280)
                        
                    # Export subclip
                    sub.write_videofile(
                        clip_filepath,
                        fps=24,
                        codec="libx264",
                        audio_codec="aac" if not mute_audio else None,
                        logger=None
                    )
                    sub.close()
                    
                    # 3. Analyze Quality
                    status = "Generated"
                    deleted = False
                    error_note = ""
                    score = {
                        "brightness_score": 0.0, "motion_score": 0.0, "sharpness_score": 0.0,
                        "scene_change_score": 0.0, "vertical_score": 0.0, "overall_score": 0.0,
                        "recommendation": "Okay", "reason": "Chưa phân tích chất lượng.",
                        "source_width": clip.size[0], "source_height": clip.size[1],
                        "source_aspect_ratio": clip.size[0] / clip.size[1],
                        "output_width": 720 if export_vertical else clip.size[0],
                        "output_height": 1280 if export_vertical else clip.size[1],
                        "output_aspect_ratio": 0.5625 if export_vertical else clip.size[0] / clip.size[1]
                    }
                    
                    if analyze_quality:
                        score = analyze_clip(clip_filepath)
                        
                        # Discard Rejected clip if enabled
                        if reject_bad_clips and score["recommendation"] == "Reject":
                            log(f"    [!] Loại bỏ clip chất lượng kém (Điểm: {score['overall_score']}): {score['reason']}")
                            try:
                                os.remove(clip_filepath)
                                deleted = True
                                status = "Rejected"
                            except Exception as ex:
                                log(f"    [!] Lỗi xóa file loại bỏ: {ex}")
                                
                    # Record relative path for portability
                    rel_path = f"projects/{product_slug}/clips/{clip_filename}" if not deleted else ""
                    
                    results.append({
                        "file_path": rel_path,
                        "source_file": mat_name,
                        "start_time": round(start_t, 2),
                        "end_time": round(end_t, 2),
                        "duration": round(clip_duration, 2),
                        "brightness_score": score["brightness_score"],
                        "motion_score": score["motion_score"],
                        "sharpness_score": score["sharpness_score"],
                        "scene_change_score": score["scene_change_score"],
                        "vertical_score": score["vertical_score"],
                        "overall_score": score["overall_score"],
                        "recommendation": score["recommendation"],
                        "reason": score["reason"],
                        "status": status,
                        "deleted": deleted,
                        "error_note": error_note,
                        "created_at": datetime.datetime.now().isoformat(),
                        "source_width": score["source_width"],
                        "source_height": score["source_height"],
                        "source_aspect_ratio": score["source_aspect_ratio"],
                        "output_width": score["output_width"] if not deleted else 0,
                        "output_height": score["output_height"] if not deleted else 0,
                        "output_aspect_ratio": score["output_aspect_ratio"] if not deleted else 0.0
                    })
                    
                except Exception as clip_ex:
                    log(f"    [x] Lỗi cắt/xuất clip phân đoạn này: {clip_ex}")
                    results.append({
                        "file_path": "",
                        "source_file": mat_name,
                        "start_time": round(start_t, 2),
                        "end_time": round(end_t, 2),
                        "duration": round(clip_duration, 2),
                        "brightness_score": 0.0, "motion_score": 0.0, "sharpness_score": 0.0,
                        "scene_change_score": 0.0, "vertical_score": 0.0, "overall_score": 0.0,
                        "recommendation": "Reject", "reason": f"Lỗi xuất clip: {str(clip_ex)}",
                        "status": "Failed",
                        "deleted": True,
                        "error_note": str(clip_ex),
                        "created_at": datetime.datetime.now().isoformat(),
                        "source_width": clip.size[0], "source_height": clip.size[1],
                        "source_aspect_ratio": clip.size[0] / clip.size[1],
                        "output_width": 0, "output_height": 0, "output_aspect_ratio": 0.0
                    })
            
            clip.close()
            
        except Exception as mat_ex:
            log(f"[x] Lỗi nghiêm trọng khi đọc phôi {mat_name}: {mat_ex}. Chuyển sang phôi tiếp theo.")
            
    # 2. Process image files into 9:16 vertical video clips
    for img_path in image_files:
        img_name = os.path.basename(img_path)
        log(f"\n[*] Đang xử lý ảnh sản phẩm thành clip dọc: {img_name}...")
        try:
            next_idx = get_next_clip_index(clips_dir, product_slug)
            clip_filename = f"{product_slug}_clip_{next_idx:03d}.mp4"
            clip_filepath = os.path.join(clips_dir, clip_filename)
            
            img_clip = ImageClip(img_path).set_duration(clip_duration)
            if export_vertical:
                img_clip = crop_to_9_16_vertical(img_clip, width=720, height=1280)
            img_clip = img_clip.fadein(0.3).fadeout(0.3)
            img_clip.write_videofile(clip_filepath, fps=24, codec="libx264", logger=None)
            img_clip.close()
            
            # Analyze Quality
            score = analyze_clip(clip_filepath) if analyze_quality else {
                "brightness_score": 75.0, "motion_score": 50.0, "sharpness_score": 80.0,
                "scene_change_score": 0.0, "vertical_score": 100.0, "overall_score": 75.0,
                "recommendation": "Good", "reason": "Ảnh sản phẩm HD",
                "source_width": 720, "source_height": 1280, "source_aspect_ratio": 0.5625,
                "output_width": 720, "output_height": 1280, "output_aspect_ratio": 0.5625
            }
            
            rel_path = f"projects/{product_slug}/clips/{clip_filename}"
            results.append({
                "file_path": rel_path,
                "source_file": img_name,
                "start_time": 0.0,
                "end_time": round(clip_duration, 2),
                "duration": round(clip_duration, 2),
                "brightness_score": score["brightness_score"],
                "motion_score": score["motion_score"],
                "sharpness_score": score["sharpness_score"],
                "scene_change_score": score["scene_change_score"],
                "vertical_score": score["vertical_score"],
                "overall_score": score["overall_score"],
                "recommendation": score["recommendation"],
                "reason": score["reason"],
                "status": "Generated",
                "deleted": False,
                "error_note": "",
                "created_at": datetime.datetime.now().isoformat(),
                "source_width": score["source_width"],
                "source_height": score["source_height"],
                "source_aspect_ratio": score["source_aspect_ratio"],
                "output_width": score["output_width"],
                "output_height": score["output_height"],
                "output_aspect_ratio": score["output_aspect_ratio"]
            })
            log(f"  [+] Đã tạo clip 9:16 từ ảnh sản phẩm thành công: {clip_filename}")
        except Exception as img_ex:
            log(f"  [x] Lỗi chuyển ảnh thành clip: {img_ex}")

    return results

def cut_single_clip(
    mat_path,
    clips_dir,
    product_slug,
    start_t,
    end_t,
    export_vertical=True,
    mute_audio=True,
    analyze_quality=True,
    log_callback=None
):
    """
    Cuts a single subclip from mat_path, crops/resizes it,
    runs quality analysis, and saves it to clips_dir.
    Returns the metadata dictionary of the cut clip.
    """
    def log(msg):
        if log_callback:
            log_callback(msg)
        else:
            print(msg)

    os.makedirs(clips_dir, exist_ok=True)
    mat_name = os.path.basename(mat_path)
    
    # Get next index
    next_idx = get_next_clip_index(clips_dir, product_slug)
    clip_filename = f"{product_slug}_clip_{next_idx:03d}.mp4"
    clip_filepath = os.path.join(clips_dir, clip_filename)
    
    log(f"[*] Đang xuất clip thủ công -> {clip_filename} ({start_t:.1f}s - {end_t:.1f}s)...")
    
    clip = VideoFileClip(mat_path)
    try:
        sub = clip.subclip(start_t, end_t)
        
        if mute_audio:
            sub = sub.without_audio()
            
        if export_vertical:
            sub = crop_to_9_16_vertical(sub, width=720, height=1280)
            
        sub.write_videofile(
            clip_filepath,
            fps=24,
            codec="libx264",
            audio_codec="aac" if not mute_audio else None,
            logger=None
        )
        sub.close()
        
        status = "Generated"
        deleted = False
        error_note = ""
        
        score = {
            "brightness_score": 0.0, "motion_score": 0.0, "sharpness_score": 0.0,
            "scene_change_score": 0.0, "vertical_score": 0.0, "overall_score": 0.0,
            "recommendation": "Okay", "reason": "Chưa phân tích chất lượng.",
            "source_width": clip.size[0], "source_height": clip.size[1],
            "source_aspect_ratio": clip.size[0] / clip.size[1],
            "output_width": 720 if export_vertical else clip.size[0],
            "output_height": 1280 if export_vertical else clip.size[1],
            "output_aspect_ratio": 0.5625 if export_vertical else clip.size[0] / clip.size[1]
        }
        
        if analyze_quality:
            score = analyze_clip(clip_filepath)
            
        # Determine path to save in metadata (relative to projects if inside, else absolute)
        abs_clip_filepath = os.path.abspath(clip_filepath)
        proj_marker = f"projects{os.sep}{product_slug}"
        if proj_marker in abs_clip_filepath:
            idx = abs_clip_filepath.index(f"projects{os.sep}")
            rel_path = abs_clip_filepath[idx:].replace(os.sep, "/")
        else:
            rel_path = abs_clip_filepath.replace(os.sep, "/")
        
        result = {
            "file_path": rel_path,
            "source_file": mat_name,
            "start_time": round(start_t, 2),
            "end_time": round(end_t, 2),
            "duration": round(end_t - start_t, 2),
            "brightness_score": score["brightness_score"],
            "motion_score": score["motion_score"],
            "sharpness_score": score["sharpness_score"],
            "scene_change_score": score["scene_change_score"],
            "vertical_score": score["vertical_score"],
            "overall_score": score["overall_score"],
            "recommendation": score["recommendation"],
            "reason": score["reason"],
            "status": status,
            "deleted": deleted,
            "error_note": error_note,
            "created_at": datetime.datetime.now().isoformat(),
            "source_width": score["source_width"],
            "source_height": score["source_height"],
            "source_aspect_ratio": score["source_aspect_ratio"],
            "output_width": score["output_width"],
            "output_height": score["output_height"],
            "output_aspect_ratio": score["output_aspect_ratio"]
        }
        
        log(f"[+] Đã lưu và phân tích clip thành công: {clip_filename} (Điểm: {score['overall_score']:.1f})")
        return result
        
    except Exception as e:
        log(f"[x] Lỗi cắt video thủ công: {e}")
        raise e
    finally:
        clip.close()

