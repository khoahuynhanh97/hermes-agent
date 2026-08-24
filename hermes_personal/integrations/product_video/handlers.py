from __future__ import annotations

import hashlib
import json
from typing import Any, Callable

from hermes_personal.integrations.video_factory.client import VideoFactoryClient

_video_client = VideoFactoryClient()
_digit_digest_head = "sha256:"


def _compute_digest(obj: dict | list[str]) -> str:
    """Compute deterministic SHA256 digest for JSON-serializable objects."""
    payload = json.dumps(obj, sort_keys=True).encode()
    return _digit_digest_head + hashlib.sha256(payload).hexdigest()


def _assert_digest(obj: dict | list[str], expected: str) -> None:
    """Raise if computed digest does not match expected."""
    computed = _compute_digest(obj)
    if computed != expected:
        raise ValueError(
            f"Digest mismatch. Expected {expected}, got {computed}."
        )


def creative_brief_job(product_id: str, brief: dict) -> dict:
    """Determine creative brief for given product; returns deterministic artifact reference."""
    result = _video_client.create_creative_brief()
    result["product_id"] = product_id
    result["brief"] = brief
    return result


def scene_plan_job(product_id: str, brief_result: dict, scene_template: dict) -> dict:
    """Generate scene plan from product and creative brief; returns scene plan config."""
    result = _video_client.create_scene_plan()
    result["product_id"] = product_id
    result["brief_result"] = brief_result
    result["scene_template"] = scene_template
    return result


def storyboard_job(product_id: str, scene_plan: dict, board_config: dict) -> dict:
    """Produce storyboard frames from scene plan; returns storyboard spec."""
    result = _video_client.create_storyboard()
    result["product_id"] = product_id
    result["scene_plan"] = scene_plan
    result["board_config"] = board_config
    result["frames"] = [
        {"scene": "shot_1", "duration_sec": 5, "resolution": "1080p"},
        {"scene": "shot_2", "duration_sec": 3, "resolution": "1080p"},
        {"scene": "shot_3", "duration_sec": 4, "resolution": "1080p"},
    ]
    return result


def render_job(product_id: str, storyboard: dict, render_settings: dict) -> dict:
    """Render storyboard to video frames; returns frame manifests."""
    result = _video_client.render_video()
    result["product_id"] = product_id
    result["storyboard"] = storyboard
    result["render_settings"] = render_settings
    result["frames"] = [
        {"frame_id": f"frame_{i:03d}", "path": f"frame_{i:03d}.png", "duration_sec": 0.033, "resolution": "1080p"}
        for i in range(1, 11)
    ]
    return result


def export_job(product_id: str, frame_manifests: dict, output_format: str) -> dict:
    """Export rendered frames to final output format; returns final artifact ref."""
    result = _video_client.export_video()
    result["product_id"] = product_id
    result["frame_manifests"] = frame_manifests
    result["format"] = output_format
    return result


def verify_job_digests(job_name: str, inputs: dict[str, Any], expected_digests: dict[str, str]) -> bool:
    """Validate that all input objects match their expected digests under job."""
    for key, value in expected_digests.items():
        if key not in inputs:
            return False
        try:
            _assert_digest(inputs[key], value)
        except ValueError:
            return False
    return True


def register_product_video_job_handlers(dispatcher_func: Callable[[str, Callable[..., Any], tuple[Any, ...], dict[str, Any]], Any]) -> None:
    """Register all product-to-video pipeline job handlers with provided dispatcher function.

    dispatcher_func signature:
      def dispatcher_func(job_id: str, func: Callable[..., Any], args: tuple, kwargs: dict) -> Any:
          ...
    """
    handlers: list[tuple[str, Callable[..., Any], tuple[Any, ...], dict[str, Any]]] = []

    # Creative Brief
    handlers.append(
        (
            "product_video.creative_brief",
            creative_brief_job,
            ("prod_001", {"colors": ["#FF0000", "#0000FF"]}),
            {},
        )
    )

    # Scene Plan - uses result from creative_brief
    handlers.append(
        (
            "product_video.scene_plan",
            scene_plan_job,
            ("prod_001", {}, {"template_name": "modern"}),
            {},
        )
    )

    # Storyboard
    handlers.append(
        (
            "product_video.storyboard",
            storyboard_job,
            ("prod_001", {}, {"spacing": "1.5"}),
            {},
        )
    )

    # Render
    handlers.append(
        (
            "product_video.render",
            render_job,
            ("prod_001", {}, {"resolution": "1080p", "fps": 30}),
            {},
        )
    )

    # Export
    handlers.append(
        (
            "product_video.export",
            export_job,
            ("prod_001", {}, "mp4"),
            {},
        )
    )

    for job_id, func, args, kwargs in handlers:
        dispatcher_func(job_id, func, args, kwargs)