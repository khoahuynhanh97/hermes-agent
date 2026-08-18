"""Small text LLM gateway for Hermes.

9Router is the primary text endpoint. The existing in-process provider
router remains an explicit compatibility fallback during migration.
"""

from __future__ import annotations

import logging
import os
import re
import time
from typing import Any

import requests

from hermes.runtime import config as _config  # Loads .env for scripts that import the gateway directly.

logger = logging.getLogger(__name__)


class LLMGatewayError(RuntimeError):
    """A normalized model-access failure."""


def complete(prompt: str, system: str = "", task_type: str = "chat", max_tokens: int = 4096) -> str:
    """Complete a text request through 9Router with controlled fallback."""
    if task_type in {"vision", "tool_call"}:
        raise LLMGatewayError(
            f"Task type '{task_type}' is not supported by the text gateway; use a verified capable adapter."
        )
    provider = os.environ.get("LLM_PROVIDER", "router").strip().lower()
    if provider == "legacy":
        return _legacy_complete(prompt, system, task_type)

    started = time.monotonic()
    primary_model = _model_for_task(task_type)
    candidate_models = [primary_model]

    last_error = None
    for model in candidate_models:
        try:
            text, actual_model, retry_count = _router_complete(prompt, system, task_type, max_tokens, target_model=model)
            logger.info(
                "[LLMGateway] provider=9router task=%s model=%s actual_model=%s duration_ms=%s retry_count=%s",
                task_type,
                model,
                actual_model or "unknown",
                int((time.monotonic() - started) * 1000),
                retry_count,
            )
            return text
        except Exception as exc:
            last_error = exc
            safe_error = _sanitize_error(str(exc))
            logger.warning(
                "[LLMGateway] 9Router model %s failed task=%s error=%s",
                model,
                task_type,
                safe_error,
            )

    safe_error = _sanitize_error(str(last_error))
    if not _env_bool("LLM_ENABLE_LEGACY_PROVIDER_FALLBACK", False):
        raise LLMGatewayError(f"9Router request failed: {safe_error}") from last_error
    logger.warning("[LLMGateway] Falling back to the existing local provider router.")
    return _legacy_complete(prompt, system, task_type)


def health_check() -> dict[str, Any]:
    """Probe 9Router health without exposing credentials or response bodies."""
    url = _router_root_url() + "/api/health"
    try:
        response = requests.get(url, headers=_headers(), timeout=_timeout())
        return {"ok": response.ok, "status_code": response.status_code, "url": url}
    except requests.RequestException as exc:
        return {"ok": False, "status_code": None, "url": url, "error": _sanitize_error(str(exc))}


def list_models() -> dict[str, Any]:
    """Return a redacted `/v1/models` probe result for diagnostics."""
    status_code = None
    try:
        response = requests.get(_router_url("/models"), headers=_headers(), timeout=_timeout())
        status_code = response.status_code
        response.raise_for_status()
        payload = response.json()
        models = payload.get("data", []) if isinstance(payload, dict) else []
        return {"ok": True, "status_code": response.status_code, "models": [
            item.get("id") for item in models if isinstance(item, dict) and item.get("id")
        ]}
    except Exception as exc:
        return {"ok": False, "status_code": status_code, "error": _sanitize_error(str(exc))}


def _router_complete(prompt: str, system: str, task_type: str, max_tokens: int, target_model: str | None = None) -> tuple[str, str | None, int]:
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    request = {
        "model": target_model or _model_for_task(task_type),
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": _temperature(),
        "stream": False,
    }
    retries = _retry_count()
    last_error = None
    for attempt in range(retries + 1):
        try:
            response = requests.post(
                _router_url("/chat/completions"),
                headers=_headers(),
                json=request,
                timeout=_timeout(),
            )
            if response.status_code >= 500 and attempt < retries:
                time.sleep(min(2.0, 0.25 * (attempt + 1)))
                continue
            if not response.ok:
                detail = ""
                try:
                    body = response.json()
                    detail = str(body.get("error", {}).get("message", "")) if isinstance(body, dict) else ""
                except (ValueError, AttributeError):
                    pass
                raise LLMGatewayError(detail or f"9Router HTTP {response.status_code}")
            data = response.json()
            break
        except LLMGatewayError:
            raise
        except requests.RequestException as exc:
            last_error = exc
            if attempt >= retries:
                raise
            time.sleep(min(2.0, 0.25 * (attempt + 1)))
    else:
        raise last_error or LLMGatewayError("9Router request failed")
    try:
        message = data["choices"][0]["message"]
        text = str(message.get("content") or "").strip()
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMGatewayError("9Router response has an invalid chat-completions shape") from exc
    if not text:
        raise LLMGatewayError("9Router response did not contain text content")
    return text, data.get("model") if isinstance(data, dict) else None, attempt


def _legacy_complete(prompt: str, system: str, task_type: str) -> str:
    from hermes.application.core.ai_router import chat as legacy_chat
    return legacy_chat(prompt, system=system, task_type=_legacy_task_type(task_type))


def _legacy_task_type(task_type: str) -> str:
    return {"chat": "default", "summarize": "analysis", "learning": "analysis", "deep_analysis": "analysis", "structured_extraction": "analysis", "code": "analysis"}.get(task_type, task_type or "default")


def _model_for_task(task_type: str) -> str:
    return "reason_combo"


def _router_url(path: str) -> str:
    return _configured_base_url().rstrip("/") + path


def _router_root_url() -> str:
    base = _configured_base_url().rstrip("/")
    return re.sub(r"/v1$", "", base)


def _configured_base_url() -> str:
    return (
        os.environ.get("LLM_BASE_URL", "").strip()
        or os.environ.get("LLM_ROUTER_BASE_URL", "").strip()
        or "http://127.0.0.1:20128/v1"
    )


def _headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    api_key = os.environ.get("LLM_ROUTER_API_KEY", "").strip()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _timeout() -> float:
    try:
        return max(1.0, float(os.environ.get("LLM_TIMEOUT_SECONDS", "120")))
    except ValueError:
        return 120.0


def _retry_count() -> int:
    try:
        return max(0, min(5, int(os.environ.get("LLM_RETRY_COUNT", "1"))))
    except ValueError:
        return 1


def _temperature() -> float:
    try:
        return max(0.0, min(2.0, float(os.environ.get("LLM_TEMPERATURE", "0.3"))))
    except ValueError:
        return 0.3


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _sanitize_error(message: str) -> str:
    if not message:
        return "Unknown error"
    return re.sub(r"([?&]key=)[^&]+", r"\1[REDACTED]", message)
