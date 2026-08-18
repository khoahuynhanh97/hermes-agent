from __future__ import annotations

import hashlib
import inspect
import re
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from typing import Any, Sequence
from urllib.parse import urlparse

from hermes.application.reference_pattern_abstractor import (
    ReferencePatternAbstractor,
)
from hermes.domain.affiliate_research import (
    AffiliateProduct,
    ContentIdea,
    ContentPackage,
    PackageStatus,
    ReferenceMetadata,
    ResearchBrief,
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
    def __init__(
        self,
        repository: AffiliateResearchRepository,
        gateway: Any,
        *,
        reference_pattern_abstractor: ReferencePatternAbstractor | None = None,
    ):
        self._repository = repository
        self._gateway = gateway
        self._reference_pattern_abstractor = (
            reference_pattern_abstractor or ReferencePatternAbstractor()
        )

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
            package_id = self._initial_package_id(owner_user_id, run_id, product.id)
            saved_package = next(
                (package for package in existing if package.id == package_id), None
            )
            if saved_package is not None:
                packages.append(saved_package)
                continue
            product_references = self._references_for_product(
                owner_user_id, product.id, references
            )
            brief = self._repository.save_brief(
                self._brief_for(
                    product,
                    owner_user_id,
                    run_id,
                    product_references,
                    self._reference_pattern_abstractor,
                )
            )
            ideas = self._repository.save_ideas(
                product.id,
                run_id,
                self._ideas_for(product, owner_user_id, run_id, brief),
            )
            selected_idea = next(idea for idea in ideas if idea.selected)
            package = self._package_from_payload(
                self._generate(
                    product,
                    product_references,
                    brief=brief,
                    selected_idea=selected_idea,
                ),
                owner_user_id=owner_user_id,
                run_id=run_id,
                product=product,
                references=product_references,
                revision=1,
                existing=existing + packages,
                selected_idea=selected_idea,
                package_id=package_id,
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
        root_id = self._root_id(previous.id)
        revision_id = f"{root_id}:r{previous.revision + 1}"
        existing = self._repository.list_packages(owner_user_id)
        saved_revision = next((package for package in existing if package.id == revision_id), None)
        if saved_revision is not None:
            return saved_revision
        payload = self._gateway.generate(
            product,
            (),
            previous_package=previous,
            feedback=feedback,
        )
        revision = self._package_from_payload(
            payload,
            owner_user_id=owner_user_id,
            run_id=previous.run_id,
            product=product,
            references=(),
            revision=previous.revision + 1,
            existing=[
                package for package in existing if package.id != revision_id
            ],
            asset_rights=previous.asset_rights,
            package_id=revision_id,
            canonical_claims=previous.claims,
        )
        save_revision = getattr(self._repository, "save_revision", None)
        if save_revision is not None:
            return save_revision(previous.id, owner_user_id, revision, feedback)
        return self._repository.save_package(revision)

    @staticmethod
    def _ideas_for(
        product: AffiliateProduct,
        owner_user_id: str,
        run_id: str,
        brief: ResearchBrief,
    ) -> list[ContentIdea]:
        now = datetime.now(timezone.utc).isoformat()
        audiences = (
            ("office_worker", "workspace improvement"),
            ("remote_worker", "repeatable daily use"),
            ("tech_shopper", "evidence-led product comparison"),
        )
        signals = tuple(sorted(set(product.visual_signals))) or (
            f"{product.category} form and function",
        )
        patterns = brief.reference_patterns or (
            {
                "hook": "benefit-led observation",
                "pacing": "setup-demo-verdict",
                "story": "use-case-demonstration-takeaway",
            },
        )
        evidence_ids = tuple(
            str(item.get("reference_id", ""))
            for item in brief.reference_pattern_provenance
            if item.get("reference_id")
        )
        drafts = []
        for index, (audience, outcome) in enumerate(audiences, start=1):
            signal = signals[(index - 1) % len(signals)]
            pattern = patterns[(index - 1) % len(patterns)]
            hook_lens = pattern["hook"]
            angle = (
                f"{product.name}: {outcome} through {signal} "
                f"with a {hook_lens}"
            )
            drafts.append(
                (
                    round(
                        88.0
                        - index * 4.0
                        + min(6.0, len(brief.verified_specs) * 1.5),
                        2,
                    ),
                    audience,
                    angle,
                    (
                        f"Use {signal} as the observable proof for "
                        f"{product.category}; apply hook '{pattern['hook']}', "
                        f"pacing '{pattern['pacing']}', and story "
                        f"'{pattern['story']}' from references "
                        f"{', '.join(evidence_ids) or 'none'}."
                    ),
                )
            )
        drafts.sort(key=lambda item: (-item[0], item[1], item[2]))
        return [
            ContentIdea(
                id=hashlib.sha256(
                    f"{product.id}\0{run_id}\0{audience}\0{angle}".encode(
                        "utf-8"
                    )
                ).hexdigest(),
                owner_user_id=owner_user_id,
                product_id=product.id,
                run_id=run_id,
                audience=audience,
                angle=angle,
                rationale=rationale,
                created_at=now,
                score=score,
                rank=rank,
                selected=rank == 1,
            )
            for rank, (score, audience, angle, rationale) in enumerate(
                drafts, start=1
            )
        ]

    @staticmethod
    def _brief_for(
        product: AffiliateProduct,
        owner_user_id: str,
        run_id: str,
        references: Sequence[ReferenceMetadata],
        abstractor: ReferencePatternAbstractor | None = None,
    ) -> ResearchBrief:
        now = datetime.now(timezone.utc).isoformat()
        verified_specs = (
            {
                "name": "price_vnd",
                "value": product.price_vnd,
                "evidence_url": product.product_url or product.source_url,
                "source_type": product.source_type,
                "content_hash": product.content_hash,
            },
            {
                "name": "category",
                "value": product.category,
                "evidence_url": product.product_url or product.source_url,
                "source_type": product.source_type,
                "content_hash": product.content_hash,
            },
        )
        strengths = tuple(
            value
            for condition, value in (
                (bool(product.visual_signals), "Visible demonstration potential"),
                (
                    product.rating is not None and product.rating >= 4.5,
                    "Strong current rating evidence",
                ),
                (
                    product.sold_count is not None and product.sold_count > 0,
                    "Current sales evidence is available",
                ),
            )
            if condition
        )
        limitations = tuple(
            value
            for condition, value in (
                (product.rating is None, "Rating is not verified"),
                (product.review_count is None, "Review count is not verified"),
                (not product.visual_signals, "Visual demonstration needs review"),
            )
            if condition
        )
        abstractions = (abstractor or ReferencePatternAbstractor()).abstract(
            references
        )
        patterns = tuple(item.labels() for item in abstractions)
        provenance = tuple(dict(item.provenance) for item in abstractions)
        brief_id = hashlib.sha256(
            f"{owner_user_id}\0{run_id}\0{product.id}\0brief\0r1".encode("utf-8")
        ).hexdigest()
        return ResearchBrief(
            id=brief_id,
            owner_user_id=owner_user_id,
            product_id=product.id,
            run_id=run_id,
            revision=1,
            verified_specs=verified_specs,
            strengths=strengths,
            limitations=limitations,
            unverified_claims=(
                ("First-hand use has not been verified",)
                if product.rights_status != "owned"
                else ()
            ),
            reference_patterns=patterns,
            created_at=now,
            reference_pattern_provenance=provenance,
        )

    def _generate(
        self,
        product: AffiliateProduct,
        references: Sequence[ReferenceMetadata],
        *,
        brief: ResearchBrief,
        selected_idea: ContentIdea,
    ) -> Mapping[str, Any]:
        parameters = inspect.signature(self._gateway.generate).parameters
        kwargs = {}
        if "brief" in parameters:
            kwargs["brief"] = brief
        if "selected_idea" in parameters:
            kwargs["selected_idea"] = selected_idea
        return self._gateway.generate(product, references, **kwargs)

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
        selected_idea: ContentIdea | None = None,
        canonical_claims: Sequence[Mapping[str, Any]] = (),
    ) -> ContentPackage:
        self._validate_payload(payload)
        self._reject_first_hand_claims(payload)
        self._reject_duplicate_content(payload, existing)
        self._reject_reference_wording(payload, references)
        claims = self._canonicalize_claims(
            payload["claims"],
            product,
            references,
            canonical_claims,
        )
        rights = asset_rights if asset_rights is not None else {
            product.id: product.rights_status,
            **{reference.id: "reference_only" for reference in references},
        }
        now = datetime.now(timezone.utc).isoformat()
        return ContentPackage(
            id=package_id
            or self._initial_package_id(owner_user_id, run_id, product.id),
            owner_user_id=owner_user_id,
            product_id=product.id,
            run_id=run_id,
            revision=revision,
            status=PackageStatus.PENDING_REVIEW,
            audience=payload["audience"].strip(),
            angle=(
                selected_idea.angle
                if selected_idea is not None
                else payload["angle"].strip()
            ),
            angle_reason=(
                selected_idea.rationale
                if selected_idea is not None
                else payload["angle_reason"].strip()
            ),
            hook=payload["hook"].strip(),
            script=payload["script"].strip(),
            duration_seconds=payload["duration_seconds"],
            storyboard=tuple(dict(item) for item in payload["storyboard"]),
            ai_prompts=tuple(
                self._preserve_product_design(item, product)
                for item in payload["ai_prompts"]
            ),
            voiceover_plan=payload["voiceover_plan"].strip(),
            text_overlays=tuple(item.strip() for item in payload["text_overlays"]),
            claims=claims,
            warnings=tuple(item.strip() for item in payload["warnings"]),
            asset_rights=dict(rights),
            created_at=created_at or now,
            updated_at=updated_at or now,
        )

    @staticmethod
    def _initial_package_id(
        owner_user_id: str, run_id: str, product_id: str
    ) -> str:
        digest = hashlib.sha256(
            f"{owner_user_id}\0{run_id}\0{product_id}\0package\0r1".encode(
                "utf-8"
            )
        ).hexdigest()[:24]
        return f"pkg_{digest}"

    @staticmethod
    def _canonicalize_claims(
        claims: Sequence[Mapping[str, Any]],
        product: AffiliateProduct,
        references: Sequence[ReferenceMetadata],
        prior_claims: Sequence[Mapping[str, Any]],
    ) -> tuple[dict[str, object], ...]:
        evidence: dict[str, dict[str, object]] = {}
        for url in (product.product_url, product.source_url):
            if isinstance(url, str) and url.startswith("https://"):
                evidence[url] = {
                    "source_type": product.source_type,
                    "content_hash": product.content_hash,
                    "collected_at": product.updated_at,
                }
        for reference in references:
            evidence[reference.source_url] = {
                "source_type": reference.source_type,
                "content_hash": reference.content_hash
                or hashlib.sha256(reference.source_url.encode("utf-8")).hexdigest(),
                "collected_at": reference.collected_at,
            }
        for claim in prior_claims:
            url = claim.get("evidence_url")
            if (
                isinstance(url, str)
                and isinstance(claim.get("source_type"), str)
                and isinstance(claim.get("content_hash"), str)
                and isinstance(claim.get("collected_at"), str)
            ):
                evidence.setdefault(
                    url,
                    {
                        "source_type": claim["source_type"],
                        "content_hash": claim["content_hash"],
                        "collected_at": claim["collected_at"],
                    },
                )

        canonical = []
        stale_before = datetime.now(timezone.utc) - timedelta(days=30)
        for claim in claims:
            url = str(claim.get("evidence_url", ""))
            provenance = evidence.get(url)
            if provenance is None:
                raise ContentValidationError(
                    "every factual claim must match canonical evidence"
                )
            try:
                collected_at = datetime.fromisoformat(
                    str(provenance["collected_at"]).replace("Z", "+00:00")
                )
            except (TypeError, ValueError) as error:
                raise ContentValidationError(
                    "claim evidence has invalid provenance time"
                ) from error
            if collected_at.tzinfo is None:
                collected_at = collected_at.replace(tzinfo=timezone.utc)
            if collected_at < stale_before:
                raise ContentValidationError("claim evidence is stale")
            canonical.append(
                {
                    **dict(claim),
                    "evidence_url": url,
                    "source_type": provenance["source_type"],
                    "content_hash": provenance["content_hash"],
                    "collected_at": provenance["collected_at"],
                }
            )
        return tuple(canonical)

    @staticmethod
    def _reject_reference_wording(
        payload: Mapping[str, Any],
        references: Sequence[ReferenceMetadata],
    ) -> None:
        for output in (payload["hook"], payload["script"]):
            for reference in references:
                for wording in (reference.title, reference.caption):
                    if wording and AffiliateContentService._is_high_overlap(
                        output, wording
                    ):
                        raise ContentValidationError(
                            "content substantially overlaps reference wording"
                        )

    @staticmethod
    def _preserve_product_design(
        prompt: str, product: AffiliateProduct
    ) -> str:
        return (
            f"{prompt.strip()}. Use the supplied image of {product.name}; "
            "preserve its exact physical design, controls, proportions, and colors."
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
