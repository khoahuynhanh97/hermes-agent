from __future__ import annotations

from typing import Literal

from hermes.domain.affiliate_research import ContentPackage
from hermes.ports.affiliate_research import AffiliateResearchRepository


ReviewAction = Literal["approve", "revise", "reject"]


class PackageNotFound(LookupError):
    """The requested package is not visible to the reviewing owner."""


class AffiliateReviewService:
    """Owner-scoped package lifecycle operations for human review channels."""

    def __init__(self, repository: AffiliateResearchRepository):
        self._repository = repository

    def apply(
        self,
        package_id: str,
        owner_user_id: str,
        action: ReviewAction,
        reason: str = "",
    ) -> ContentPackage:
        if action not in {"approve", "revise", "reject"}:
            raise ValueError(f"unsupported review action: {action}")
        try:
            return self._repository.transition_package(
                package_id, owner_user_id, action, reason
            )
        except LookupError as error:
            raise PackageNotFound(package_id) from error
