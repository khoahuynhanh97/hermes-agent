# tools/prompt — Tạo & quản lý Prompt
#
# Sub-package tổ chức các module liên quan đến:
#   - Tạo prompt từ storyboard (prompt_engine)
#   - Sinh keyword (keyword_generator)
#   - Quản lý prompt library
#
# Re-export cho backward compatibility:
#   from hermes.tools.prompt import generate_prompts_from_storyboard

from hermes.application.core.prompt_engine import generate_prompts_from_storyboard
from hermes.application.core.keyword_generator import (
    extract_keywords_from_product_page,
)

__all__ = [
    "generate_prompts_from_storyboard",
    "extract_keywords_from_product_page",
]
