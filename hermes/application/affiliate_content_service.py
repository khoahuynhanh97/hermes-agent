from __future__ import annotations

import hashlib
import re
import uuid
from collections.abc import Mapping
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any, Sequence
from urllib.parse import urlparse

from hermes.domain.affiliate_research import (
    AffiliateProduct,
    ContentIdea,
    ContentPackage,
    PackageStatus,
    ReferenceMetadata,
)
from hermes.ports.affiliate_research import AffiliateResearchRepository


class ContentValidationError(ValueError):
    pass


_REQUIRED_TEXT_FIELDS = (
    "audience",
    "angle",
    "angle_reason",
    "hook",
    "script",
    "voiceover_plan",
)
_FIRST_HAND_PATTERNS = (
    "\\b(?:t\u00f4i|m\u00ecnh)\\s+(?:(?:\u0111\u00e3)\\s+)?(?:d\u00f9ng|th\u1eed|tr\u1ea3i\\s+nghi\u1ec7m|review|s\u1edf\\s+h\u1eefu)\\b",
    "\\bsau\\s+khi\\s+d\u00f9ng\\b",
    r"\bI\s+(?:tried|used|tested|own)\b",
    r"\bmy\s+(?:experience|review|desk)\b",
)
_TOKEN_PATTERN = re.compile(r"[\w]+", re.UNICODE)


