from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

SECRET_KEYWORDS = (
    "secret",
    "token",
    "password",
    "auth",
    "bearer",
    "api_key",
    "private_key",
)


@dataclass
class CapabilityError(Exception):
    code: str
    message: str
    retryable: bool
    capability_id: str
    actionable_recovery: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return f"CapabilityError[{self.code}]: {self.message} (capability={self.capability_id})"

    def to_dict(self) -> dict[str, Any]:
        cleaned_details = _sanitize_primitives(self.details)
        res: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
            "capability_id": self.capability_id,
            "details": cleaned_details,
        }
        if self.actionable_recovery is not None:
            res["actionable_recovery"] = self.actionable_recovery
        return res


def _sanitize_primitives(val: Any) -> Any:
    if isinstance(val, (str, int, float, bool, type(None))):
        if isinstance(val, str):
            lower_val = val.lower()
            if any(kw in lower_val for kw in SECRET_KEYWORDS):
                return "[REDACTED]"
        return val
    if isinstance(val, dict):
        res = {}
        for k, v in val.items():
            k_str = str(k)
            lower_k = k_str.lower()
            if any(kw in lower_k for kw in SECRET_KEYWORDS):
                res[k_str] = "[REDACTED]"
            else:
                res[k_str] = _sanitize_primitives(v)
        return res
    if isinstance(val, (list, tuple, set)):
        return [_sanitize_primitives(item) for item in val]
    return str(val)
