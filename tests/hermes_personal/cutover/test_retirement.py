from __future__ import annotations

import pytest

from hermes_personal.cutover.retirement import (
    RetirementAuthorizationError,
    RetirementChecker,
    RetirementEvidence,
)


def test_retirement_authorization_all_gates_passed():
    evidence = RetirementEvidence(
        zero_callers=True,
        parity_passed=True,
        reconciliation_passed=True,
        rollback_artifact_present=True,
        full_suite_passed=True,
        observation_window_completed=True,
        signed_release_record_present=True,
        retained_data_stores_confirmed=True,
    )

    auth = RetirementChecker.authorize("legacy_telegram_bot_loop", evidence)
    assert auth.authorized is True
    assert len(auth.missing_gates) == 0
    assert auth.component == "legacy_telegram_bot_loop"


def test_retirement_authorization_missing_gates_rejected():
    # Incomplete evidence (missing observation window and zero callers verification)
    evidence = RetirementEvidence(
        zero_callers=False,
        parity_passed=True,
        reconciliation_passed=True,
        rollback_artifact_present=True,
        full_suite_passed=True,
        observation_window_completed=False,
        signed_release_record_present=True,
        retained_data_stores_confirmed=True,
    )

    auth = RetirementChecker.authorize("legacy_cli_dispatcher", evidence)
    assert auth.authorized is False
    assert "zero_callers_static_and_runtime" in auth.missing_gates
    assert "completed_production_observation_window" in auth.missing_gates

    with pytest.raises(RetirementAuthorizationError, match="Missing mandatory gates"):
        RetirementChecker.authorize("legacy_cli_dispatcher", evidence, raise_on_failure=True)


def test_retirement_strictly_retains_data_stores():
    evidence = RetirementEvidence(
        zero_callers=True,
        parity_passed=True,
        reconciliation_passed=True,
        rollback_artifact_present=True,
        full_suite_passed=True,
        observation_window_completed=True,
        signed_release_record_present=True,
        retained_data_stores_confirmed=False,  # Unconfirmed data retention
    )

    auth = RetirementChecker.authorize("legacy_storage_adapter", evidence)
    assert auth.authorized is False
    assert "retained_data_stores_and_media" in auth.missing_gates
