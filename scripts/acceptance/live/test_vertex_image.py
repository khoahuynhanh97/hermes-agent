import os
import vertexai
from vertexai.preview.vision_models import ImageGenerationModel

# Init
project = "gen-lang-client-0816609628"
location = "us-central1"
vertexai.init(project=project, location=location)

# Model
model = ImageGenerationModel.from_pretrained("imagen-3.0-generate-001")

# Prompt
prompt = "Professional product photography of a sleek Ugreen fast charger, minimalist background, high resolution, studio lighting, clean aesthetic."

# Generate
response = model.generate_images(
    prompt=prompt,
    number_of_images=1,
)

# Save
image_path = "ugreen_charger.png"
response.images[0].save(image_path)
print(f"Saved: {image_path}")
