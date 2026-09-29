"""Multimodal vision evaluator for Image and Video QC."""

from __future__ import annotations

import base64
import json
import logging
import mimetypes
import os
import re
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any

from agent.vertex_adapter import get_vertex_config
from hermes_personal.product_video.qc.models import QCStage

logger = logging.getLogger(__name__)


class QCResponseParseError(ValueError):
    """A fail-closed parse error with provider diagnostics safe to persist."""

    def __init__(self, raw_response: str, finish_reason: str | None, parse_error: str) -> None:
        self.raw_response = raw_response
        self.finish_reason = finish_reason
        self.parse_error = parse_error
        super().__init__(f"Could not parse JSON from model response: {parse_error}")


def validate_qc_response(raw: dict[str, Any], stage: QCStage) -> dict[str, Any]:
    """Validate and normalize the one response contract shared by image/video QC."""
    if not isinstance(raw, dict):
        raise ValueError("QC response must be a JSON object")

    components = {
        QCStage.IMAGE: {
            "identity_score": (0, 60),
            "clarity_score": (0, 25),
            "usability_score": (0, 15),
        },
        QCStage.VIDEO: {
            "identity_consistency": (0, 50),
            "scene_adherence": (0, 30),
            "visual_cleanliness": (0, 20),
        },
        QCStage.KEYFRAME: {
            "identity_consistency": (0, 50),
            "scene_adherence": (0, 30),
            "visual_cleanliness": (0, 20),
        },
    }[stage]
    required = (*components, "total_score", "verdict", "hard_failure", "reason")
    missing = [key for key in required if key not in raw]
    if missing:
        raise ValueError(f"QC response missing required fields: {', '.join(missing)}")

    normalized = dict(raw)
    for key, (lower, upper) in components.items():
        value = raw[key]
        if isinstance(value, bool) or not isinstance(value, int) or not lower <= value <= upper:
            raise ValueError(f"QC response field '{key}' must be an integer in [{lower}, {upper}]")

    total = raw["total_score"]
    if isinstance(total, bool) or not isinstance(total, int) or not 0 <= total <= 100:
        raise ValueError("QC response field 'total_score' must be an integer in [0, 100]")
    if sum(raw[key] for key in components) != total:
        raise ValueError("QC response total_score does not equal component sum")

    verdict = raw["verdict"]
    if verdict not in ("pass", "fail", "unknown"):
        raise ValueError("QC response verdict must be pass, fail, or unknown")
    if not isinstance(raw["hard_failure"], bool):
        raise ValueError("QC response hard_failure must be a boolean")
    if not isinstance(raw["reason"], str):
        raise ValueError("QC response reason must be a string")

    for key in ("source_branding_detected", "identity_mismatch"):
        if key in raw and not isinstance(raw[key], bool):
            raise ValueError(f"QC response field '{key}' must be a boolean")
        normalized[key] = bool(raw.get(key, False))

    if normalized["source_branding_detected"] or normalized["identity_mismatch"]:
        normalized["hard_failure"] = True
        normalized["verdict"] = "fail"

    if stage == QCStage.IMAGE:
        eligible = raw.get("eligible")
        if not isinstance(eligible, bool):
            raise ValueError("Image QC response eligible must be a boolean")
        normalized["eligible"] = (
            eligible
            and normalized["verdict"] == "pass"
            and total >= 80
            and not normalized["hard_failure"]
        )
        profile_fields = (
            "view_angle",
            "shot_type",
            "visible_details",
            "scene_suitability",
            "risk_flags",
            "text_coverage_percent",
        )
        missing_profile = [key for key in profile_fields if key not in raw]
        if missing_profile:
            raise ValueError(
                f"Image QC response missing required fields: {', '.join(missing_profile)}"
            )
        for key in ("view_angle", "shot_type"):
            value = raw[key]
            if not isinstance(value, str):
                raise ValueError(f"Image QC response field '{key}' must be a string")
            normalized[key] = value.strip()
        for key in ("visible_details", "scene_suitability", "risk_flags"):
            value = raw[key]
            if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
                raise ValueError(f"Image QC response field '{key}' must be a string list")
            normalized[key] = [item.strip() for item in value if item.strip()]
        if normalized["risk_flags"]:
            normalized["eligible"] = False
            normalized["verdict"] = "fail"
        text_coverage = raw["text_coverage_percent"]
        if isinstance(text_coverage, bool) or not isinstance(text_coverage, int) or not 0 <= text_coverage <= 100:
            raise ValueError("Image QC response text_coverage_percent must be an integer in [0, 100]")
        normalized["text_coverage_percent"] = text_coverage

    if stage == QCStage.KEYFRAME:
        gate_fields = (
            "prompt_reference_consistent",
            "important_details_preserved",
            "composition_usable",
            "animation_suitable",
        )
        missing_gates = [key for key in (*gate_fields, "recommended_action") if key not in raw]
        if missing_gates:
            raise ValueError(
                f"Keyframe QC response missing required fields: {', '.join(missing_gates)}"
            )
        for key in gate_fields:
            value = raw[key]
            if not isinstance(value, bool):
                raise ValueError(f"Keyframe QC response field '{key}' must be a boolean")
            normalized[key] = value
        action = raw.get("recommended_action")
        if action is None:
            action = "none"
        elif not isinstance(action, str):
            action = str(action)
        normalized["recommended_action"] = action.strip()
        if not all(
            normalized[key]
            for key in (
                "prompt_reference_consistent",
                "important_details_preserved",
                "composition_usable",
                "animation_suitable",
            )
        ):
            normalized["verdict"] = "fail"

    return normalized


