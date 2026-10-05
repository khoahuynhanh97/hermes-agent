"""Single resolver for the keyframe (image) provider.

Product Video keyframes are generated through Google Flow (Playwright). Vertex AI
is only used for keyframes when the operator explicitly opts in via
``video_factory.keyframe_provider: vertex_ai`` or enables
``video_factory.keyframe_fallback: vertex_ai``. There is no silent fallback.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from hermes_personal.integrations.video_factory.ports import KeyframeGenerationPort

_FLOW = "google_flow"
_VERTEX = "vertex_ai"


class KeyframeProviderUnavailable(RuntimeError):
    """Configured keyframe provider cannot run and no fallback is enabled."""


def _video_factory_config() -> dict[str, Any]:
    from hermes_cli.config import load_config

    cfg = load_config()
    vf_cfg = cfg.get("video_factory", {}) if isinstance(cfg, dict) else {}
    return vf_cfg if isinstance(vf_cfg, dict) else {}


def resolve_keyframe_provider(output_dir: Path | str) -> tuple[KeyframeGenerationPort, str]:
    """Return ``(provider, capacity_kind)`` according to ``video_factory`` config."""
    from hermes_personal.integrations.video_factory.google_flow_keyframe_provider import (
        GoogleFlowKeyframeProvider,
    )
    from hermes_personal.integrations.video_factory.keyframe_provider import VertexKeyframeProvider

    vf_cfg = _video_factory_config()
    preferred = str(vf_cfg.get("keyframe_provider", _FLOW)).strip().lower()
    fallback = str(vf_cfg.get("keyframe_fallback", "")).strip().lower()
    if preferred not in {_FLOW, _VERTEX}:
        raise KeyframeProviderUnavailable(
            f"video_factory.keyframe_provider must be '{_FLOW}' or '{_VERTEX}', got {preferred!r}"
        )

    if preferred == _VERTEX:
        return VertexKeyframeProvider(output_dir=output_dir), "vertex_keyframe"

    flow = GoogleFlowKeyframeProvider.from_config(output_dir=output_dir)
    if flow.is_available():
        return flow, _FLOW
    if fallback == _VERTEX:
        return VertexKeyframeProvider(output_dir=output_dir), "vertex_keyframe"
    raise KeyframeProviderUnavailable(
        "Google Flow keyframe session is unavailable (profile missing or not logged in). "
        "Log in to the Google Flow profile, or set video_factory.keyframe_fallback: vertex_ai."
    )
