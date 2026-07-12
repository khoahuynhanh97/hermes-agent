import os
from PIL import Image, ImageDraw, ImageFont
import numpy as np
from moviepy.editor import ImageClip

def wrap_text(text, font, max_width):
    """Wraps text so it doesn't exceed max_width when drawn with font."""
    words = text.split()
    if not words:
        return ""
        
    # Temporary draw context to measure text
    img = Image.new('RGBA', (1, 1))
    draw = ImageDraw.Draw(img)
    
    lines = []
    current_line = []
    
    for word in words:
        test_line = " ".join(current_line + [word])
        try:
            bbox = draw.textbbox((0, 0), test_line, font=font)
            w = bbox[2] - bbox[0]
        except AttributeError:
            w, _ = draw.textsize(test_line, font=font)
            
        if w <= max_width:
            current_line.append(word)
        else:
            if current_line:
                lines.append(" ".join(current_line))
                current_line = [word]
            else:
                lines.append(word)
                
    if current_line:
        lines.append(" ".join(current_line))
        
    return "\n".join(lines)

def draw_subtitle_frame(text, size=(1080, 1920), font_size=50, font_color=(255, 255, 255), stroke_color=(0, 0, 0), stroke_width=4):
    """Draws subtitle text centered near the bottom with word-wrap and outlines."""
    img = Image.new('RGBA', size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # Load system font
    font_path = "arial.ttf"
    try:
        font = ImageFont.truetype(font_path, font_size)
    except IOError:
        # Fallback to default
        font = ImageFont.load_default()
        
    # Wrap text to 80% of width
    max_text_width = int(size[0] * 0.8)
    wrapped_text = wrap_text(text, font, max_text_width)
    
    # Calculate wrapped text dimensions
    lines = wrapped_text.split('\n')
    line_heights = []
    total_height = 0
    max_line_w = 0
    
    for line in lines:
        try:
            bbox = draw.textbbox((0, 0), line, font=font)
            w = bbox[2] - bbox[0]
            h = bbox[3] - bbox[1]
        except AttributeError:
            w, h = draw.textsize(line, font=font)
        # Default height safety
        h = max(h, font_size)
        line_heights.append((w, h))
        max_line_w = max(max_line_w, w)
        total_height += h + 8 # Add spacing
        
    # Vertical position (near the bottom, e.g., 200px from edge)
    start_y = size[1] - total_height - 200
    
    current_y = start_y
    for i, line in enumerate(lines):
        line_w, line_h = line_heights[i]
        # Center horizontally
        x = (size[0] - line_w) // 2
        
        # Draw outline (stroke)
        if stroke_width > 0:
            for dx in range(-stroke_width, stroke_width + 1):
                for dy in range(-stroke_width, stroke_width + 1):
                    if dx != 0 or dy != 0:
                        draw.text((x + dx, current_y + dy), line, font=font, fill=stroke_color)
                        
        # Draw main text
        draw.text((x, current_y), line, font=font, fill=font_color)
        current_y += line_h + 8
        
    return np.array(img)

def generate_subtitles_from_script(voice_script_path, audio_duration, video_size=(1080, 1920), log_callback=None):
    """
    Reads the voice script and maps lines to timestamps proportionally based on characters.
    Returns a list of tuples: (start_time, end_time, text)
    """
    def log(msg):
        if log_callback:
            log_callback(msg)
        else:
            print(msg)

    if not os.path.exists(voice_script_path):
        log("[-] Không tìm thấy file kịch bản để tạo phụ đề.")
        return []
        
    try:
        with open(voice_script_path, 'r', encoding='utf-8') as f:
            lines = [line.strip() for line in f if line.strip()]
    except Exception as e:
        log(f"[x] Lỗi đọc file kịch bản: {e}")
        return []
        
    if not lines:
        return []
        
    total_chars = sum(len(line) for line in lines)
    if total_chars == 0:
        return []
        
    subtitles = []
    current_start = 0.0
    
    for line in lines:
        # Proportion duration based on character count
        duration = (len(line) / total_chars) * audio_duration
        current_end = current_start + duration
        
        subtitles.append((current_start, current_end, line))
        current_start = current_end
        
    return subtitles

def create_subtitle_overlays(subtitles, video_size=(1080, 1920)):
    """
    Takes subtitle definitions and returns a list of moviepy ImageClips with text burnt in.
    """
    clips = []
    for start, end, text in subtitles:
        duration = end - start
        if duration <= 0:
            continue
            
        frame_np = draw_subtitle_frame(text, size=video_size)
        
        # Create image clip, set start time, set duration, make transparent
        img_clip = (ImageClip(frame_np)
                    .set_start(start)
                    .set_duration(duration))
        clips.append(img_clip)
        
    return clips
