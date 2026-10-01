"""Hermes Personal - Google Flow Playwright Video Generation Runner.

Executes end-to-end AI video scene generation on Google Flow via Playwright automation.
Strictly adheres to Grounded Fidelity Contract (No 2D fallback, authentic Playwright Flow submission).
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from hermes_personal.integrations.video_factory.google_flow_provider import (
    GoogleFlowPlaywrightProvider,
)
from hermes_personal.integrations.video_factory.ports import (
    VideoGenerationRequest,
    VideoGenerationResult,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("hermes.google_flow")

PRODUCTS = {
    "huawei": {
        "brand": "Huawei",
        "model": "GT 2 Pro",
        "display_name": "Đồng hồ thông minh HUAWEI WATCH GT 2 Pro",
        "reference_image": r"D:\work\Personal\hermes-product-video-exchange\inbox\2026-10-01\run_20261001_000031\products\huawei_gt-2-pro\images\image_3.png",
        "scenes": [
            {
                "scene_id": "scene_01",
                "duration": 6,
                "prompt": "A cinematic ultra-high-definition commercial shot of a luxury Huawei Watch GT 2 Pro smartwatch hovering in a dark minimalist studio. Dramatic soft silver rim lighting caresses the brushed matte titanium alloy casing and sparkles across the scratch-resistant sapphire crystal glass face. The AMOLED screen illuminates showing an elegant analog watch face with glowing complications. Shallow depth of field, f/2.8, pristine reflections, hyper-realistic metallic textures, 8k resolution, smooth fluid motion.",
            },
            {
                "scene_id": "scene_02",
                "duration": 6,
                "prompt": "Extreme macro cinematic close-up of the Huawei Watch GT 2 Pro smartwatch. Water droplets bead and slide smoothly off the glossy flat sapphire glass display and the precision-machined titanium bezels. Panning along the dual crown buttons on the right side. Glossy ceramic back plate visible with delicate optical heart-rate sensor glow. 4k 60fps slow-motion feel.",
            },
            {
                "scene_id": "scene_03",
                "duration": 6,
                "prompt": "A sleek Huawei Watch GT 2 Pro smartwatch landing softly onto a circular wireless charging pad on a dark wooden executive desk. The circular AMOLED screen displays a smooth glowing charge animation showing 14 days battery capacity icon. Soft ambient luxury room lighting, warm bokeh in the background.",
            },
        ],
    },
    "xiaomi": {
        "brand": "Xiaomi",
        "model": "Robot Vacuum E10",
        "display_name": "Robot hút bụi lau nhà thông minh Xiaomi Robot Vacuum E10",
        "reference_image": r"D:\work\Personal\hermes-product-video-exchange\inbox\2026-09-29\run_20260930_040252\products\xiaomi_robot-vacuum-e10\images\image_1.png",
        "scenes": [
            {
                "scene_id": "scene_01",
                "duration": 6,
                "prompt": "Cinematic low-angle tracking shot gliding backwards just above a polished bright oak wood floor in a sunlit modern apartment. A sleek pure white Xiaomi Robot Vacuum E10 glides forward with whisper-quiet precision, spinning side brush sweeping dust into its central suction port. Bright airy Scandinavian interior, warm morning sunlight.",
            },
            {
                "scene_id": "scene_02",
                "duration": 6,
                "prompt": "Close-up dynamic slow-motion angle of the Xiaomi Robot Vacuum E10 cleaning crumbs and pet hair off a soft grey rug. A semi-transparent glowing blue CGI airflow vortex demonstrates the powerful 4000Pa suction drawing deep dust from carpet fibers effortlessly.",
            },
        ],
    },
    "jbl": {
        "brand": "JBL",
        "model": "PartyBox 310",
        "display_name": "Loa Bluetooth di động công suất lớn JBL PartyBox 310",
        "reference_image": r"D:\work\Personal\hermes-product-video-exchange\inbox\2026-09-29\run_20260930_040252\products\jbl_partybox-310\images\image_1.jpg",
        "scenes": [
            {
                "scene_id": "scene_01",
                "duration": 6,
                "prompt": "High-energy cinematic music commercial shot of the rugged black JBL PartyBox 310 portable speaker in a dark rooftop club party. Dynamic fast zoom-in into the dual large speaker woofers vibrating intensely with powerful 240W bass drops. Colorful neon smoke, electric blue and magenta laser beams cutting through the haze.",
            },
            {
                "scene_id": "scene_02",
                "duration": 6,
                "prompt": "Close-up orbiting Dutch-angle shot focusing on the front metal mesh grille of the JBL PartyBox 310. The dual circular RGB LED infinity rings pulse, swirl, and flash in hypnotic synchronization with the thumping music rhythm. Rich deep contrast, glossy lens flares.",
            },
        ],
    },
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Hermes Google Flow Video Generator")
    parser.add_argument("--product", choices=list(PRODUCTS.keys()), default="huawei", help="Sản phẩm cần tạo video")
    parser.add_argument("--scene", type=int, default=1, help="Chỉ số scene (1-based)")
    parser.add_argument("--check-only", action="store_true", help="Chỉ kiểm tra kết nối Google Flow")
    args = parser.parse_args()

    output_dir = Path(r"D:\work\hermes-agent-data\workspaces\video-factory\flow_renders")
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Initializing GoogleFlowPlaywrightProvider...")
    provider = GoogleFlowPlaywrightProvider.from_config(output_dir=output_dir)

    is_ready = provider.is_available()
    logger.info(f"Google Flow Playwright Provider Ready: {is_ready}")

    if args.check_only:
        print(f"\n[GOOGLE FLOW STATUS] Khả dụng: {is_ready}")
        return 0 if is_ready else 1

    if not is_ready:
        logger.error("Google Flow provider is not available or unauthenticated.")
        return 1

    p_data = PRODUCTS[args.product]
    scene_idx = max(0, min(args.scene - 1, len(p_data["scenes"]) - 1))
    s_data = p_data["scenes"][scene_idx]

    logger.info(f"=== Bắt đầu tạo Scene qua Google Flow ===")
    logger.info(f"Sản phẩm: {p_data['brand']} {p_data['model']}")
    logger.info(f"Scene: {s_data['scene_id']} ({s_data['duration']}s)")
    logger.info(f"Reference Image: {p_data['reference_image']}")
    logger.info(f"Prompt: {s_data['prompt']}")

    request = VideoGenerationRequest(
        request_id=f"flow-req-{args.product}-{s_data['scene_id']}",
        owner_user_id="local-owner",
        project_id=f"proj-flow-{args.product}",
        scene_id=s_data["scene_id"],
        prompt=s_data["prompt"],
        duration_seconds=s_data["duration"],
        reference_image_paths=(p_data["reference_image"],),
        aspect_ratio="9:16",
    )

    logger.info("Submitting generation request to Google Flow UI...")
    res = provider.submit(request)
    logger.info(f"Result Status: {res.status}")
    if res.video_path:
        logger.info(f"Generated Video Saved: {res.video_path}")
    elif res.error_message:
        logger.error(f"Generation Error: {res.error_code} - {res.error_message}")

    return 0 if res.success else 1


if __name__ == "__main__":
    sys.exit(main())
