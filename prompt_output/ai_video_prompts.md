# AI Video Generation Prompts

## Video AI TikTok 5-8s
**Type:** video_prompt  
**ID:** `promptC`  
**Source:** `f\prompt.chat\prompt_library\templates\promptC_video_ai.md`  

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


---

## Cinematic Drone & Landscape Video
**Type:** video_prompt  
**ID:** `video_drone_cinematic`  
**Source:** `f\prompt.chat\prompt_library\templates\video_drone_cinematic.md`  

---
id: video_drone_cinematic
name: Cinematic Drone & Landscape Video
type: video_prompt
description: Tạo prompt chuyển động flycam/drone hùng vĩ cho phong cảnh hoặc bất động sản.
---

Cinematic aerial drone footage, high-definition video.

Camera Movement & Shot Type:
- Shot type: {{ camera_shot }} (e.g., high-altitude drone flyover shot, epic crane shot descending, majestic wide sweeping shot)
- Camera trajectory: {{ camera_movement }} (e.g., slow forward glide, orbit rotation around the subject, smooth tracking shot following a road)

Subject & Scene:
- Location/Landscape: {{ location }} (e.g., towering snow-capped mountain range, ancient stone castle on a cliff edge, luxury modern villa overlooking the ocean)
- Active environmental elements: {{ dynamic_elements }} (e.g., misty clouds drifting slowly between peaks, gentle waves crashing on black sand, small waterfall cascading into a crystal stream)

Lighting & Atmosphere:
- Time of day/Lighting: {{ lighting }} (e.g., spectacular sunrise with golden light rays, moody twilight with low-angle fog, soft overcast daylight)
- Mood: {{ mood }} (e.g., awe-inspiring, peaceful, mysterious, grand scale)

Motion & Realism:
- Motion speed: {{ motion_speed }} (e.g., slow cinematic speed, majestic slow-motion, smooth natural physics flow)
- Visual quality: Photorealistic textures, high-fidelity rendering, realistic wind physics on trees and grass.

Negative Prompt Constraints:
- No fast jittery camera movements, no sudden zooms, no low-resolution textures, no watermarks, no distorted physics, no CGI flat look.

Parameters:
- Aspect Ratio: {{ aspect_ratio }} (e.g., 16:9 widescreen, 9:16 vertical)
- Duration: {{ duration_seconds }} seconds


---

## High-Speed Macro Slow-Motion Physics
**Type:** video_prompt  
**ID:** `video_macro_slowmotion`  
**Source:** `f\prompt.chat\prompt_library\templates\video_macro_slowmotion.md`  

---
id: video_macro_slowmotion
name: High-Speed Macro Slow-Motion Physics
type: video_prompt
description: Tạo prompt video AI mô phỏng hiện tượng vật lý góc siêu cận (macro) như té nước, tan chảy, khói lửa.
---

High-speed macro photography, ultra slow-motion footage.

Subject & Material:
- Main object/substance: {{ subject }} (e.g., a ripe strawberry, a glossy dark chocolate cube, a glowing amber bead)
- Physical state/material: {{ material_details }} (e.g., fresh glistening organic fruit skin, smooth liquid syrup texture, crystal clear glass reflection)

Macro Action & Physics:
- Kinetic event: {{ physics_action }} (e.g., dropping into milk, causing a gorgeous crown-shaped splash; melting slowly under intense heat; exploding into a cloud of colorful powder)
- Speed detail: {{ speed_details }} (e.g., recorded at 1000fps, suspended in time, fluid dynamics flowing in extreme slow motion)

Camera & Lighting:
- Shot framing: Extreme close-up macro shot, narrow depth of field, sharp focus on the impact point with background beautifully blurred.
- Lighting: {{ lighting }} (e.g., bright studio backlighting, high-contrast rim light, soft softbox lighting reflecting on the liquid surface)
- Background: {{ background_details }} (e.g., clean studio black background, soft pastel solid color, minimalist neutral gradient)

Negative Prompt Constraints:
- No blurry focus on the subject, no CGI look, no sudden frame jumps, no low framerate jitter, no watermarks, no messy background.

Parameters:
- Aspect Ratio: {{ aspect_ratio }} (e.g., 9:16 vertical, 16:9 widescreen)
- Duration: {{ duration_seconds }} seconds


---
