# Image Generation Prompts (Background & Character)

## 3D Pixar/Disney Animated Character Style
**Type:** image_prompt  
**ID:** `image_3d_disney`  
**Source:** `f\prompt.chat\prompt_library\templates\image_3d_disney.md`  

---
id: image_3d_disney
name: 3D Pixar/Disney Animated Character Style
type: image_prompt
description: Tạo prompt hình ảnh nhân vật hoạt hình 3D phong cách Pixar hoặc Disney dễ thương.
---

A premium 3D digital render of an animated character, Pixar and Disney style.

Character Concept:
- Concept/Subject: {{ character_concept }} (e.g., a cute fluffy baby dragon, a cheerful young female scientist, a tiny robotic explorer)
- Facial Expression/Emotion: {{ facial_expression }} (e.g., wide-eyed curiosity, joyful bright smile, determined smirk)
- Key features/Pose: {{ pose_features }} (e.g., sitting on a pile of books, holding a glowing lantern, waving enthusiastically)

Clothing & Textures:
- Attire: {{ clothing_details }} (e.g., oversized knitted wool sweater, high-tech metallic astronaut suit, tiny leather goggles)
- Hair/Fur texture: {{ hair_fur_details }} (e.g., fluffy white soft fur, messy curly red hair with highly detailed strands)

Setting & Environment:
- Background scene: {{ environment }} (e.g., a magical glowing forest, a cozy workshop filled with gadgets, a clean pastel clay studio backdrop)
- Props: {{ props_details }} (e.g., colorful test tubes, glowing mushrooms, floating holographic screens)

Aesthetic & Lighting:
- Render style: {{ rendering_style }} (e.g., Octane Render, Raytraced, claymation feel, smooth clean subsurface scattering)
- Lighting: {{ lighting }} (e.g., rim lighting highlighting details, soft studio three-point lighting, glowing volumetric light sources)
- Color palette: {{ color_palette }} (e.g., vibrant pastel colors, warm cozy earth tones, neon accent lighting)

Negative Prompt Constraints:
- No realistic human photos, no scary/creepy eyes, no distorted limbs, no blurry textures, no low quality, no 2D flat drawings, no text.

Parameters:
- Aspect Ratio: {{ aspect_ratio }} (e.g., --ar 1:1, --ar 4:5, --ar 16:9)
- Midjourney settings: --v 6.0 --s 400 --niji 6 --style cute


---

## Cinematic commercial & lifestyle photo
**Type:** image_prompt  
**ID:** `image_cinematic`  
**Source:** `f\prompt.chat\prompt_library\templates\image_cinematic.md`  

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


---

## Premium Architectural & Interior Design Rendering
**Type:** image_prompt  
**ID:** `image_interior_arch`  
**Source:** `f\prompt.chat\prompt_library\templates\image_interior_arch.md`  

---
id: image_interior_arch
name: Premium Architectural & Interior Design Rendering
type: image_prompt
description: Tạo prompt dựng hình phối cảnh kiến trúc và thiết kế nội thất sang trọng.
---

An architectural and interior design visualization.

Space & Room Type:
- Type of space: {{ space_type }} (e.g., luxury minimalist living room, modern scandinavian kitchen, high-end hotel lobby)
- Spatial layout: {{ spatial_layout }} (e.g., open-concept layout, high ceilings with exposed wooden beams, double-height floor-to-ceiling windows)

Architectural Style & Design:
- Style: {{ design_style }} (e.g., Japandi, Mid-century modern, Industrial chic, Biophilic architecture)
- Key materials/Textures: {{ materials }} (e.g., polished concrete, brushed brass accents, matte white oak, raw travertine stone, bouclé fabric)

Environment & View:
- Outside view: {{ outdoor_view }} (e.g., lush green garden patio, towering pine forest, neon-lit cyberpunk city skyline at night)
- Internal decorations/Furniture: {{ furniture_details }} (e.g., low-profile linen sofa, minimalist marble coffee table, abstract sculpture, lush fiddle-leaf fig plant)

Lighting & Atmosphere:
- Lighting: {{ lighting }} (e.g., diffused afternoon sunlight, dramatic shadows, warm recessed LED lighting, soft ambient glow)
- Mood/Time of day: {{ mood }} (e.g., serene and calm, moody sunset, bright and airy morning)

Negative Prompt Constraints:
- No people, no low-quality renders, no distorted perspectives, no watermarks, no unrealistic lighting.

Parameters:
- Aspect Ratio: {{ aspect_ratio }} (e.g., --ar 16:9, --ar 4:3)
- Midjourney settings: --v 6.0 --s 300 --c 5


---

## Ảnh quảng cáo theo background/thành phần
**Type:** image_prompt  
**ID:** `promptB`  
**Source:** `f\prompt.chat\prompt_library\templates\promptB_image_background.md`  

---
id: promptB
name: Ảnh quảng cáo theo background/thành phần
type: image_prompt
description: Prompt mẫu để tạo ảnh TikTok 9:16 dựa theo background và ảnh thành phần.
---

Use case: ads-marketing.
Asset type: TikTok vertical product ad image, 9:16 portrait.

Primary request:
Create a photorealistic advertising image for the product below, using the provided background/reference style and component images.

Product:
- Product name: {{ product_name }}
- Product description: {{ product_description }}
- Main visual subject: {{ main_subject }}
- Required product color/material: {{ product_color_material }}

Background/reference:
- Background image/style note: {{ background_note }}
- Component images to preserve or echo: {{ component_note }}
- Desired mood: {{ mood }}

Composition:
- Place the product as the main focus in the lower-middle or lower-right third.
- Keep the product fully visible and realistic.
- Leave clean negative space for TikTok overlay text.
- Use vertical 9:16 portrait framing.

Lighting and style:
- Soft commercial product photography.
- Warm natural desk/studio lighting.
- Crisp product details, realistic shadows, premium but friendly e-commerce look.

Constraints:
- No text unless explicitly requested.
- No logo, no watermark, no brand marks.
- Do not distort the product.
- Do not add extra duplicate products.
- Keep hands natural if hands are included.
- Keep the background consistent with the reference style.

Final prompt should be copy-ready for an AI image generator.


---
