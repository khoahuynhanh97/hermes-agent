from __future__ import annotations

import re
from typing import Any

REDACTED_PLACEHOLDER = "[REDACTED]"

DEFAULT_SECRET_KEY_PATTERNS = (
    "authorization",
    "api_key",
    "apikey",
    "token",
    "cookie",
    "password",
    "secret",
    "private_key",
    "bearer",
    "credential",
)


def _is_secret_key(key: str, sensitive_keys: tuple[str, ...]) -> bool:
    normalized = key.lower().replace("-", "_")
    return any(pattern in normalized for pattern in sensitive_keys)


def redact(
    data: Any,
    sensitive_keys: tuple[str, ...] = DEFAULT_SECRET_KEY_PATTERNS,
) -> Any:
    """Recursively redact sensitive keys and values from dictionaries, lists, and structures."""
    if isinstance(data, dict):
        result: dict[str, Any] = {}
        for k, v in data.items():
            if isinstance(k, str) and _is_secret_key(k, sensitive_keys):
                result[k] = REDACTED_PLACEHOLDER
            else:
                result[k] = redact(v, sensitive_keys=sensitive_keys)
        return result

    if isinstance(data, list):
        return [redact(item, sensitive_keys=sensitive_keys) for item in data]

    if isinstance(data, tuple):
        return tuple(redact(item, sensitive_keys=sensitive_keys) for item in data)

    if isinstance(data, set):
        return {redact(item, sensitive_keys=sensitive_keys) for item in data}

    return data
