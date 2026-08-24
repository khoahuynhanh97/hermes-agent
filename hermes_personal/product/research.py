"""Simple product research pipeline used for Phase 5 Task 1.

The implementation avoids any live provider calls – it works entirely with
in‑memory dummy data so that tests run deterministically and quickly. The
pipeline consists of three public symbols:

* ``ResearchSpec`` – minimal input specification (currently only a ``query``
  string).
* ``ResearchResult`` – holds ``summary`` text and optional ``data`` mapping.
* ``ProductResearchPipeline`` – ``run`` method that creates a ``ResearchResult``
  from a spec.

Convenience wrapper ``run_research`` mirrors the typical CLI‑style entry
point used by other personal modules.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Dict, Any

@dataclass(frozen=True, slots=True)
class ResearchSpec:
    """Specification for a research run.

    Attributes
    ----------
    product_name:
        Name of the product being researched.
    keywords:
        List of keywords relevant to the market analysis.
    """

    product_name: str
    keywords: list[str]


@dataclass(frozen=True, slots=True)
class ResearchResult:
    """Result of a research execution.

    ``summary`` is a short human‑readable description, while ``report`` is a
    JSON string containing structured data.
    """

    summary: str
    report: str


class ProductResearchPipeline:
    """Deterministic, provider‑free research pipeline.

    The ``run`` method fabricates a tiny dataset based on the ``spec.query``
    and returns a ``ResearchResult``. No external I/O occurs – the function is
    pure and therefore trivially testable.
    """

    def run(self, spec: ResearchSpec) -> ResearchResult:
        # Deterministic dummy data – generate a fake market potential percentage.
        # In a real implementation this would query external sources.
        potential = 42  # fixed deterministic value for testing
        summary = f"Research for {spec.product_name}: {potential}% market potential"
        report_dict = {
            "product_name": spec.product_name,
            "keywords": spec.keywords,
            "potential": potential,
        }
        report = json.dumps(report_dict)
        return ResearchResult(summary=summary, report=report)


def run_research(spec: ResearchSpec) -> ResearchResult:
    """Convenient one‑liner used by tests/CLI.

    Executes the pipeline with the provided specification.
    """

    pipeline = ProductResearchPipeline()
    return pipeline.run(spec)
