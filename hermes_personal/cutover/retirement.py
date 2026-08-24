from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class RetirementAuthorizationError(Exception):
    """Raised when an unauthorized component retirement is attempted."""


@dataclass(frozen=True)
class RetirementEvidence:
    """The 7 mandatory quality gates required before legacy component retirement."""

    zero_callers: bool
    parity_passed: bool
    reconciliation_passed: bool
    rollback_artifact_present: bool
    full_suite_passed: bool
    observation_window_completed: bool
    signed_release_record_present: bool
    retained_data_stores_confirmed: bool = True

    def evaluate_gates(self) -> list[str]:
        missing: list[str] = []
        if not self.zero_callers:
            missing.append("zero_callers_static_and_runtime")
        if not self.parity_passed:
            missing.append("semantic_parity_verification")
        if not self.reconciliation_passed:
            missing.append("data_migration_reconciliation")
        if not self.rollback_artifact_present:
            missing.append("tested_rollback_artifact")
        if not self.full_suite_passed:
            missing.append("full_test_suite_pass")
        if not self.observation_window_completed:
            missing.append("completed_production_observation_window")
        if not self.signed_release_record_present:
            missing.append("signed_release_record")
        if not self.retained_data_stores_confirmed:
            missing.append("retained_data_stores_and_media")
        return missing


@dataclass(frozen=True)
class RetirementAuthorization:
    authorized: bool
    component: str
    missing_gates: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "authorized": self.authorized,
            "component": self.component,
            "missing_gates": list(self.missing_gates),
        }


class RetirementChecker:
    """Enforces strict multi-gate authorization before retiring any legacy gateway or agent path."""

    @classmethod
    def authorize(
        cls,
        component_name: str,
        evidence: RetirementEvidence,
        raise_on_failure: bool = False,
    ) -> RetirementAuthorization:
        missing = evidence.evaluate_gates()
        is_authorized = len(missing) == 0

        if not is_authorized and raise_on_failure:
            raise RetirementAuthorizationError(
                f"Retirement of '{component_name}' rejected. Missing mandatory gates: {', '.join(missing)}"
            )

        return RetirementAuthorization(
            authorized=is_authorized,
            component=component_name,
            missing_gates=tuple(missing),
        )
