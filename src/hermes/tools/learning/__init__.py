# tools/learning — Phân tích video & trích xuất bài học
#
# Sub-package tổ chức các module liên quan đến:
#   - Phân tích video/ảnh bằng Gemini Vision (video_analyser)
#   - Trích xuất kiến thức vào Knowledge Store
#   - Phân tích phong cách nội dung (style_profiler)
#
# Re-export cho backward compatibility:
#   from hermes.tools.learning import analyze_video

from hermes.tools.video_analyser import (
    analyze_video,
    analyze_images,
    init_gemini,
    MediaAnalysisUnavailable,
)
from hermes.application.core.style_profiler import build_profile as build_style_profile

__all__ = [
    "analyze_video",
    "analyze_images",
    "init_gemini",
    "MediaAnalysisUnavailable",
    "build_style_profile",
]
