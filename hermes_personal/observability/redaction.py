from __future__ import annotations

import re
from typing import Any, Pattern, Sequence

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


def _is_secret_key(key: str, sensitive_keys: Sequence[str]) -> bool:
    normalized = key.lower().replace("-", "_")
    return any(pattern in normalized for pattern in sensitive_keys)


def _matches_value_fingerprint(
    value: str,
    value_fingerprints: Sequence[str | Pattern[str]],
) -> bool:
    for fingerprint in value_fingerprints:
        if isinstance(fingerprint, str):
            if fingerprint and fingerprint in value:
                return True
        elif hasattr(fingerprint, "search"):
            if fingerprint.search(value):
                return True
    return False


def redact_string(
    value: str,
    value_fingerprints: Sequence[str | Pattern[str]] = (),
) -> str:
    """Mask a string value if it matches any configured value fingerprint."""
    if value_fingerprints and _matches_value_fingerprint(value, value_fingerprints):
        return REDACTED_PLACEHOLDER
    return value


CONFIGURED_VALUE_FINGERPRINTS: Sequence[str | Pattern[str]] = ()

def set_value_fingerprints(fingerprints: Sequence[str | Pattern[str]]) -> None:
    """Set global value fingerprints for redaction.
    Allows callers to configure redaction without passing fingerprints each time.
    """
    global CONFIGURED_VALUE_FINGERPRINTS
    CONFIGURED_VALUE_FINGERPRINTS = fingerprints

def redact(
    data: Any,
    sensitive_keys: Sequence[str] = DEFAULT_SECRET_KEY_PATTERNS,
    value_fingerprints: Sequence[str | Pattern[str]] = (),
) -> Any:
    """Recursively redact sensitive keys and configured value fingerprints from structures."""
    if isinstance(data, dict):
        result: dict[str, Any] = {}
        for k, v in data.items():
            if isinstance(k, str) and _is_secret_key(k, sensitive_keys):
                result[k] = REDACTED_PLACEHOLDER
            else:
                result[k] = redact(
                    v,
                    sensitive_keys=sensitive_keys,
                    value_fingerprints=value_fingerprints,
                )
        return result

    if isinstance(data, list):
        return [
            redact(item, sensitive_keys=sensitive_keys, value_fingerprints=value_fingerprints)
            for item in data
        ]

    if isinstance(data, tuple):
        return tuple(
            redact(item, sensitive_keys=sensitive_keys, value_fingerprints=value_fingerprints)
            for item in data
        )

    if isinstance(data, set):
        return {
            redact(item, sensitive_keys=sensitive_keys, value_fingerprints=value_fingerprints)
            for item in data
        }

    if isinstance(data, str):
        # Use provided fingerprints or fall back to globally configured ones
        effective_fps = value_fingerprints if value_fingerprints else CONFIGURED_VALUE_FINGERPRINTS
        return redact_string(data, value_fingerprints=effective_fps)

    return data
