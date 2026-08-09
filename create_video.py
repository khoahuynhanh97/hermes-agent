#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tạo video quảng cáo UGREEN Nexode Robot Uno từ ảnh sản phẩm
"""

from moviepy.editor import (
    ImageClip, TextClip, CompositeVideoClip, 
    concatenate_videoclips, ColorClip
)
from moviepy.video.fx import fadein, fadeout, resize
import os

# Cấu hình video
WIDTH = 1080
HEIGHT = 1920  # Format dọc cho social media (9:16)
FPS = 30
FONT = 'Arial-Bold'
BG_COLOR = (245, 245, 250)  # Màu nền sáng

def create_text_clip(text, duration, fontsize=60, color='white', 
                     position='center', bg_color=None):
    """Tạo text clip với background"""
    txt_clip = TextClip(
        text,
        fontsize=fontsize,
        color=color,
        font=FONT,
        method='caption',
        size=(WIDTH - 100, None),
        align='center'
    ).set_duration(duration).set_position(position)
    
    return txt_clip

def create_scene(image_path, duration, title, caption, animation='zoom'):
    """Tạo một scene từ ảnh với text overlay"""
    
    # Load và resize ảnh
    img_clip = ImageClip(image_path).set_duration(duration)
    
    # Resize ảnh để fit trong frame
    img_clip = img_clip.resize(height=HEIGHT*0.6)
    
    # Áp dụng animation
    if animation == 'zoom':
        img_clip = img_clip.resize(lambda t: 1 + 0.05 * t/duration)
    elif animation == 'fade':
        img_clip = fadein(img_clip, 0.5)
    
    img_clip = img_clip.set_position('center')
    
    # Background
    bg = ColorClip(size=(WIDTH, HEIGHT), color=BG_COLOR).set_duration(duration)
    
    # Title text
    title_clip = create_text_clip(
        title, 
        duration, 
        fontsize=70, 
        color='black',
        position=('center', 150)
    )
    
    # Caption text
    caption_clip = create_text_clip(
        caption,
        duration,
        fontsize=45,
        color='#333333',
        position=('center', HEIGHT - 250)
    )
    
    # Composite
    scene = CompositeVideoClip([bg, img_clip, title_clip, caption_clip])
    
    return scene

def main():
    print("🎬 Bắt đầu tạo video UGREEN Nexode Robot Uno...")
    
    scenes = []
    
    # Scene 1: Hero Shot (5s)
    print("📹 Scene 1: Hero Shot")
    scene1 = create_scene(
        'assets/ugreen-nexode-robot-uno/sg-11134201-7rbm5-m62nvl361r4n2c.png',
        5,
        'UGREEN Nexode Robot Uno',
        'Gặp gỡ người bạn sạc đáng yêu nhất! 🤖',
        'fade'
    )
    scenes.append(fadein(scene1, 0.5))
    
    # Scene 2: Thiết kế (5s)
    print("📹 Scene 2: Thiết kế độc đáo")
    scene2 = create_scene(
        'assets/ugreen-nexode-robot-uno/vn-11134201-81ztc-mrffmjlnrabp6b.png',
        5,
        '🤖 Thiết kế Robot Đáng Yêu',
        'LED face thông minh | Nhỏ gọn 30% nhờ GaN',
        'zoom'
    )
    scenes.append(scene2)
    
    # Scene 3: Sạc nhanh (8s)
    print("📹 Scene 3: Sạc siêu nhanh")
    scene3 = create_scene(
        'assets/ugreen-nexode-robot-uno/sg-11134201-7rbm9-m62nviffzac796.png',
        8,
        '⚡ 30W Sạc Siêu Nhanh',
        'iPhone 16: 0-50% chỉ 30 phút | PD 3.0',
        'zoom'
    )
    scenes.append(scene3)
    
    # Scene 4: An toàn (7s)
    print("📹 Scene 4: An toàn")
    scene4 = create_scene(
        'assets/ugreen-nexode-robot-uno/vn-11134103-81ztc-mlftjsv7bklkcc.png',
        7,
        '🛡️ 100% An Toàn',
        'Chống quá nhiệt | Quá áp | Ngắn mạch',
        'fade'
    )
    scenes.append(scene4)
    
    # Scene 5: CTA (5s)
    print("📹 Scene 5: Call to Action")
    scene5 = create_scene(
        'assets/ugreen-nexode-robot-uno/sg-11134201-7rbnf-m62nvjqm29j4f6.png',
        5,
        'UGREEN',
        'Mua ngay tại Shopee & Thế Giới Di Động! 🛒',
        'zoom'
    )
    scenes.append(fadeout(scene5, 0.5))
    
    # Ghép các scene lại
    print("🔗 Đang ghép các scene...")
    final_video = concatenate_videoclips(scenes, method='compose')
    
    # Export video
    output_path = 'C:/Users/ninak/Downloads/sac-ugreen/ugreen_nexode_robot_review_30s.mp4'
    print(f"💾 Đang xuất video: {output_path}")
    
    final_video.write_videofile(
        output_path,
        fps=FPS,
        codec='libx264',
        audio=False,
        preset='medium',
        threads=4
    )
    
    print(f"✅ Hoàn thành! Video đã được lưu tại: {output_path}")
    print(f"⏱️  Thời lượng: {final_video.duration}s")
    print(f"📐 Kích thước: {WIDTH}x{HEIGHT} (9:16)")

if __name__ == '__main__':
    main()