def encode_image_to_base64(image_path: str | Path) -> tuple[str, str]:
    """Read image file and return (mime_type, base64_str)."""
    p = Path(image_path)
    if not p.is_file():
        raise FileNotFoundError(f"Image file not found: {image_path}")
    mime, _ = mimetypes.guess_type(str(p))
    if not mime:
        mime = "image/jpeg" if p.suffix.lower() in (".jpg", ".jpeg") else "image/png"
    data = p.read_bytes()
    b64 = base64.b64encode(data).decode("utf-8")
    return mime, b64


class MultimodalEvaluator:
    """Configured multimodal evaluator using Google Cloud Vertex AI Gemini."""

    def __init__(
        self,
        model: str = "google/gemini-2.5-flash",
        evaluator_name: str = "vertex_gemini_vision",
        evaluator_version: str = "1.0",
        timeout: float = 90.0,
        fake_mode: bool = False,
    ) -> None:
        self.model = model
        self.evaluator_name = evaluator_name
        self.evaluator_version = evaluator_version
        self.timeout = timeout
        self.fake_mode = fake_mode

    def evaluate_image(
        self,
        image_path: str | Path,
        prompt: str,
        system_instruction: str | None = None,
    ) -> dict[str, Any]:
        """Send image and prompt to multimodal model and return structured JSON."""
        if self.fake_mode:
            return {
                "verdict": "pass",
                "total_score": 90,
                "identity_score": 55,
                "clarity_score": 23,
                "usability_score": 12,
                "hard_failure": False,
                "source_branding_detected": False,
                "identity_mismatch": False,
                "eligible": True,
                "reason": "Offline test evaluation passed",
                "view_angle": "front three-quarter",
                "shot_type": "clean product reference",
                "visible_details": [],
                "scene_suitability": ["hero", "context"],
                "risk_flags": [],
                "text_coverage_percent": 0,
            }

        mime, b64 = encode_image_to_base64(image_path)
        token, base_url = get_vertex_config()
        if not token or not base_url:
            raise RuntimeError("Vertex AI credentials or base_url unavailable for MultimodalEvaluator")

        endpoint = f"{base_url}/chat/completions"
        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})

        messages.append({
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
            ],
        })

        body = {
            "model": self.model,
            "messages": messages,
            "max_tokens": 8192,
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }

        req = urllib.request.Request(
            endpoint,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}",
            },
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw_resp = json.loads(resp.read().decode("utf-8"))
            return self._parse_completion(raw_resp)
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="replace")
            logger.error("MultimodalEvaluator HTTP error %d: %s", exc.code, err_body)
            raise RuntimeError(f"MultimodalEvaluator HTTP {exc.code}: {err_body}") from exc
        except Exception as exc:
            logger.error("MultimodalEvaluator call failed: %s", exc)
            raise

    def evaluate_multiple_images(
        self,
        image_paths: list[str | Path],
        prompt: str,
        system_instruction: str | None = None,
    ) -> dict[str, Any]:
        """Send multiple images (e.g. reference vs video frames) and prompt to model."""
        if self.fake_mode:
            return {
                "verdict": "pass",
                "total_score": 88,
                "identity_consistency": 45,
                "scene_adherence": 26,
                "visual_cleanliness": 17,
                "hard_failure": False,
                "source_branding_detected": False,
                "identity_mismatch": False,
                "reason": "Offline multi-image test evaluation passed",
                "prompt_reference_consistent": True,
                "important_details_preserved": True,
                "composition_usable": True,
                "animation_suitable": True,
                "recommended_action": "none",
            }

        token, base_url = get_vertex_config()
        if not token or not base_url:
            raise RuntimeError("Vertex AI credentials or base_url unavailable for MultimodalEvaluator")

        endpoint = f"{base_url}/chat/completions"
        content_parts: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        for p in image_paths:
            mime, b64 = encode_image_to_base64(p)
            content_parts.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}})

        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": content_parts})

        body = {
            "model": self.model,
            "messages": messages,
            "max_tokens": 8192,
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }

        req = urllib.request.Request(
            endpoint,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}",
            },
        )

        for attempt in range(4):
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    raw_resp = json.loads(resp.read().decode("utf-8"))
                return self._parse_completion(raw_resp)
            except urllib.error.HTTPError as exc:
                if exc.code == 429 and attempt < 3:
                    import time
                    time.sleep(3.0 * (attempt + 1))
                    continue
                err_body = exc.read().decode("utf-8", errors="replace")
                logger.error("MultimodalEvaluator HTTP error %d: %s", exc.code, err_body)
                raise RuntimeError(f"MultimodalEvaluator HTTP {exc.code}: {err_body}") from exc
            except Exception as exc:
                logger.error("MultimodalEvaluator multi-image call failed: %s", exc)
                raise

    @classmethod
    def _parse_completion(cls, raw_response: dict[str, Any]) -> dict[str, Any]:
        """Extract the first completion while retaining finish metadata on failure."""
        try:
            choice = raw_response["choices"][0]
            finish_reason = choice.get("finish_reason")
            content = choice["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raw = json.dumps(raw_response, ensure_ascii=False, sort_keys=True)
            raise QCResponseParseError(raw, None, f"completion envelope is invalid: {exc}") from exc

        if isinstance(content, list):
            content = "".join(
                str(part.get("text", "")) if isinstance(part, dict) else str(part)
                for part in content
            )
        if not isinstance(content, str):
            raise QCResponseParseError(str(content), finish_reason, "completion content is not text")
        return cls._parse_json_response(content, finish_reason=finish_reason)

    @staticmethod
    def _parse_json_response(text: str, *, finish_reason: str | None = None) -> dict[str, Any]:
        """Extract and parse JSON from model output."""
        cleaned = text.strip()
        # strip markdown code fences if present
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()
        try:
            return json.loads(cleaned)
        except (TypeError, ValueError, json.JSONDecodeError) as first_error:
            # try to find first { and last }
            m = re.search(r"\{.*\}", cleaned, re.DOTALL)
            if m:
                try:
                    return json.loads(m.group(0))
                except (TypeError, ValueError, json.JSONDecodeError) as nested_error:
                    raise QCResponseParseError(text, finish_reason, str(nested_error)) from nested_error
            raise QCResponseParseError(text, finish_reason, str(first_error)) from first_error
