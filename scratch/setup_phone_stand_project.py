import json
import os
import shutil
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from core.project_manager import ProjectManager


PRODUCT_NAME = "Giá đỡ điện thoại hình thú xinh đẹp"
SLUG = "gia-do-dien-thoai-hinh-thu-xinh-dep"
REFERENCE_IMAGE = (
    r"C:\Users\TeamSol\Downloads\TIKTOK\gia_do_dien_thoai"
    r"\vn-11134207-7r98o-lxjozr4aj9w9cd@resize_w450_nl.png"
)

DESCRIPTION = (
    "Giá đỡ điện thoại mini để bàn hình thú phong cách cute/kawaii, có các mẫu "
    "thỏ hồng, vịt vàng, gấu nâu; dùng để dựng điện thoại khi xem video, "
    "livestream, học online hoặc trang trí góc bàn."
)
SELLING_POINTS = (
    "Thiết kế hình thú dễ thương, màu pastel nổi bật, nhỏ gọn, để bàn tiện, "
    "vừa giữ điện thoại vừa làm đồ decor."
)
TARGET_AUDIENCE = (
    "Học sinh, sinh viên, dân văn phòng, người thích đồ cute, decor góc học tập/góc làm việc."
)
PAIN_POINTS = (
    "Cầm điện thoại lâu bị mỏi tay, để điện thoại trên bàn dễ trượt/ngã, "
    "góc bàn thiếu phụ kiện xinh để quay video hoặc học online."
)

KEYWORDS = {
    "manual": [
        "giá đỡ điện thoại hình thú",
        "kệ đỡ điện thoại cute",
        "giá đỡ điện thoại thỏ hồng",
        "giá đỡ điện thoại để bàn",
        "phụ kiện decor bàn học cute",
        "cute animal phone stand",
        "kawaii phone holder",
        "rabbit phone stand",
        "cartoon phone stand",
        "desktop phone holder",
        "phone stand for desk",
    ],
    "vi": [
        "giá đỡ điện thoại hình thú",
        "giá đỡ điện thoại cute",
        "kệ điện thoại để bàn",
        "phụ kiện bàn học dễ thương",
        "đồ decor bàn làm việc cute",
    ],
    "en": [
        "cute animal phone stand",
        "kawaii phone holder",
        "rabbit phone stand",
        "cartoon phone stand",
        "desktop phone holder",
    ],
    "zh": [
        "卡通手机支架",
        "可爱手机支架",
        "兔子手机支架",
        "桌面手机支架",
        "手机支架可爱",
    ],
}

VOICE_SCRIPT = """[gasp] Mấy dợ ơi... cái giá đỡ điện thoại hình thú này nhìn CƯNG XỈU luôn á.

[playful] Bình thường để điện thoại trên bàn là cứ trượt trượt, nghiêng nghiêng, nhìn hơi bực đúng không?

[amazed] Em này nhỏ gọn thôi, nhưng dựng điện thoại lên rất tiện, xem video, học online, livestream hay để cạnh laptop đều hợp.

[softly] Thiết kế thỏ hồng ôm củ cà rốt nhìn cute kiểu đồ decor bàn học Hàn Nhật, đặt lên góc bàn là sáng mood liền.

[happy] Vừa là giá đỡ điện thoại, vừa là món trang trí nhỏ xinh, mua một cái mà dùng được mỗi ngày.

[confident] Mấy ní thích góc bàn gọn hơn, xinh hơn, quay video cũng có vibe hơn thì bấm giỏ hàng xem mẫu nha.

[excited] Có mẫu cute thì dứt lẹ... Dứt!"""

CAPTION = (
    "Giá đỡ điện thoại hình thú cute cho góc bàn xinh hơn mỗi ngày. "
    "Vừa dựng điện thoại tiện, vừa decor bàn học/bàn làm việc rất yêu. "
    "Bấm giỏ hàng xem mẫu nha."
)
HASHTAGS = (
    "#giadodienthoai #giadodienthoaicute #decorbanhoc #phukiencute "
    "#dohoccuute #kawaiidesk #tiktokshop"
)


def main():
    pm = ProjectManager()
    project_dir = os.path.join(pm.get_projects_root(), SLUG)
    os.makedirs(project_dir, exist_ok=True)
    for subdir in ["Phoi", "clips", "audio", "scripts", "exports", "reference"]:
        os.makedirs(os.path.join(project_dir, subdir), exist_ok=True)

    meta = pm.get_metadata(SLUG) or {}
    meta.update(
        {
            "product_name": PRODUCT_NAME,
            "product_slug": SLUG,
            "description": DESCRIPTION,
            "price": "",
            "selling_points": SELLING_POINTS,
            "target_audience": TARGET_AUDIENCE,
            "pain_points": PAIN_POINTS,
            "keywords": KEYWORDS,
            "scripts": {
                "voice_script": VOICE_SCRIPT,
                "caption": CAPTION,
                "hashtags": HASHTAGS,
                "style": "TikTok affiliate cute review",
            },
            "content_angles": [
                "Góc bàn cute hơn chỉ với một món nhỏ",
                "Không cần cầm điện thoại khi xem video/học online",
                "Phụ kiện vừa tiện vừa decor",
                "Quà nhỏ xinh cho người thích đồ cute",
            ],
            "reference_image": (
                "reference/vn-11134207-7r98o-lxjozr4aj9w9cd@resize_w450_nl.png"
            ),
        }
    )
    meta.setdefault("audio", {})
    meta.setdefault("clips", [])
    meta.setdefault("exports", {})
    pm.save_metadata(SLUG, meta)

    if os.path.exists(REFERENCE_IMAGE):
        shutil.copy2(
            REFERENCE_IMAGE,
            os.path.join(project_dir, "reference", os.path.basename(REFERENCE_IMAGE)),
        )

    scripts_dir = os.path.join(project_dir, "scripts")
    files = {
        "voice_adam.txt": VOICE_SCRIPT,
        "caption_hashtags.txt": f"{CAPTION}\n\n{HASHTAGS}\n",
        "search_keywords.txt": "\n".join(KEYWORDS["manual"]) + "\n",
    }
    for filename, content in files.items():
        with open(os.path.join(scripts_dir, filename), "w", encoding="utf-8") as f:
            f.write(content)

    print(json.dumps({"project_dir": project_dir, "slug": SLUG}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
