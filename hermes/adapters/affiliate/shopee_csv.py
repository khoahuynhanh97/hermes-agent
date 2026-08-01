from __future__ import annotations

import csv
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from hermes.domain.affiliate_research import ProductCandidate


@dataclass(frozen=True)
class ImportRowError:
    row_number: int
    message: str


@dataclass(frozen=True)
class ImportBatch:
    candidates: list[ProductCandidate]
    errors: list[ImportRowError]


class ShopeeAffiliateCsvSource:
    """Parses a user-authorized Shopee affiliate export without network access."""

    MAX_FILE_BYTES = 10 * 1024 * 1024
    MAX_ROWS = 5_000
    _ALIASES = {
        "external_product_id": ("item_id", "product_id", "id"),
        "name": ("product_name", "name", "item_name"),
        "category": ("category", "category_name"),
        "price_vnd": ("price", "price_vnd", "product_price"),
        "sold_count": ("sold", "sold_count", "sales"),
        "rating": ("rating", "product_rating"),
        "review_count": ("review_count", "reviews", "rating_count"),
        "commission_rate": ("commission", "commission_rate", "commission_percent"),
        "shop_name": ("shop_name", "shop", "seller_name"),
        "product_url": ("product_link", "product_url", "url", "link"),
        "image_urls": ("image", "image_url", "images"),
        "visual_signals": ("visual_signals", "visual_signal"),
    }

    def __init__(self, path: str | Path, authorization_scope: str = "user_export"):
        self._path = Path(path)
        self._authorization_scope = authorization_scope

    def load(self, owner_user_id: str) -> list[ProductCandidate]:
        return self.load_batch(owner_user_id).candidates

    def load_batch(self, owner_user_id: str) -> ImportBatch:
        if self._path.stat().st_size > self.MAX_FILE_BYTES:
            raise ValueError(f"CSV exceeds the {self.MAX_FILE_BYTES // (1024 * 1024)} MB file limit")

        candidates: list[ProductCandidate] = []
        errors: list[ImportRowError] = []
        with self._path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            for row_number, raw_row in enumerate(reader, start=2):
                if row_number - 1 > self.MAX_ROWS:
                    raise ValueError(f"CSV exceeds the {self.MAX_ROWS} row limit")
                try:
                    candidates.append(self._candidate_from_row(raw_row, owner_user_id))
                except ValueError as error:
                    errors.append(ImportRowError(row_number, str(error)))
        return ImportBatch(candidates, errors)

    def _candidate_from_row(self, row: dict[str | None, str | None], owner_user_id: str) -> ProductCandidate:
        values = {self._normalize_header(key): (value or "").strip() for key, value in row.items() if key}
        external_product_id = self._required(values, "external_product_id")
        name = self._required(values, "name")
        category = self._required(values, "category")
        price_vnd = self._parse_money(self._required(values, "price_vnd"))
        product_url = self._required(values, "product_url")
        candidate_values: dict[str, Any] = {
            "owner_user_id": owner_user_id,
            "platform": "shopee",
            "external_product_id": external_product_id,
            "name": name,
            "category": category,
            "price_vnd": price_vnd,
            "sold_count": self._parse_sold(self._value(values, "sold_count")),
            "rating": self._parse_rating(self._value(values, "rating")),
            "review_count": self._parse_nonnegative_integer(
                self._value(values, "review_count")
            ),
            "commission_rate": self._parse_percentage(self._value(values, "commission_rate")),
            "shop_name": self._value(values, "shop_name"),
            "product_url": product_url,
            "image_urls": self._split_values(self._value(values, "image_urls")),
            "visual_signals": self._split_values(self._value(values, "visual_signals")),
            "source_type": "shopee_affiliate_csv",
            "source_url": f"authorized_csv:{self._path.name}",
            "authorization_scope": self._authorization_scope,
            "rights_status": "authorized_affiliate_export",
        }
        candidate_values["content_hash"] = self._content_hash(candidate_values)
        return ProductCandidate(**candidate_values)

    def _value(self, values: dict[str, str], field: str) -> str:
        return next((values[alias] for alias in self._ALIASES[field] if values.get(alias)), "")

    def _required(self, values: dict[str, str], field: str) -> str:
        value = self._value(values, field)
        if not value:
            raise ValueError(f"missing required field: {field}")
        return value

    @staticmethod
    def _normalize_header(header: str) -> str:
        return header.strip().lower().replace(" ", "_").replace("-", "_")

    @staticmethod
    def _parse_money(value: str) -> int:
        match = re.fullmatch(
            r"\s*(?P<amount>\d{1,3}(?:[.,]\d{3})+|\d+)\s*(?:[^\d\s]+)?\s*",
            value,
        )
        if match is None:
            raise ValueError("price must be exactly one VND money token")
        return int(match.group("amount").replace(".", "").replace(",", ""))

    @staticmethod
    def _parse_sold(value: str) -> int | None:
        if not value:
            return None
        normalized = value.strip().lower().replace(" ", "")
        if normalized.endswith("k"):
            number = normalized[:-1].replace(",", ".")
            if re.fullmatch(r"\d+(?:\.\d+)?", number) is None:
                raise ValueError(f"invalid integer: {value}")
            return round(float(number) * 1_000)
        return ShopeeAffiliateCsvSource._parse_nonnegative_integer(normalized)

    @staticmethod
    def _parse_integer(value: str) -> int | None:
        if not value:
            return None
        normalized = value.strip()
        if re.fullmatch(r"\d+", normalized) is None:
            raise ValueError(f"invalid integer: {value}")
        return int(normalized)

    @staticmethod
    def _parse_nonnegative_integer(value: str) -> int | None:
        return ShopeeAffiliateCsvSource._parse_integer(value)

    @staticmethod
    def _parse_float(value: str) -> float | None:
        if not value:
            return None
        try:
            return float(value.replace(",", "."))
        except ValueError as error:
            raise ValueError(f"invalid number: {value}") from error

    @staticmethod
    def _parse_rating(value: str) -> float | None:
        rating = ShopeeAffiliateCsvSource._parse_float(value)
        if rating is not None and not 0 <= rating <= 5:
            raise ValueError("rating must be between 0 and 5")
        return rating

    @staticmethod
    def _parse_percentage(value: str) -> float | None:
        if not value:
            return None
        normalized = value.strip().replace("%", "").replace(",", ".")
        try:
            rate = float(normalized)
        except ValueError as error:
            raise ValueError(f"invalid commission rate: {value}") from error
        parsed = rate / 100 if rate > 1 or "%" in value else rate
        if not 0 <= parsed <= 1:
            raise ValueError("commission rate must be between 0 and 1")
        return parsed

    @staticmethod
    def _split_values(value: str) -> tuple[str, ...]:
        return tuple(part.strip() for part in re.split(r"[|;]", value) if part.strip())

    @staticmethod
    def _content_hash(values: dict[str, Any]) -> str:
        canonical = json.dumps(values, ensure_ascii=True, sort_keys=True, separators=(",", ":"), default=list)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
