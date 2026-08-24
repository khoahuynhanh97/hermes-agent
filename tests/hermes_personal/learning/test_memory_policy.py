from __future__ import annotations

import pytest

from hermes_personal.learning.memory_policy import PreferenceMemoryPolicy
from hermes_personal.learning.models import (
    EvidenceRef,
    LearningCandidate,
    LearningVersion,
)


@pytest.fixture
def policy():
    return PreferenceMemoryPolicy()


def sample_evidence(source_type="feedback"):
    return EvidenceRef(
        evidence_id="ev_m1",
        source_type=source_type,
        source_id="turn_1",
        digest="sha256:789",
        excerpt="preference statement",
    )


def test_low_risk_explicit_preferences_allow_auto(policy):
    low_risk_cases = [
        ("Brevity", "Always reply concisely in bullet points.", "formatting"),
        ("Tone", "Use a direct, professional tone.", "tone"),
        ("Locale", "Preferred language is Vietnamese.", "locale"),
        ("UI Theme", "Enable dark mode by default.", "ui_default"),
    ]

    for title, content, expected_cat in low_risk_cases:
        cand = LearningCandidate(
            candidate_id=f"c_{expected_cat}",
            owner_user_id="user1",
            kind="preference",
            title=title,
            content=content,
            evidence=(sample_evidence("feedback"),),
        )
        result = policy.classify(cand)
        assert result.allowed_auto is True
        assert result.risk_level == "low_risk"
        assert result.category == expected_cat


def test_high_risk_preferences_require_approval(policy):
    high_risk_cases = [
        ("Identity Info", "My SSN is 000-12-3456", "identity"),
        ("Billing Limit", "Set payment budget limit to 1000 USD", "financial"),
        ("Destructive Command", "Auto-delete temporary database tables on start", "destructive"),
        ("Medical Advice", "Store medical diagnosis notes", "legal_medical"),
    ]

    for title, content, expected_cat in high_risk_cases:
        cand = LearningCandidate(
            candidate_id=f"c_hr_{expected_cat}",
            owner_user_id="user1",
            kind="preference",
            title=title,
            content=content,
            evidence=(sample_evidence("feedback"),),
        )
        result = policy.classify(cand)
        assert result.allowed_auto is False
        assert result.risk_level == "high_risk"
        assert result.category == expected_cat


def test_prohibited_secrets_rejected(policy):
    cand = LearningCandidate(
        candidate_id="c_sec",
        owner_user_id="user1",
        kind="preference",
        title="OpenAI Secret",
        content="Default api_key := 'sk-123456789012345678901234567890'",
        evidence=(sample_evidence("feedback"),),
    )
    result = policy.classify(cand)
    assert result.allowed_auto is False
    assert result.risk_level == "prohibited_secret"


def test_low_risk_without_explicit_feedback_requires_approval(policy):
    cand = LearningCandidate(
        candidate_id="c_no_exp",
        owner_user_id="user1",
        kind="preference",
        title="Tone Inferred",
        content="Casual tone observed in artifact",
        evidence=(sample_evidence(source_type="artifact"),),
    )
    result = policy.classify(cand)
    assert result.allowed_auto is False
    assert result.risk_level == "low_risk"


def test_project_user_markdown(policy):
    versions = [
        LearningVersion(
            version_id="v_1",
            candidate_id="c_1",
            owner_user_id="user1",
            version=1,
            content="Concise bullets",
            digest="sha256:111",
        ),
    ]
    markdown = policy.project_user_markdown(versions)
    assert "# User Profile & Preferences" in markdown
    assert "Concise bullets" in markdown
