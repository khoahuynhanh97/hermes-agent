"""Product research pipeline – deterministic, no external calls.

Provides simple fake data generation for a product name and optional keywords.
Used by Phase 5 Task 1.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import List


@dataclass(frozen=True, slots=True)
class ResearchSpec:
    """Specification for a product research run.

    Attributes
    ----------
    product_name: Name of the product to research.
    keywords: Optional list of focus keywords.
    """

    product_name: str
    keywords: List[str] | None = None

    def __post_init__(self) -> None:  # noqa: D401
        # Normalise keywords to a sorted list for deterministic behaviour
        object.__setattr__(self, "keywords", sorted(self.keywords or []))


@dataclass(frozen=True, slots=True)
class ResearchResult:
    """Result of a research run.

    summary: One‑line headline.
    report: JSON‑formatted detail block.
    """

    summary: str
    report: str

    def as_dict(self) -> dict:
        """Return result as a plain dict for json serialisation."""
        return {"summary": self.summary, "report": self.report}


class ProductResearchPipeline:
    """Deterministic fake research pipeline.

    Generates reproducible dummy insights based on a hash of the input spec.
    No network or paid‑provider calls are performed.
    """

    @staticmethod
    def _deterministic_hash(spec: ResearchSpec) -> int:
        """Create a stable integer hash from the spec.

        Uses SHA‑256 of a JSON representation; returns an int in range 0‑100.
        """
        spec_json = json.dumps({"product_name": spec.product_name, "keywords": spec.keywords}, sort_keys=True)
        digest = hashlib.sha256(spec_json.encode()).hexdigest()
        # Take first 8 hex chars → 32‑bit int, then mod 101 for a 0‑100 range
        return int(digest[:8], 16) % 101

    def run(self, spec: ResearchSpec) -> ResearchResult:
        """Execute the fake research pipeline.

        Returns a reproducible ``ResearchResult`` based on the spec.
        """
        score = self._deterministic_hash(spec)
        # Simple deterministic faux‑insights
        summary = f"Research for {spec.product_name}: {score}% market potential"
        insights = {
            "product": spec.product_name,
            "keywords": spec.keywords,
            "potential_score": score,
            "insights": [
                f"Keyword '{kw}' shows {score // max(1, len(spec.keywords))}% relevance" for kw in spec.keywords
            ]
            if spec.keywords
            else [],
        }
        report = json.dumps(insights, indent=2, sort_keys=True)
        return ResearchResult(summary=summary, report=report)


def run_research(spec: ResearchSpec) -> ResearchResult:
    """Convenient helper to run the pipeline in a single call."""
    pipeline = ProductResearchPipeline()
    return pipeline.run(spec)
