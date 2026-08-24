import json
from hermes_personal.product.resource_pack import ResourcePackSpec, run_resource_pack_builder

def test_resource_pack_deterministic():
    spec = ResourcePackSpec(
        product_name="DemoProduct",
        assets=["logo", "banner"],
        scenes=["intro", "outro"]
    )
    result1 = run_resource_pack_builder(spec)
    result2 = run_resource_pack_builder(spec)
    # identical results
    assert result1.summary == result2.summary
    assert result1.assets_mapping == result2.assets_mapping
    assert result1.scene_plan.steps == result2.scene_plan.steps
    # summary contains product name and counts
    assert "DemoProduct" in result1.summary
    assert "2 assets" in result1.summary
    assert "2 scenes" in result1.summary
    # assets mapping deterministic URLs
    expected_urls = {
        "logo": "https://example.com/assets/logo.png",
        "banner": "https://example.com/assets/banner.png",
    }
    assert result1.assets_mapping == expected_urls
    # scene plan steps formatted correctly
    assert result1.scene_plan.steps == ["Scene 1: intro", "Scene 2: outro"]
    # JSON serialization round‑trip
    parsed = json.loads(result1.to_json())
    assert parsed["summary"] == result1.summary
    assert parsed["assets_mapping"] == result1.assets_mapping
    assert parsed["scene_plan"] == {"steps": result1.scene_plan.steps}
