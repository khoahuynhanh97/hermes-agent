#!/usr/bin/env python3
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import os

WIDTH = 1080
HEIGHT = 1920
FPS = 30
BASE_DIR = r"D:/work/hermes-agent"

class VideoEffects:
    @staticmethod
    def add_glow(img, intensity=30):
        pil_img = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        glow = pil_img.filter(ImageFilter.GaussianBlur(intensity))
        blended = Image.blend(pil_img, glow, 0.3)
        return cv2.cvtColor(np.array(blended), cv2.COLOR_RGB2BGR)
    
    @staticmethod
    def add_particles(frame, num_particles=20, color=(255, 200, 100)):
        overlay = frame.copy()
        for _ in range(num_particles):
            x = np.random.randint(0, WIDTH)
            y = np.random.randint(0, HEIGHT)
            radius = np.random.randint(2, 8)
            cv2.circle(overlay, (x, y), radius, color, -1)
        return cv2.addWeighted(overlay, 0.4, frame, 0.6, 0)
    
    @staticmethod
    def zoom_effect(img, progress, zoom_range=(1.0, 1.15)):
        h, w = img.shape[:2]
        zoom = zoom_range[0] + (zoom_range[1] - zoom_range[0]) * progress
        new_w, new_h = int(w * zoom), int(h * zoom)
        resized = cv2.resize(img, (new_w, new_h))
        start_x = (new_w - w) // 2
        start_y = (new_h - h) // 2
        return resized[start_y:start_y+h, start_x:start_x+w]
    
    @staticmethod
    def add_gradient_overlay(frame, color1, color2, alpha=0.2):
        overlay = np.zeros_like(frame, dtype=np.uint8)
        for i in range(HEIGHT):
            ratio = i / HEIGHT
            r = int(color1[2] * (1 - ratio) + color2[2] * ratio)
            g = int(color1[1] * (1 - ratio) + color2[1] * ratio)
            b = int(color1[0] * (1 - ratio) + color2[0] * ratio)
            overlay[i, :] = [b, g, r]
        return cv2.addWeighted(frame, 1 - alpha, overlay, alpha, 0)

def add_text_with_style(frame, text, y_pos, font_size=60, color=(255,255,255)):
    pil_img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(pil_img)
    try:
        font = ImageFont.truetype(r"C:/Windows/Fonts/arialbd.ttf", font_size)
    except:
        font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    x = (WIDTH - text_width) // 2
    draw.text((x+3, y_pos+3), text, font=font, fill=(0, 0, 0))
    draw.text((x, y_pos), text, font=font, fill=color)
    return cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)

def create_scene(img_path, duration_sec, title, caption, bg_colors, particle_color):
    frames = []
    total_frames = int(duration_sec * FPS)
    full_path = os.path.join(BASE_DIR, img_path)
    img = cv2.imread(full_path)
    if img is None:
        print(f"Cannot load: {full_path}")
        return frames
    h, w = img.shape[:2]
    target_h = int(HEIGHT * 0.5)
    scale = target_h / h
    new_w, new_h = int(w * scale), target_h
    img_resized = cv2.resize(img, (new_w, new_h))
    for i in range(total_frames):
        progress = i / total_frames
        frame = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
        frame = VideoEffects.add_gradient_overlay(frame, bg_colors[0], bg_colors[1], 0.85)
        zoom_progress = np.sin(progress * np.pi / 2) * 0.1
        zoomed_img = VideoEffects.zoom_effect(img_resized, zoom_progress, (1.0, 1.05))
        y_offset = 500
        x_offset = (WIDTH - zoomed_img.shape[1]) // 2
        frame[y_offset:y_offset+zoomed_img.shape[0], x_offset:x_offset+zoomed_img.shape[1]] = zoomed_img
        frame = VideoEffects.add_glow(frame, 15)
        frame = VideoEffects.add_particles(frame, 30, particle_color)
        frame = add_text_with_style(frame, title, 200, 70, (255, 255, 255))
        frame = add_text_with_style(frame, caption, HEIGHT - 400, 50, (255, 255, 200))
        frames.append(frame)
    return frames

def main():
    print("Creating AI-style video UGREEN...")
    output_path = r"C:/Users/ninak/Downloads/sac-ugreen/ugreen_ai_style_30s.mp4"
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(output_path, fourcc, FPS, (WIDTH, HEIGHT))
    scenes = [
        ("assets/ugreen-nexode-robot-uno/vn-11134201-81ztc-mrffmjlnrabp6b.png", 6, "UGREEN Nexode Robot Uno", "Nguoi ban sac dang yeu!", ((138, 43, 226), (75, 0, 130)), (255, 200, 150)),
        ("assets/ugreen-nexode-robot-uno/sg-11134201-7rbm5-m62nvl361r4n2c.png", 5, "Thiet ke Robot Dang Yeu", "LED face | GaN sieu nho gon", ((180, 100, 200), (255, 150, 200)), (255, 150, 255)),
        ("assets/ugreen-nexode-robot-uno/sg-11134201-7rbm9-m62nviffzac796.png", 8, "30W Sac Sieu Nhanh", "0-50%% chi 30 phut | PD 3.0", ((20, 20, 40), (50, 100, 50)), (0, 255, 100)),
        ("assets/ugreen-nexode-robot-uno/vn-11134103-81ztc-mlftjsv7bklkcc.png", 6, "Bao Ve Toan Dien", "Chong qua nhiet | Qua ap", ((50, 50, 150), (100, 150, 255)), (150, 200, 255)),
        ("assets/ugreen-nexode-robot-uno/sg-11134201-7rbnf-m62nvjqm29j4f6.png", 5, "UGREEN - Cong Nghe", "Mua ngay: Shopee & TGDD", ((200, 200, 220), (240, 240, 245)), (200, 150, 255)),
    ]
    total = 0
    for img_path, dur, title, caption, colors, pcol in scenes:
        print(f"Scene: {title} ({dur}s)")
        frames = create_scene(img_path, dur, title, caption, colors, pcol)
        for frame in frames:
            out.write(frame)
            total += 1
    out.release()
    print(f"Done! {output_path}")
    print(f"Total: {total} frames = {total/FPS:.1f}s @ {FPS}fps")
    print(f"Size: {WIDTH}x{HEIGHT} (9:16)")

if __name__ == '__main__':
    main()
