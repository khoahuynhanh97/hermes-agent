"""Product-to-Video Workflow Tool registered in Hermes Tool Registry."""
from __future__ import annotations

import json
import logging
from typing import Any, Dict

from hermes.tools.registry import registry, tool_error
from hermes.config import get_data_path
from hermes.security.principal import current_principal

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
                "description": "Compatibility fallback outside authenticated channels. Authenticated principal always wins.",
                "default": "user",
            },
            "project_id": {
                "type": "string",
                "description": "Existing Video Factory project to continue after an explicit approval",
            },
            "run_id": {
                "type": "string",
                "description": "Existing workflow run associated with project_id",
            },
            "async_dispatch": {
                "type": "boolean",
                "description": "Legacy compatibility flag. User-governed agent calls remain synchronous until an approval-aware durable dispatcher is available.",
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
    principal = current_principal.get()
    owner_user_id = principal.owner_user_id if principal is not None else params.get("owner_user_id", "user")
    project_id = params.get("project_id") or None
    run_id = params.get("run_id") or None

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
            project_id=project_id,
            run_id=run_id,
            async_dispatch=False,
            approval_policy="require_user",
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
