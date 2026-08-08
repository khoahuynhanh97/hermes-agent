"""Layer-3 application service that turns products + references into
spec-compliant ``AffiliateAnalysis`` records.

Designed to live next to the existing ``AffiliateContentService``
without touching it: it consumes the same product + reference
inputs and writes to a new ``affiliate_analyses`` table.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Protocol, Sequence

from hermes.domain.affiliate_analysis import (
    AffiliateAnalysis,
    TikTokScript,
    VisualPrompts,
)
from hermes.domain.affiliate_research import AffiliateProduct, ReferenceMetadata


class AffiliateAnalysisValidationError(ValueError):
    """Raised when the gateway returned an analysis that fails spec validation."""


class AnalysisGatewayPort(Protocol):
    def generate(
        self,
        product: AffiliateProduct,
        references: Sequence[ReferenceMetadata],
        web_documents: Sequence[Any],
    ) -> dict[str, Any]: ...


class AffiliateAnalysisRepositoryPort(Protocol):
    def save(self, analysis: AffiliateAnalysis) -> AffiliateAnalysis: ...


class AffiliateAnalysisService:
    def __init__(
        self,
        gateway: AnalysisGatewayPort,
        repository: AffiliateAnalysisRepositoryPort,
        *,
        validate_payload: Any = None,
    ):
        from hermes.adapters.model.affiliate_analysis_gateway import (
            validate_analysis_payload,
        )

        self._gateway = gateway
        self._repository = repository
        self._validate_payload = validate_payload or validate_analysis_payload

    def analyze_product(
        self,
        owner_user_id: str,
        run_id: str,
        product: AffiliateProduct,
        references: Sequence[ReferenceMetadata] = (),
        web_documents: Sequence[Any] = (),
        *,
        fallback_used: bool = False,
    ) -> AffiliateAnalysis:
        if product.owner_user_id != owner_user_id:
            raise AffiliateAnalysisValidationError(
                f"product '{product.id}' owner mismatch"
            )

        payload = self._gateway.generate(product, references, web_documents)
        try:
            self._validate_payload(payload)
        except Exception as error:
            raise AffiliateAnalysisValidationError(str(error)) from error

        analysis = _build_analysis(
            owner_user_id=owner_user_id,
            run_id=run_id,
            product=product,
            payload=payload,
            fallback_used=fallback_used,
        )
        return self._repository.save(analysis)


def _build_analysis(
    *,
    owner_user_id: str,
    run_id: str,
    product: AffiliateProduct,
    payload: dict[str, Any],
    fallback_used: bool,
) -> AffiliateAnalysis:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    analysis_id = hashlib.sha256(
        f"{owner_user_id}\0{run_id}\0{product.id}\0analysis".encode("utf-8")
    ).hexdigest()[:24]
    return AffiliateAnalysis(
        analysis_id=f"ana_{analysis_id}",
        owner_user_id=owner_user_id,
        product_id=product.id,
        run_id=run_id,
        usp_list=tuple(item.strip() for item in payload["usp_list"]),
        pain_points=tuple(item.strip() for item in payload["pain_points"]),
        target_audience=payload["target_audience"].strip(),
        tiktok_script=TikTokScript(
            hook=payload["tiktok_script"]["hook"].strip(),
            body=payload["tiktok_script"]["body"].strip(),
            cta=payload["tiktok_script"]["cta"].strip(),
        ),
        visual_prompts=VisualPrompts(
            image_prompt=payload["visual_prompts"]["image_prompt"].strip(),
            video_prompt=payload["visual_prompts"]["video_prompt"].strip(),
        ),
        fallback_used=fallback_used,
        created_at=now,
    )
