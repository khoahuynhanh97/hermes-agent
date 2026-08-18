"""Shared Gemini/Vertex generateContent payload helpers.

Both the Developer API adapter and the Google Cloud (Vertex) adapter build the
same contents/generationConfig shape and parse the same response shape, so the
logic lives here instead of being duplicated.
"""

from __future__ import annotations

import ast
import base64
import json
from pathlib import Path
from typing import Any

from hermes.ports.image_generation import ImageGenerationRequest


SUPPORTED_ASPECT_RATIOS = {"1:1", "9:16", "16:9", "4:3", "3:4", "2:3", "3:2"}
MAX_REFERENCE_IMAGES = 4

_MIME_BY_EXT = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


def mime_for(path: Path) -> str:
    return _MIME_BY_EXT.get(path.suffix.lower(), "image/png")


def build_contents(request: ImageGenerationRequest) -> list[dict[str, Any]]:
    """contents parts: bounded reference images (inlineData) then the prompt.

    Gemini image models do not support negative-prompt semantics; appending
    "Avoid: ..." text can trigger the safety filter. The positive prompt is
    sent as-is.
    """
    parts: list[dict[str, Any]] = []
    ref_count = 0
    for ref in request.reference_image_paths:
        if ref_count >= MAX_REFERENCE_IMAGES:
            break
        path = Path(ref)
        if not path.is_file():
            continue
        mime = mime_for(path)
        data = base64.b64encode(path.read_bytes()).decode("ascii")
        parts.append({"inlineData": {"mimeType": mime, "data": data}})
        ref_count += 1

    parts.append({"text": request.positive_prompt})
    return [{"role": "user", "parts": parts}]


def generation_config(request: ImageGenerationRequest) -> dict[str, Any]:
    config: dict[str, Any] = {"responseModalities": ["TEXT", "IMAGE"]}
    if request.aspect_ratio in SUPPORTED_ASPECT_RATIOS:
        config["imageConfig"] = {"aspectRatio": request.aspect_ratio}
    provider_options = request.provider_options or {}
    for key in ("sampleCount", "temperature", "seed"):
        if key in provider_options:
            config[key] = provider_options[key]
    return config


def extract_image(body: dict) -> bytes | None:
    """Extract the first inline image from a generateContent response.

    Vertex may return inlineData either as a dict or as a JSON/repr string;
    both forms are handled.
    """
    try:
        candidates = body.get("candidates", [])
        for candidate in candidates:
            for part in candidate.get("content", {}).get("parts", []):
                inline = part.get("inlineData") or part.get("inline_data")
                if inline is None:
                    continue
                if isinstance(inline, str):
                    inline = _parse_inline_str(inline)
                if isinstance(inline, dict) and inline.get("data"):
                    return base64.b64decode(inline["data"])
    except (KeyError, TypeError, ValueError):
        return None
    return None


def _parse_inline_str(value: str) -> dict | None:
    """Parse an inlineData value that arrived as a JSON or repr string."""
    try:
        parsed = json.loads(value)
        if isinstance(parsed, dict):
            return parsed
    except (TypeError, ValueError):
        pass
    try:
        parsed = ast.literal_eval(value)
        if isinstance(parsed, dict):
            return parsed
    except (TypeError, ValueError, SyntaxError):
        pass
    return None


def output_path_for(output_dir: Path, request_id: str) -> Path:
    safe = "".join(c for c in request_id if c.isalnum() or c in "-_.") or "image"
    return output_dir / f"{safe}.png"
