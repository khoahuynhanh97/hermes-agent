import pytest

from hermes_personal.product.research import ResearchSpec, run_research


def test_run_research_default_topics():
    spec = ResearchSpec(product_name="Widget")
    result = run_research(spec)
    assert result.product_name == "Widget"
    # deterministic data
    assert result.data == {
        "interest_score": "42%",
        "market_size": "68k users",
        "competition": "9 major rivals",
    }
    expected_summary = (
        "Research for Widget in general market:\n"
        "- Interest: 42%\n"
        "- Estimated market size: 68k users\n"
        "- Competition: 9 major rivals"
    )
    assert result.summary == expected_summary


def test_effective_topics_custom():
    spec = ResearchSpec(product_name="Gadget", topics=["pricing", "distribution"])
    # effective_topics should return the custom list
    assert spec.effective_topics() == ["pricing", "distribution"]
