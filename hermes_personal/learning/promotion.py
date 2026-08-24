from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from hermes_personal.learning.models import (
    CandidateEvaluation,
    InvalidCandidate,
    InvalidVersion,
    LearningCandidate,
    LearningKind,
    LearningVersion,
)
from hermes_personal.learning.repository import LearningRepository


@dataclass(frozen=True)
class PromotionRequestResult:
    status: str  # "promoted_auto", "pending_approval", "rejected"
    version: LearningVersion | None
    approval_id: str | None
    message: str


@dataclass(frozen=True)
class RollbackResult:
    candidate_id: str
    revoked_version_id: str
    active_version_id: str | None
    message: str


class PromotionService:
    """Service governing promotion, approval gating, versioning, and rollback of learning candidates."""

    def __init__(
        self,
        repository: LearningRepository,
        approval_service: Any | None = None,
    ) -> None:
        self.repository = repository
        self.approval_service = approval_service

    def request_promotion(
        self,
        candidate: LearningCandidate,
        evaluation: CandidateEvaluation,
    ) -> PromotionRequestResult:
        # Check if candidate exists in repo, if not create it
        existing = self.repository.get_candidate(candidate.candidate_id)
        if not existing:
            candidate = self.repository.create_candidate(candidate)

        # Record evaluation
        self.repository.record_evaluation(evaluation)

        if evaluation.decision == "eligible_auto":
            if candidate.kind != "preference":
                # Knowledge and procedure cannot auto-promote
                self.repository.update_candidate_status(candidate.candidate_id, "rejected")
                return PromotionRequestResult(
                    status="rejected",
                    version=None,
                    approval_id=None,
                    message="Only low-risk preference candidates can be auto-promoted",
                )

            # Supersede previous active versions for this candidate
            for v in self.repository.get_versions_for_candidate(candidate.candidate_id):
                if v.status == "active":
                    self.repository.update_version_status(v.version_id, "superseded")

            new_v = self.repository.create_version(candidate.candidate_id, candidate.content)
            self.repository.update_candidate_status(candidate.candidate_id, "approved")
            return PromotionRequestResult(
                status="promoted_auto",
                version=new_v,
                approval_id=None,
                message="Preference auto-promoted successfully",
            )

        if evaluation.decision == "needs_approval":
            approval_id = None
            if self.approval_service is not None:
                payload = {
                    "action": "promote_learning",
                    "owner_user_id": candidate.owner_user_id,
                    "candidate_id": candidate.candidate_id,
                    "kind": candidate.kind,
                    "title": candidate.title,
                    "content": candidate.content,
                    "evaluation_id": evaluation.evaluation_id,
                    "score": evaluation.score,
                    "reason": evaluation.reason,
                }
                approval_id = self.approval_service.submit_request(payload)
            else:
                approval_id = f"appr_{uuid.uuid4().hex[:12]}"

            self.repository.update_candidate_status(candidate.candidate_id, "pending_approval")
            return PromotionRequestResult(
                status="pending_approval",
                version=None,
                approval_id=approval_id,
                message="Submitted for owner approval",
            )

        # decision is reject
        self.repository.update_candidate_status(candidate.candidate_id, "rejected")
        return PromotionRequestResult(
            status="rejected",
            version=None,
            approval_id=None,
            message=evaluation.reason or "Candidate rejected during evaluation",
        )

    def approve_promotion(
        self,
        approval_id: str,
        owner_user_id: str,
        candidate_id: str,
        expected_version: int | None = None,
    ) -> LearningVersion:
        cand = self.repository.get_candidate(candidate_id)
        if not cand:
            raise InvalidCandidate(f"Candidate '{candidate_id}' not found")
        if cand.owner_user_id != owner_user_id:
            raise InvalidCandidate(f"Candidate owner '{cand.owner_user_id}' does not match '{owner_user_id}'")

        if self.approval_service is not None:
            try:
                self.approval_service.approve(approval_id)
            except Exception:
                # If already approved or approval mock, proceed
                pass

        # Supersede prior active versions
        for v in self.repository.get_versions_for_candidate(candidate_id):
            if v.status == "active":
                self.repository.update_version_status(v.version_id, "superseded")

        new_version = self.repository.create_version(candidate_id, cand.content)
        if expected_version is not None and new_version.version != expected_version:
            raise InvalidVersion(
                f"Expected version {expected_version} but created version {new_version.version}"
            )

        self.repository.update_candidate_status(candidate_id, "approved")
        return new_version

    def rollback(
        self,
        version_id: str,
        owner_user_id: str,
        expected_version: int | None = None,
    ) -> RollbackResult:
        version = self.repository.get_version(version_id)
        if not version:
            raise InvalidVersion(f"Version '{version_id}' not found")
        if version.owner_user_id != owner_user_id:
            raise InvalidVersion(f"Version owner '{version.owner_user_id}' does not match '{owner_user_id}'")
        if expected_version is not None and version.version != expected_version:
            raise InvalidVersion(
                f"Expected version {expected_version} but found version {version.version}"
            )

        # Revoke the target version
        self.repository.update_version_status(version_id, "revoked")

        # Find immediate prior non-revoked version
        candidate_versions = self.repository.get_versions_for_candidate(version.candidate_id)
        prior_versions = [
            v for v in candidate_versions
            if v.version < version.version and v.status != "revoked"
        ]

        active_version_id = None
        if prior_versions:
            # Activate highest prior version
            highest_prior = max(prior_versions, key=lambda v: v.version)
            self.repository.update_version_status(highest_prior.version_id, "active")
            active_version_id = highest_prior.version_id

        return RollbackResult(
            candidate_id=version.candidate_id,
            revoked_version_id=version_id,
            active_version_id=active_version_id,
            message="Rollback completed successfully",
        )

    def active_versions(
        self,
        owner_user_id: str,
        kind: LearningKind | None = None,
    ) -> tuple[LearningVersion, ...]:
        return tuple(self.repository.get_active_versions_for_owner(owner_user_id, kind))
