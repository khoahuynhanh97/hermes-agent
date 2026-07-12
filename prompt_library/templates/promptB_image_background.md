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
