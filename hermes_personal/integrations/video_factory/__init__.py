"""Video Factory edge capability MCP surface.

This module owns the canonical MCP server entry point for the Video Factory
edge. The deterministic client/contracts in this package remain the single
import target. ``src/hermes/**`` is the legacy prototype and is not the
canonical packaging boundary.
"""

from __future__ import annotations

from typing import Any

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:  # pragma: no cover - optional dependency boundary
    FastMCP = None  # type: ignore[misc,assignment]

from .client import VideoFactoryClient
from .contracts import (
    CreativeBriefRequest,
    ExportRequest,
    RenderRequest,
    ScenePlanRequest,
    StoryboardRequest,
)


def create_video_factory_mcp(client: VideoFactoryClient | None = None) -> Any:
    """Create the Video Factory MCP server when FastMCP is available."""
    if FastMCP is None:
        raise RuntimeError("FastMCP is not installed; cannot create Video Factory MCP server")

    effective_client = client or VideoFactoryClient()

    mcp = FastMCP("video_factory")

    @mcp.tool()
    def video_create_creative_brief(
        product_id: str = "",
        brief_config: dict | None = None,
    ) -> dict:
        """Create a deterministic creative brief request."""
        req = CreativeBriefRequest(product_id=product_id, brief_config=brief_config or {})
        return {
            "artifact_ref": effective_client._artifact.digest(),
            "payload": req.to_json(),
            "digest": req.digest(),
        }

    @mcp.tool()
    def video_create_scene_plan() -> dict:
        req = ScenePlanRequest()
        return {
            "artifact_ref": effective_client._artifact.digest(),
            "payload": req.to_json(),
            "digest": req.digest(),
        }

    @mcp.tool()
    def video_create_storyboard() -> dict:
        req = StoryboardRequest()
        return {
            "artifact_ref": effective_client._artifact.digest(),
            "payload": req.to_json(),
            "digest": req.digest(),
        }

    @mcp.tool()
    def video_render() -> dict:
        req = RenderRequest()
        return {
            "artifact_ref": effective_client._artifact.digest(),
            "payload": req.to_json(),
            "digest": req.digest(),
        }

    @mcp.tool()
    def video_export() -> dict:
        req = ExportRequest()
        return {
            "artifact_ref": effective_client._artifact.digest(),
            "payload": req.to_json(),
            "digest": req.digest(),
        }

    return mcp


__all__ = [
    "VideoFactoryClient",
    "CreativeBriefRequest",
    "ScenePlanRequest",
    "StoryboardRequest",
    "RenderRequest",
    "ExportRequest",
    "create_video_factory_mcp",
]
