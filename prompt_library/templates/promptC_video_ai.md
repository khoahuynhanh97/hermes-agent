---
id: promptC
name: Video AI TikTok 5-8s
type: video_prompt
description: Prompt mẫu tạo video AI ngắn cho TikTok/Reels/Shorts.
---

Create a short vertical TikTok product video.

Product:
- Product name: {{ product_name }}
- Product description: {{ product_description }}
- Main selling point: {{ selling_points }}
- Scene idea: {{ scene_idea }}

Video requirements:
- vertical 9:16 aspect ratio
- duration: {{ duration_seconds }} seconds
- realistic TikTok product review video style
- product-focused close-up
- natural hand movement if hands appear
- smooth slow camera panning
- clean commercial background
- high detail, realistic material, no exaggerated motion

Background/style:
{{ background_note }}

Action:
{{ action_note }}

Negative prompt:
no watermark, no logo, no distorted hands, no deformed product, no text artifacts, no blurry text, extra fingers, bad anatomy, deformed fingers, low quality, grainy
