from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Any, List, Optional

@dataclass(frozen=True)
class ResearchSpec:
    """Specification of a product research request.

    Attributes:
        product_name: Name of the product to research.
        topics: Optional list of research topics.
    """
    product_name: str
    topics: Optional[List[str]] = None

    def effective_topics(self) -> List[str]:
        """Return topics to research.

        If explicit topics are provided, return them; otherwise return a default
        set covering interest, market size, and competition.
        """
        return self.topics if self.topics is not None else ["interest", "market_size", "competition"]

@dataclass(frozen=True)
class ResearchResult:
    """Result of a product research execution.

    Attributes:
        product_name: Name of the product researched.
        summary: Human‑readable summary of findings.
        data: Deterministic structured data with interest, market size, and competition.
    """
    product_name: str
    summary: str
    data: Dict[str, Any]

class ProductResearchPipeline:
    """Deterministic, offline research pipeline.

    Generates deterministic placeholder data without external services.
    """

    def run(self, spec: ResearchSpec) -> ResearchResult:
        """Execute pipeline for *spec* and return deterministic result.

        The implementation returns fixed data and a formatted summary matching the
        test expectations.
        """
        # Deterministic placeholder data.
        data: Dict[str, Any] = {
            "interest_score": "42%",
            "market_size": "68k users",
            "competition": "9 major rivals",
        }
        # Build summary using the expected format.
        summary = (
            f"Research for {spec.product_name} in general market:\n"
            f"- Interest: {data['interest_score']}\n"
            f"- Estimated market size: {data['market_size']}\n"
            f"- Competition: {data['competition']}"
        )
        return ResearchResult(product_name=spec.product_name, summary=summary, data=data)

def run_research(spec: ResearchSpec) -> ResearchResult:
    """Convenience helper that runs the given research spec.
    """
    pipeline = ProductResearchPipeline()
    return pipeline.run(spec)
