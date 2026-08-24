from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class ResearchSpec:
    """Specification for a product research run.

    Attributes
    ----------
    product_name: str
        Name of the product to research.
    topics: List[str] | None
        Optional list of topics to include; defaults to a generic set.
    """

    product_name: str
    topics: List[str] | None = None

    def effective_topics(self) -> List[str]:
        return self.topics or ["market", "competition", "trends"]


@dataclass(frozen=True)
class ResearchResult:
    """Result of a product research execution.

    Attributes
    ----------
    product_name: str
    data: dict
    summary: str
    """

    product_name: str
    data: dict
    summary: str

    def __str__(self) -> str:
        return self.summary


class ProductResearchPipeline:
    """Deterministic, offline research pipeline.

    Generates a predictable summary from the spec without external calls.
    """

    def __init__(self, spec: ResearchSpec):
        self.spec = spec

    def _gather_data(self) -> dict:
        # Deterministic fake metrics
        return {
            "interest_score": "42%",
            "market_size": "68k users",
            "competition": "9 major rivals",
        }

    def _synthesize_summary(self, data: dict) -> str:
        # Deterministic summary format
        return (
            f"Research for {self.spec.product_name} in general market:\n"
            f"- Interest: {data['interest_score']}\n"
            f"- Estimated market size: {data['market_size']}\n"
            f"- Competition: {data['competition']}"
        )

    def run(self) -> ResearchResult:
        data = self._gather_data()
        summary = self._synthesize_summary(data)
        return ResearchResult(product_name=self.spec.product_name, data=data, summary=summary)


def run_research(spec: ResearchSpec) -> ResearchResult:
    """Convenient function to execute the pipeline.

    Returns a :class:`ResearchResult`.
    """

    pipeline = ProductResearchPipeline(spec)
    return pipeline.run()
