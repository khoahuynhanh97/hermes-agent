from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence

from hermes.domain.affiliate_research import ReferenceMetadata


_TOKEN_PATTERN = re.compile(r"[\w]+", re.UNICODE)


@dataclass(frozen=True)
class ReferencePattern:
    hook: str
    pacing: str
    story: str
    provenance: dict[str, object]

    def labels(self) -> dict[str, str]:
        return {
            "hook": self.hook,
            "pacing": self.pacing,
            "story": self.story,
        }


class ReferencePatternAbstractor:
    """Map observable reference semantics to a controlled pattern vocabulary."""

    _QUESTION = frozenset({"how", "why", "what", "which"})
    _PROBLEM = frozenset(
        {
            "clutter",
            "cluttered",
            "fix",
            "fixing",
            "mess",
            "messy",
            "pain",
            "problem",
            "tangled",
        }
    )
    _SOLUTION = frozenset(
        {"after", "clean", "fix", "fixed", "install", "reveal", "solution"}
    )
    _SEQUENCE = frozenset(
        {"first", "next", "then", "finally", "step", "steps"}
    )
    _COMPARISON = frozenset(
        {"compare", "comparison", "versus", "vs", "better", "verdict"}
    )
    _DEMONSTRATION = frozenset(
        {"demo", "demonstrate", "show", "test", "unbox", "setup"}
    )

    def abstract(
        self, references: Sequence[ReferenceMetadata]
    ) -> tuple[ReferencePattern, ...]:
        return tuple(
            self._abstract_one(reference)
            for reference in sorted(references, key=lambda item: item.id)
        )

    def _abstract_one(
        self, reference: ReferenceMetadata
    ) -> ReferencePattern:
        title_tokens = self._tokens(reference.title)
        caption_tokens = self._tokens(reference.caption)
        tokens = title_tokens | caption_tokens
        combined = f"{reference.title}\n{reference.caption}".lower()
        signals = []
        before_after = "before" in tokens and "after" in tokens
        comparison = bool(tokens & self._COMPARISON)
        sequence = bool(tokens & self._SEQUENCE)
        problem_solution = bool(tokens & self._PROBLEM) and bool(
            tokens & self._SOLUTION
        )
        question = "?" in reference.title or bool(
            title_tokens & self._QUESTION
        )
        demonstration = bool(tokens & self._DEMONSTRATION)

        for matched, label in (
            (before_after, "before_after"),
            (comparison, "comparison"),
            (sequence, "sequence"),
            (problem_solution, "problem_solution"),
            (question, "question"),
        ):
            if matched:
                signals.append(label)
        if demonstration and not signals:
            signals.append("demonstration")

        if before_after:
            hook = "transformation reveal"
        elif comparison:
            hook = "comparative evaluation"
        elif problem_solution:
            hook = "problem-solution reveal"
        elif question:
            hook = "question-led discovery"
        elif demonstration:
            hook = "demonstration-led reveal"
        else:
            hook = "benefit-led observation"

        if sequence:
            pacing = "stepwise demonstration"
        elif len(combined) <= 100:
            pacing = "rapid proof beats"
        elif len(combined) >= 240:
            pacing = "measured explanation"
        else:
            pacing = "setup-demo-verdict"

        if before_after:
            story = "baseline-intervention-result"
        elif comparison:
            story = "criteria-comparison-verdict"
        elif problem_solution:
            story = "friction-intervention-outcome"
        elif "unbox" in tokens or "setup" in tokens:
            story = "arrival-setup-proof"
        else:
            story = "use-case-demonstration-takeaway"

        return ReferencePattern(
            hook=hook,
            pacing=pacing,
            story=story,
            provenance={
                "reference_id": reference.id,
                "source_type": reference.source_type,
                "content_hash": reference.content_hash,
                "collected_at": reference.collected_at,
                "observable_fields": ("title", "caption", "platform"),
                "matched_signals": tuple(signals),
            },
        )

    @staticmethod
    def _tokens(value: str) -> set[str]:
        return {
            match.group(0).lower()
            for match in _TOKEN_PATTERN.finditer(value)
        }
