from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal, Sequence

from hermes_personal.learning.evaluator import SENSITIVE_PATTERNS
from hermes_personal.learning.models import LearningCandidate, LearningVersion
from hermes_personal.learning.retrieval import RetrievedLearning

PreferenceRiskLevel = Literal["low_risk", "high_risk", "prohibited_secret"]
PreferenceCategory = Literal[
    "formatting",
    "tone",
    "locale",
    "ui_default",
    "identity",
    "credential",
    "financial",
    "destructive",
    "legal_medical",
    "other",
]


@dataclass(frozen=True)
class PreferencePolicyResult:
    allowed_auto: bool
    risk_level: PreferenceRiskLevel
    category: PreferenceCategory
    reason: str


HIGH_RISK_PATTERNS: dict[PreferenceCategory, re.Pattern] = {
    "identity": re.compile(r"\b(?:ssn|social\s+security|passport|tax\s+id|driver'?s?\s+license|date\s+of\s+birth)\b", re.IGNORECASE),
    "financial": re.compile(r"\b(?:credit\s+card|bank\s+account|cvv|budget\s+limit|billing|wire\s+transfer|payment\s+method)\b", re.IGNORECASE),
    "destructive": re.compile(r"\b(?:auto[- ]delete|drop\s+table|purge\s+all|rm\s+-rf|force\s+overwrite|wipe\s+database)\b", re.IGNORECASE),
    "legal_medical": re.compile(r"\b(?:medical\s+diagnosis|prescription|legal\s+liability|attorney[- ]client|litigation)\b", re.IGNORECASE),
    "credential": re.compile(r"\b(?:api[_-]?key|access[_-]?token|auth[_-]?token|bearer\s+token|private\s+key|password|credential)\b", re.IGNORECASE),
}

LOW_RISK_PATTERNS: dict[PreferenceCategory, re.Pattern] = {
    "formatting": re.compile(r"\b(?:concise|brief|bullet\s+points|table\s+format|markdown|summary\s+first|short\s+answers?|verbosity)\b", re.IGNORECASE),
    "tone": re.compile(r"\b(?:tone|style|formal|casual|friendly|professional|direct|polite|humorous)\b", re.IGNORECASE),
    "locale": re.compile(r"\b(?:vietnamese|english|spanish|french|japanese|language|locale|timezone)\b", re.IGNORECASE),
    "ui_default": re.compile(r"\b(?:dark\s+mode|light\s+mode|theme|compact\s+view|sidebar|layout)\b", re.IGNORECASE),
}


class PreferenceMemoryPolicy:
    """Classifies preference memory candidates against governance rules and generates USER.md projections."""

    def classify(self, candidate: LearningCandidate) -> PreferencePolicyResult:
        combined_text = f"{candidate.title}\n{candidate.content}"

        # 1. Prohibited secret detection
        if any(p.search(combined_text) for p in SENSITIVE_PATTERNS):
            return PreferencePolicyResult(
                allowed_auto=False,
                risk_level="prohibited_secret",
                category="credential",
                reason="Prohibited secret or credential pattern detected; storage rejected",
            )

        # 2. High-risk topic detection
        for cat, pat in HIGH_RISK_PATTERNS.items():
            if pat.search(combined_text):
                return PreferencePolicyResult(
                    allowed_auto=False,
                    risk_level="high_risk",
                    category=cat,
                    reason=f"High-risk topic '{cat}' requires explicit owner approval",
                )

        # 3. Low-risk categorization
        for cat, pat in LOW_RISK_PATTERNS.items():
            if pat.search(combined_text):
                has_explicit_evidence = any(
                    e.source_type in ("feedback", "turn") for e in candidate.evidence
                )
                if has_explicit_evidence:
                    return PreferencePolicyResult(
                        allowed_auto=True,
                        risk_level="low_risk",
                        category=cat,
                        reason=f"Explicit low-risk preference in '{cat}' category is eligible for automatic promotion",
                    )
                return PreferencePolicyResult(
                    allowed_auto=False,
                    risk_level="low_risk",
                    category=cat,
                    reason="Low-risk preference requires explicit turn/feedback evidence for auto-promotion",
                )

        # 4. Default / unclassified
        return PreferencePolicyResult(
            allowed_auto=False,
            risk_level="high_risk",
            category="other",
            reason="Unclassified preference requires explicit owner approval",
        )

    def project_user_markdown(
        self,
        preferences: Sequence[LearningVersion | RetrievedLearning | LearningCandidate],
    ) -> str:
        if not preferences:
            return "# User Profile & Preferences\n\nNo preferences recorded.\n"

        lines: list[str] = ["# User Profile & Preferences\n"]
        for pref in preferences:
            title = getattr(pref, "title", "Preference")
            content = getattr(pref, "content", "")
            lines.append(f"- **{title}**: {content}")

        return "\n".join(lines) + "\n"
