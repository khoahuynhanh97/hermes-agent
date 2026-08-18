"""Brand safety filter — scans text for brand-unsafe language."""
from __future__ import annotations

import re
from typing import Any

# Default built-in rules (Vietnamese + English absolute claims)
_DEFAULT_RULES: list[dict[str, str]] = [
    {"pattern": r"cam\s*kết\s*100%", "label": "Absolute claim", "severity": "high"},
    {"pattern": r"trị\s*dứt\s*điểm", "label": "Medical claim", "severity": "high"},
    {"pattern": r"tuyệt\s*đối\s*không", "label": "Absolute claim", "severity": "medium"},
    {"pattern": r"không\s*bao\s*giờ", "label": "Absolute claim", "severity": "medium"},
    {"pattern": r"tốt\s*nhất", "label": "Superlative claim", "severity": "high"},
    {"pattern": r"xấu\s*nhất", "label": "Negative superlative", "severity": "medium"},
    {"pattern": r"guaranteed\s*100%", "label": "Absolute claim", "severity": "high"},
    {"pattern": r"cure[s]?\s*all", "label": "Medical claim", "severity": "high"},
    {"pattern": r"never\s*fails", "label": "Absolute claim", "severity": "high"},
    {"pattern": r"best\s*in\s*the\s*world", "label": "Superlative claim", "severity": "high"},
    {"pattern": r"100%\s*effective", "label": "Absolute claim", "severity": "high"},
]

_SUGGESTIONS: dict[str, str] = {
    "Absolute claim": "Hãy thay bằng cam kết cụ thể, ví dụ: 'hiệu quả cao' thay vì 'cam kết 100%'",
    "Medical claim": "Tránh claims y tế, thay bằng mô tả sản phẩm trung tính",
    "Superlative claim": "Giảm tính từ siêu cấp, dùng 'một trong những' thay vì 'nhất'",
    "Negative superlative": "Tránh ngôn ngữ tiêu cực cực đoan",
}


class BrandSafetyFilter:
    """Scans text content for brand-unsafe language."""

    def __init__(self, extra_rules: list[dict[str, str]] | None = None):
        self.rules = list(_DEFAULT_RULES)
        if extra_rules:
            self.rules.extend(extra_rules)

    def scan_text(self, text: str) -> dict[str, Any]:
        """Scan text for brand safety violations.

        Returns:
            {"passed": bool, "violations": list[dict]}
            Each violation: {"pattern": str, "match": str, "position": int,
                            "severity": str, "label": str}
        """
        violations: list[dict[str, Any]] = []
        for rule in self.rules:
            for m in re.finditer(rule["pattern"], text, re.IGNORECASE):
                violations.append({
                    "pattern": rule["pattern"],
                    "match": m.group(),
                    "position": m.start(),
                    "severity": rule["severity"],
                    "label": rule["label"],
                })
        violations.sort(key=lambda v: v["position"])
        return {"passed": len(violations) == 0, "violations": violations}

    def scan_voiceover_script(self, script: str) -> dict[str, Any]:
        """Scan voiceover text."""
        return self.scan_text(script)

    def scan_caption_text(self, captions: list[dict[str, Any]]) -> dict[str, Any]:
        """Scan caption/subtitle text.

        Each caption dict expected to have a 'text' key.
        """
        combined = " ".join(c.get("text", "") for c in captions)
        return self.scan_text(combined)

    def suggest_replacement(self, violation: dict[str, Any]) -> str:
        """Suggest a safer alternative for a violation."""
        label = violation.get("label", "")
        return _SUGGESTIONS.get(label, "Hãy xem xét lại câu wording để tránh claim tuyệt đối")
