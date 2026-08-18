"""Product-to-Video Workflow Tool registered in Hermes Tool Registry."""
from __future__ import annotations

import json
import logging
from typing import Any, Dict

from hermes.tools.registry import registry, tool_error
from hermes.config import get_data_path

logger = logging.getLogger(__name__)

PRODUCT_TO_VIDEO_SCHEMA = {
    "name": "product_to_video",
    "description": "Create a complete marketing / review video (storyboard, voiceover audio, vertical 9:16 video render, and timeline) for a product from authentic Product Intelligence resources. Supports both synchronous execution and non-blocking asynchronous dispatch returning a job_id and queued status immediately.",
    "parameters": {
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": "Natural language request or prompt describing the desired video",
            },
            "product_query": {
                "type": "string",
                "description": "Product ID, brand, model, or product search query (optional)",
            },
            "duration_seconds": {
                "type": "integer",
                "description": "Target video duration in seconds (default: 30)",
                "default": 30,
            },
            "platform": {
                "type": "string",
                "description": "Target social video platform (e.g. TikTok, Shorts, Reels)",
                "default": "TikTok",
            },
            "language": {
                "type": "string",
                "description": "Voiceover language (default: Vietnamese)",
                "default": "Vietnamese",
            },
            "owner_user_id": {
                "type": "string",
                "description": "Owner user identifier",
                "default": "user",
            },
            "async_dispatch": {
                "type": "boolean",
                "description": "If true, queues the long-running video workflow in CanonicalJobWorker and returns job_id and queued status immediately without blocking.",
                "default": False,
            },
        },
        "required": ["prompt"],
    },
}


def _handle_product_to_video(args: dict | str = None, **kwargs) -> Dict[str, Any]:
    """Execute or dispatch product-to-video workflow through Hermes application engine."""
    from hermes.application.workflow import WorkflowOrchestrator

    if isinstance(args, str):
        params = {"prompt": args, **kwargs}
    elif isinstance(args, dict):
        params = {**args, **kwargs}
    else:
        params = dict(kwargs)

    prompt = params.get("prompt", "")
    product_query = params.get("product_query")
    duration_seconds = int(params.get("duration_seconds", 30))
    platform = params.get("platform", "TikTok")
    language = params.get("language", "Vietnamese")
    owner_user_id = params.get("owner_user_id", "user")
    async_dispatch = bool(
        params.get("async_dispatch", False)
        or params.get("async_mode", False)
        or params.get("non_blocking", False)
    )

    try:
        db_path = get_data_path("db", "video_factory.sqlite")
        orchestrator = WorkflowOrchestrator(db_path)
        result = orchestrator.run_product_to_video_workflow(
            owner_user_id=owner_user_id,
            prompt=prompt,
            product_query=product_query,
            duration_seconds=duration_seconds,
            platform=platform,
            language=language,
            async_dispatch=async_dispatch,
        )
        return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as err:
        logger.exception("product_to_video execution failed")
        return tool_error(f"Product-to-Video Workflow failed: {err}")


def check_product_to_video_requirements() -> tuple[bool, str]:
    return True, ""


registry.register(
    name="product_to_video",
    toolset="video_factory",
    schema=PRODUCT_TO_VIDEO_SCHEMA,
    handler=_handle_product_to_video,
    check_fn=check_product_to_video_requirements,
    requires_env=[],
    is_async=False,
    emoji="🎥",
)
