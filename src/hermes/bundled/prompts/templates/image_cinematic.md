---
id: image_cinematic
name: Cinematic commercial & lifestyle photo
type: image_prompt
description: Tạo prompt ảnh chụp thương mại hoặc lifestyle dạng điện ảnh (cinematic) chất lượng cao.
---

Create a photorealistic cinematic commercial lifestyle image.

Subject:
- Main subject/product: {{ subject }}
- Details/Action/Pose: {{ details_action }}

Environment & Setting:
- Background scene/Location: {{ environment }}
- Setting elements/Props: {{ setting_style }}

Composition & Camera:
- Camera shot type/Angle: {{ camera_angle }} (e.g., extreme close-up, low-angle hero shot, medium shot)
- Lens/Aperture/Camera model: {{ lens }} (e.g., 50mm f/1.2 lens, shallow depth of field, captured on Hasselblad)

Lighting & Mood:
- Lighting style/Direction: {{ lighting }} (e.g., soft morning sunlight filtering through, dramatic side-lighting, warm golden hour glow)
- Color grading/Atmosphere: {{ color_grading }} (e.g., warm cinematic color palette, teal and orange grading, soft misty atmosphere)

Negative Prompt Constraints:
- No text, no logos, no watermarks, no artificial oversaturation, no distorted details, no generic stock photo look.

Parameters:
- Aspect Ratio: {{ aspect_ratio }} (e.g., --ar 16:9, --ar 4:5, --ar 9:16)
- Midjourney settings: --style raw --v 6.0 --s 250
