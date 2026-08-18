#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tạo video quảng cáo UGREEN Nexode Robot Uno bằng OpenCV
"""

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import os

# Cấu hình
WIDTH = 1080
HEIGHT = 1920
FPS = 30
BG_COLOR = (250, 245, 245)  # BGR format

def add_text_to_frame(frame, text, y_position, font_scale=2.0, color=(0, 0, 0), thickness=3):
    """Thêm text vào frame với font unicode support"""
    # Convert frame to PIL Image for unicode support
    pil_img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(pil_img)
    
    try:
        font = ImageFont.truetype("arial.ttf", int(font_scale * 30))
    except:
        try:
            font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", int(font_scale * 30))
        except:
            font = ImageFont.load_default()
    
    # Get text bbox and draw centered
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    
    x = (WIDTH - text_width) // 2
    
    draw.text((x, y_position), text, font=font, fill=color)
    
    return cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)

def create_scene(image_path, duration_sec, title, caption):
    """Tạo scene từ ảnh"""
    frames = []
    total_frames = int(duration_sec * FPS)
    
    # Load ảnh
    img = cv2.imread(image_path)
    if img is None:
        print(f"Không load được: {image_path}")
        return frames
    
    # Resize ảnh giữ tỷ lệ
    h, w = img.shape[:2]
    target_h = int(HEIGHT * 0.55)
    scale = target_h / h
    new_w = int(w * scale)
    new_h = target_h
    
    if new_w > WIDTH - 100:
        new_w = WIDTH - 100
        scale = new_w / w
        new_h = int(h * scale)
    
    img_resized = cv2.resize(img, (new_w, new_h))
    
    # Tạo frames
    for i in range(total_frames):
        # Background
        frame = np.full((HEIGHT, WIDTH, 3), BG_COLOR, dtype=np.uint8)
        
        # Đặt ảnh vào giữa
        y_offset = 400
        x_offset = (WIDTH - new_w) // 2
        frame[y_offset:y_offset+new_h, x_offset:x_offset+new_w] = img_resized
        
        # Thêm title (trên)
        frame = add_text_to_frame(frame, title, 150, font_scale=2.2, thickness=4)
        
        # Thêm caption (dưới)
        frame = add_text_to_frame(frame, caption, HEIGHT - 350, 
                                 font_scale=1.4, color=(50, 50, 50), thickness=2)
        
        frames.append(frame)
    
    return frames

def main():
    print("🎬 Bắt đầu tạo video UGREEN Nexode Robot Uno...")
    
    output_path = 'C:/Users/ninak/Downloads/sac-ugreen/ugreen_review_30s.mp4'
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(output_path, fourcc, FPS, (WIDTH, HEIGHT))
    
    scenes_config = [
        {
            'image': 'assets/ugreen-nexode-robot-uno/sg-11134201-7rbm5-m62nvl361r4n2c.png',
            'duration': 5,
            'title': 'UGREEN Nexode Robot Uno',
            'caption': 'Nguoi ban sac dang yeu nhat!'
        },
        {
            'image': 'assets/ugreen-nexode-robot-uno/vn-11134201-81ztc-mrffmjlnrabp6b.png',
            'duration': 5,
            'title': 'Thiet ke Robot Dang Yeu',
            'caption': 'LED face thong minh | Nho gon 30% nho GaN'
        },
        {
            'image': 'assets/ugreen-nexode-robot-uno/sg-11134201-7rbm9-m62nviffzac796.png',
            'duration': 8,
            'title': '30W Sac Sieu Nhanh',
            'caption': 'iPhone 16: 0-50% chi 30 phut | PD 3.0'
        },
        {
            'image': 'assets/ugreen-nexode-robot-uno/vn-11134103-81ztc-mlftjsv7bklkcc.png',
            'duration': 7,
            'title': '100% An Toan',
            'caption': 'Chong qua nhiet | Qua ap | Ngan mach'
        },
        {
            'image': 'assets/ugreen-nexode-robot-uno/sg-11134201-7rbnf-m62nvjqm29j4f6.png',
            'duration': 5,
            'title': 'UGREEN - Sac Thong Minh',
            'caption': 'Mua ngay tai Shopee & The Gioi Di Dong!'
        }
    ]
    
    total_frames = 0
    for idx, scene in enumerate(scenes_config, 1):
        print(f"📹 Scene {idx}: {scene['title']}")
        frames = create_scene(
            scene['image'],
            scene['duration'],
            scene['title'],
            scene['caption']
        )
        
        for frame in frames:
            out.write(frame)
            total_frames += 1
    
    out.release()
    
    print(f"✅ Hoàn thành! Video đã lưu tại: {output_path}")
    print(f"⏱️  Tổng frames: {total_frames} ({total_frames/FPS:.1f}s)")
    print(f"📐 Kích thước: {WIDTH}x{HEIGHT} (9:16)")

if __name__ == '__main__':
    main()
