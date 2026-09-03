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
    """Product research pipeline with fail-closed external MCP support."""

    def __init__(self, mcp_client: Any = None) -> None:
        self.mcp_client = mcp_client

    def run(
        self,
        spec: ResearchSpec,
        *,
        fake: bool = False,
        mcp_client: Any = None,
    ) -> ResearchResult:
        client = mcp_client or self.mcp_client
        if client is not None:
            try:
                # Dispatch to external Product Intelligence MCP provider
                if hasattr(client, "research_product"):
                    result = client.research_product(spec.product_name, spec.keywords)
                elif hasattr(client, "research"):
                    result = client.research(spec.product_name, spec.keywords)
                else:
                    raise AttributeError("Configured MCP client lacks research_product/research method")

                if isinstance(result, ResearchResult):
                    return result
                if isinstance(result, dict):
                    summary = result.get("summary", f"Research for {spec.product_name}")
                    report_val = result.get("report")
                    report = report_val if isinstance(report_val, str) else json.dumps(result)
                    return ResearchResult(summary=summary, report=report)
                raise TypeError(f"Unexpected MCP response shape: {type(result)}")
            except Exception as exc:
                raise RuntimeError(f"External Product Intelligence MCP failed: {exc}") from exc

        if not fake:
            raise RuntimeError(
                "Product research requires an external MCP provider or explicit fake=True."
            )
        # Explicit fake mode only — fixed deterministic value for local development/testing.
        potential = 42
        summary = f"Research for {spec.product_name}: {potential}% market potential [FAKE]"
        report_dict = {
            "product_name": spec.product_name,
            "keywords": spec.keywords,
            "potential": potential,
            "fake": True,
        }
        report = json.dumps(report_dict)
        return ResearchResult(summary=summary, report=report)


def run_research(
    spec: ResearchSpec,
    *,
    fake: bool = False,
    mcp_client: Any = None,
) -> ResearchResult:
    """Convenient one‑liner used by tests/CLI.

    Executes the pipeline with the provided specification.
    """
    pipeline = ProductResearchPipeline(mcp_client=mcp_client)
    return pipeline.run(spec, fake=fake, mcp_client=mcp_client)
