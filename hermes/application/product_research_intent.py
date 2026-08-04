from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass


_PRICE_RANGE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(k|tr|triệu|m)?\s*[-–]\s*(\d+(?:[.,]\d+)?)\s*(k|tr|triệu|m)?", re.I)
_CATEGORY = re.compile(r"(?:ngành|nganh|category|sản phẩm|san pham)\s+([^,;.]+)", re.I)
_KNOWN_CATEGORIES = ("bàn phím", "ban phim", "keyboard", "chuột", "mouse", "hub", "đèn", "den", "tai nghe")


@dataclass(frozen=True)
class ProductResearchIntent:
    owner_user_id: str
    raw_message: str
    category: str
    keyword: str
    min_price_vnd: int
    max_price_vnd: int
    source_preference: str = "crawler_first"
    script_limit: int = 5
    idempotency_key: str = ""

    @classmethod
    def from_message(cls, owner_user_id: str, message: str) -> "ProductResearchIntent":
        owner = str(owner_user_id).strip()
        text = (message or "").strip()
        if not owner:
            raise ValueError("owner_user_id is required")
        if not text:
            raise ValueError("message is required")
        category = _extract_category(text)
        min_price, max_price = _extract_price_range(text)
        payload_key = hashlib.sha256(
            f"{owner}\0{category}\0{min_price}\0{max_price}\0{text.casefold()}".encode("utf-8")
        ).hexdigest()[:16]
        return cls(
            owner_user_id=owner,
            raw_message=text,
            category=category,
            keyword=category,
            min_price_vnd=min_price,
            max_price_vnd=max_price,
            idempotency_key=f"product-research-script-{payload_key}",
        )

    def to_payload(self) -> dict[str, object]:
        return asdict(self)


def _extract_category(text: str) -> str:
    match = _CATEGORY.search(text)
    if match:
        value = match.group(1).strip().lower()
        value = re.split(r"\s+(?:giá|gia|price|xuất|xuat|rồi|roi)\b", value, maxsplit=1, flags=re.I)[0]
        return value.strip(" ,.;:") or "tech_product"
    lowered = text.casefold()
    for category in _KNOWN_CATEGORIES:
        if category in lowered:
            return category
    return "tech_product"


def _extract_price_range(text: str) -> tuple[int, int]:
    match = _PRICE_RANGE.search(text)
    if not match:
        return 200_000, 500_000
    low = _money_to_vnd(match.group(1), match.group(2))
    high = _money_to_vnd(match.group(3), match.group(4) or match.group(2))
    if low <= 0 or high <= 0 or low > high:
        raise ValueError("invalid price range")
    return low, high


def _money_to_vnd(number: str, unit: str | None) -> int:
    value = float(number.replace(",", "."))
    normalized = (unit or "").casefold()
    if normalized in {"k"}:
        value *= 1_000
    elif normalized in {"tr", "triệu", "m"}:
        value *= 1_000_000
    return int(value)