class AffiliateContentService:
    def __init__(self, repository: AffiliateResearchRepository, gateway: Any):
        self._repository = repository
        self._gateway = gateway

    def create_packages(
        self,
        owner_user_id: str,
        run_id: str,
        products: Sequence[AffiliateProduct],
        references: Sequence[ReferenceMetadata] = (),
        *,
        per_run: int = 10,
    ) -> list[ContentPackage]:
        if not 5 <= per_run <= 10:
            raise ValueError("per_run must be between 5 and 10")
        selected = [product for product in products if product.owner_user_id == owner_user_id][:per_run]
        if len(selected) != min(len(products), per_run):
            raise ContentValidationError("products must belong to the package owner")
        for reference in references:
            if reference.owner_user_id != owner_user_id:
                raise ContentValidationError("reference must belong to the package owner")
            if reference.rights_status != "reference_only":
                raise ContentValidationError("reference rights must be reference_only")

        existing = self._repository.list_packages(owner_user_id)
        packages: list[ContentPackage] = []
        for product in selected:
            product_references = self._references_for_product(
                owner_user_id, product.id, references
            )
            self._repository.save_ideas(product.id, run_id, self._ideas_for(product, owner_user_id, run_id))
            package = self._package_from_payload(
                self._gateway.generate(product, product_references),
                owner_user_id=owner_user_id,
                run_id=run_id,
                product=product,
                references=product_references,
                revision=1,
                existing=existing + packages,
            )
            packages.append(self._repository.save_package(package))
        return packages

    def revise_package(
        self,
        package_id: str,
        owner_user_id: str,
        feedback: str,
    ) -> ContentPackage:
        if not feedback.strip():
            raise ContentValidationError("feedback is required")
        previous = self._repository.get_package(package_id, owner_user_id)
        if previous is None:
            raise LookupError(f"affiliate package not found: {package_id}")
        product = next(
            (
                item
                for item in self._repository.list_products(owner_user_id)
                if item.id == previous.product_id
            ),
            None,
        )
        if product is None:
            raise LookupError(f"affiliate product not found for package: {package_id}")
        payload = self._gateway.generate(
            product,
            (),
            previous_package=previous,
            feedback=feedback,
        )
        root_id = self._root_id(previous.id)
        revision_id = f"{root_id}:r{previous.revision + 1}"
        existing = self._repository.list_packages(owner_user_id)
        saved_revision = next((package for package in existing if package.id == revision_id), None)
        return self._repository.save_package(
            self._package_from_payload(
                payload,
                owner_user_id=owner_user_id,
                run_id=previous.run_id,
                product=product,
                references=(),
                revision=previous.revision + 1,
                existing=[
                    package
                    for package in existing
                    if package.id != revision_id
                ],
                asset_rights=previous.asset_rights,
                package_id=revision_id,
                created_at=saved_revision.created_at if saved_revision else None,
                updated_at=saved_revision.updated_at if saved_revision else None,
            )
        )

    @staticmethod
    def _ideas_for(product: AffiliateProduct, owner_user_id: str, run_id: str) -> list[ContentIdea]:
        now = datetime.now(timezone.utc).isoformat()
        angles = (
            ("office_worker", "Gon gàng góc làm việc", "Nhấn vào thay đổi bố cục có thể quan sát."),
            ("remote_worker", "Thao tác bàn làm việc", "Cho thấy một tình huống làm việc quen thuộc."),
            ("tech_shopper", "Chi tiết sản phẩm", "Dẫn từ hình ảnh sản phẩm sang thông tin có nguồn."),
        )
        return [
            ContentIdea(
                id=hashlib.sha256(f"{product.id}\0{run_id}\0{index}".encode("utf-8")).hexdigest(),
                owner_user_id=owner_user_id,
                product_id=product.id,
                run_id=run_id,
                audience=audience,
                angle=angle,
                rationale=rationale,
                created_at=now,
            )
            for index, (audience, angle, rationale) in enumerate(angles, start=1)
        ]

    @staticmethod
    def _references_for_product(
        owner_user_id: str,
        product_id: str,
        references: Sequence[ReferenceMetadata],
    ) -> tuple[ReferenceMetadata, ...]:
        selected = tuple(reference for reference in references if reference.product_id == product_id)
        return selected

    def _package_from_payload(
        self,
        payload: Mapping[str, Any],
        *,
        owner_user_id: str,
        run_id: str,
        product: AffiliateProduct,
        references: Sequence[ReferenceMetadata],
        revision: int,
        existing: Sequence[ContentPackage],
        asset_rights: dict[str, str] | None = None,
        package_id: str | None = None,
        created_at: str | None = None,
        updated_at: str | None = None,
    ) -> ContentPackage:
        self._validate_payload(payload)
        self._reject_first_hand_claims(payload)
        self._reject_duplicate_content(payload, existing)
        rights = asset_rights if asset_rights is not None else {
            product.id: product.rights_status,
            **{reference.id: "reference_only" for reference in references},
        }
        now = datetime.now(timezone.utc).isoformat()
        return ContentPackage(
            id=package_id or uuid.uuid4().hex,
            owner_user_id=owner_user_id,
            product_id=product.id,
            run_id=run_id,
            revision=revision,
            status=PackageStatus.PENDING_REVIEW,
            audience=payload["audience"].strip(),
            angle=payload["angle"].strip(),
            angle_reason=payload["angle_reason"].strip(),
            hook=payload["hook"].strip(),
            script=payload["script"].strip(),
            duration_seconds=payload["duration_seconds"],
            storyboard=tuple(dict(item) for item in payload["storyboard"]),
            ai_prompts=tuple(item.strip() for item in payload["ai_prompts"]),
            voiceover_plan=payload["voiceover_plan"].strip(),
            text_overlays=tuple(item.strip() for item in payload["text_overlays"]),
            claims=tuple(dict(item) for item in payload["claims"]),
            warnings=tuple(item.strip() for item in payload["warnings"]),
            asset_rights=dict(rights),
            created_at=created_at or now,
            updated_at=updated_at or now,
        )

    @staticmethod
    def _validate_payload(payload: Mapping[str, Any]) -> None:
        if not isinstance(payload, Mapping):
            raise ContentValidationError("content payload must be an object")
        for field in _REQUIRED_TEXT_FIELDS:
            if not isinstance(payload.get(field), str) or not payload[field].strip():
                raise ContentValidationError(f"{field} is required")
        duration = payload.get("duration_seconds")
        if isinstance(duration, bool) or not isinstance(duration, int) or not 30 <= duration <= 90:
            raise ContentValidationError("duration must be between 30 and 90 seconds")
        storyboard = payload.get("storyboard")
        if not isinstance(storyboard, list) or not storyboard:
            raise ContentValidationError("storyboard is required")
        previous_end = -1
        for item in storyboard:
            if not isinstance(item, Mapping) or not isinstance(item.get("visual"), str) or not item["visual"].strip():
                raise ContentValidationError("storyboard visual is required")
            start, end = item.get("start"), item.get("end")
            if any(isinstance(value, bool) or not isinstance(value, int) for value in (start, end)):
                raise ContentValidationError("storyboard timing must be integers")
            if start < previous_end or end <= start or end > duration:
                raise ContentValidationError("storyboard timing must be ordered within duration")
            previous_end = end
        for field in ("ai_prompts", "text_overlays", "warnings"):
            values = payload.get(field)
            if not isinstance(values, list) or any(not isinstance(item, str) or not item.strip() for item in values):
                if field == "warnings" and values == []:
                    continue
                raise ContentValidationError(f"{field} must contain text values")
            if field != "warnings" and not values:
                raise ContentValidationError(f"{field} is required")
        claims = payload.get("claims")
        if not isinstance(claims, list):
            raise ContentValidationError("claims must be a list")
        for claim in claims:
            if not isinstance(claim, Mapping) or not isinstance(claim.get("text"), str) or not claim["text"].strip():
                raise ContentValidationError("claim text is required")
            evidence_url = claim.get("evidence_url")
            parsed = urlparse(evidence_url) if isinstance(evidence_url, str) else None
            if not parsed or parsed.scheme != "https" or not parsed.netloc:
                raise ContentValidationError("every factual claim requires an HTTPS evidence URL")

    @staticmethod
    def _reject_first_hand_claims(payload: Mapping[str, Any]) -> None:
        text = AffiliateContentService._normalize_text(
            " ".join(AffiliateContentService._text_values(payload))
        )
        if any(re.search(pattern, text, re.IGNORECASE) for pattern in _FIRST_HAND_PATTERNS):
            raise ContentValidationError("first-hand product claims are not allowed")

    @staticmethod
    def _reject_duplicate_content(
        payload: Mapping[str, Any], existing: Sequence[ContentPackage]
    ) -> None:
        for candidate in (payload["hook"], payload["script"]):
            for package in existing:
                for stored in (package.hook, package.script):
                    if AffiliateContentService._is_high_overlap(candidate, stored):
                        raise ContentValidationError("duplicate or high-overlap content")

    @staticmethod
    def _is_high_overlap(left: str, right: str) -> bool:
        left_normalized = AffiliateContentService._normalize_text(left)
        right_normalized = AffiliateContentService._normalize_text(right)
        if left_normalized == right_normalized:
            return bool(left_normalized)
        left_tokens = _TOKEN_PATTERN.findall(left_normalized)
        right_tokens = _TOKEN_PATTERN.findall(right_normalized)
        if min(len(left_tokens), len(right_tokens)) < 5:
            return False
        if left_normalized in right_normalized or right_normalized in left_normalized:
            return True
        left_set, right_set = set(left_tokens), set(right_tokens)
        shared = len(left_set & right_set)
        containment = shared / min(len(left_set), len(right_set))
        jaccard = shared / len(left_set | right_set)
        sequence = SequenceMatcher(None, left_tokens, right_tokens).ratio()
        return containment >= 0.9 or (jaccard >= 0.8 and sequence >= 0.8)

    @staticmethod
    def _root_id(package_id: str) -> str:
        match = re.fullmatch(r"(.+):r[1-9][0-9]*", package_id)
        return match.group(1) if match else package_id

    @staticmethod
    def _normalize_text(value: str) -> str:
        return re.sub(r"\s+", " ", value).strip().lower()

    @staticmethod
    def _text_values(value: Any) -> list[str]:
        if isinstance(value, str):
            return [value]
        if isinstance(value, Mapping):
            return [text for item in value.values() for text in AffiliateContentService._text_values(item)]
        if isinstance(value, (list, tuple)):
            return [text for item in value for text in AffiliateContentService._text_values(item)]
        return []
