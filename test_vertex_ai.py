import os
try:
    from google.cloud import aiplatform
    from vertexai.preview.vision_models import ImageGenerationModel
    
    print("Thư viện: OK")
    # Kiểm tra project ID từ môi trường hoặc config
    project = os.getenv("GOOGLE_CLOUD_PROJECT")
    location = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
    
    if not project:
        print("Lỗi: Thiếu GOOGLE_CLOUD_PROJECT environment variable")
    else:
        aiplatform.init(project=project, location=location)
        print(f"Vertex AI khởi tạo thành công: Project={project}, Location={location}")
except ImportError as e:
    print(f"Lỗi Import: {e}")
except Exception as e:
    print(f"Lỗi: {e}")
