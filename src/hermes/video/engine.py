from .models import CreativeBrief, Scene, ScenePlan
from typing import List

class ScenePlanGenerator:
    """Generates a scene plan from a creative brief."""

    def generate(self, project_id: str, brief: CreativeBrief) -> ScenePlan:
        """
        Creates a structured ScenePlan based on the chosen angle.
        
        For now, this uses hardcoded templates. In the future, an LLM
        would generate these dynamically based on product info.
        """
        if brief.angle == "Problem-Agitate-Solve":
            scenes = self._generate_pas_scenes(brief)
        elif brief.angle == "Hook-Feature-Benefit":
            scenes = self._generate_hfb_scenes(brief)
        elif brief.angle == "Before-After":
            scenes = self._generate_ba_scenes(brief)
        else:
            raise ValueError(f"Unknown angle: {brief.angle}")
            
        return ScenePlan(project_id=project_id, brief=brief, scenes=scenes)

    def _generate_pas_scenes(self, brief: CreativeBrief) -> List[Scene]:
        return [
            Scene(scene_number=1, duration_seconds=4, visual_prompt=f"A person looking frustrated with a common problem related to {brief.product_sku}", voiceover_script=brief.key_hook, text_overlay="Gặp phải vấn đề này?"),
            Scene(scene_number=2, duration_seconds=6, visual_prompt=f"Close-up shots showing the negative effects of the problem, e.g., messy desk, slow device", voiceover_script="Nó không chỉ gây khó chịu, mà còn làm bạn mất thời gian và hiệu quả công việc.", text_overlay="Bực bội & Mất thời gian"),
            Scene(scene_number=3, duration_seconds=8, visual_prompt=f"Introducing the product {brief.product_sku} with clean, cinematic shots. Product being unboxed and used.", voiceover_script=f"Nhưng đừng lo, đã có {brief.product_sku}. Giải pháp tối ưu cho bạn.", text_overlay="Giải pháp là đây!"),
            Scene(scene_number=4, duration_seconds=8, visual_prompt=f"Dynamic shots of the product solving the problem effortlessly. Happy and satisfied user.", voiceover_script="Với thiết kế thông minh và hiệu năng vượt trội, mọi vấn đề sẽ được giải quyết trong tích tắc.", text_overlay="Hiệu quả & Nhanh chóng"),
            Scene(scene_number=5, duration_seconds=4, visual_prompt=f"Final shot of the product with packaging, logo, and a clear call to action on screen.", voiceover_script=brief.cta, text_overlay=brief.cta),
        ]

    def _generate_hfb_scenes(self, brief: CreativeBrief) -> List[Scene]:
        # Implementation for Hook-Feature-Benefit
        return [
            Scene(scene_number=1, duration_seconds=3, visual_prompt=f"An eye-catching, fast-paced visual related to {brief.product_sku}. {brief.key_hook}", voiceover_script=brief.key_hook, text_overlay=brief.key_hook),
            Scene(scene_number=2, duration_seconds=7, visual_prompt=f"Demonstrating the main feature of {brief.product_sku}. e.g., showing the fast charging port.", voiceover_script="Sản phẩm được trang bị tính năng X vượt trội.", text_overlay="Tính năng độc đáo"),
            Scene(scene_number=3, duration_seconds=7, visual_prompt=f"Showing the direct benefit of that feature. e.g., phone battery going from 10% to 50% quickly.", voiceover_script="Giúp bạn tiết kiệm hàng giờ đồng hồ mỗi ngày.", text_overlay="Tiết kiệm thời gian"),
            Scene(scene_number=4, duration_seconds=7, visual_prompt=f"Showcasing another key feature and its benefit.", voiceover_script="Không chỉ vậy, với thiết kế Y, bạn có thể dễ dàng mang theo mọi lúc mọi nơi.", text_overlay="Gọn nhẹ & Tiện lợi"),
            Scene(scene_number=5, duration_seconds=6, visual_prompt=f"Final beauty shot of the product with a clear call to action.", voiceover_script=brief.cta, text_overlay=brief.cta),
        ]

    def _generate_ba_scenes(self, brief: CreativeBrief) -> List[Scene]:
        # Implementation for Before-After
        return [
            Scene(scene_number=1, duration_seconds=6, visual_prompt=f"Split screen or quick cut showing a 'before' state: messy, slow, difficult.", voiceover_script="Bạn đã quá mệt mỏi với tình trạng này...", text_overlay="TRƯỚC KHI"),
            Scene(scene_number=2, duration_seconds=12, visual_prompt=f"A satisfying transition to the 'after' state, enabled by {brief.product_sku}. Clean, fast, easy.", voiceover_script=f"Hãy xem sự khác biệt khi có {brief.product_sku}!", text_overlay="SAU KHI"),
            Scene(scene_number=3, duration_seconds=8, visual_prompt=f"User enjoying the benefits in the 'after' state, looking relieved and happy.", voiceover_script="Trải nghiệm sự tiện lợi và hiệu quả chưa từng có.", text_overlay="Thật dễ dàng!"),
            Scene(scene_number=4, duration_seconds=4, visual_prompt=f"Product shot with call to action.", voiceover_script=brief.cta, text_overlay=brief.cta),
        ]
