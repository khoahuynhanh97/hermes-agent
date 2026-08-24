import json
from hermes_personal.product.research import ResearchSpec, run_research

def test_research_deterministic():
    spec = ResearchSpec(product_name="TestProduct", keywords=["alpha", "beta"])
    result1 = run_research(spec)
    result2 = run_research(spec)
    # Results should be identical across calls
    assert result1.summary == result2.summary
    assert json.loads(result1.report) == json.loads(result2.report)
    # Summary should contain product name and a percentage
    assert "TestProduct" in result1.summary
    assert result1.summary.split(":")[-1].strip().endswith("% market potential")
