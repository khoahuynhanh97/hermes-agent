import sys
import json
from unittest.mock import MagicMock

# Stub hermes.application.product_resource_service before importing client
sys.modules['hermes'] = MagicMock()
sys.modules['hermes.application'] = MagicMock()
sys.modules['hermes.application.product_resource_service'] = MagicMock()
# Define ProductResourceService class on the stub
ProductResourceService = MagicMock()
sys.modules['hermes.application.product_resource_service'].ProductResourceService = ProductResourceService

from hermes_personal.integrations.product_intelligence import client


def test_research_returns_dict():
    cl = client.ProductIntelligenceClient()
    result = cl.research("TestProduct", ["kw1", "kw2"])
    assert isinstance(result, dict)
    assert "summary" in result
    assert "report" in result
    assert "TestProduct" in result["summary"]
    report_dict = json.loads(result["report"])
    assert report_dict["product_name"] == "TestProduct"
    assert report_dict["keywords"] == ["kw1", "kw2"]


def test_build_resource_pack_parses_and_maps():
    cl = client.ProductIntelligenceClient()
    research_result = {
        "summary": "Research for TestProduct: 42% market potential",
        "report": json.dumps({
            "product_name": "TestProduct",
            "keywords": ["kw1", "kw2"]
        })
    }
    pack = cl.build_resource_pack(research_result)
    assert isinstance(pack, dict)
    assert "summary" in pack
    assert "assets_mapping" in pack
    assert "scene_plan" in pack
    assert pack["assets_mapping"]["kw1_asset"] == "https://example.com/assets/kw1_asset.png"
    assert pack["assets_mapping"]["kw2_asset"] == "https://example.com/assets/kw2_asset.png"
    assert isinstance(pack["scene_plan"], list)
    assert len(pack["scene_plan"]) == 2
    assert pack["scene_plan"][0].startswith("Scene 1:")
    assert pack["scene_plan"][1].startswith("Scene 2:")


def test_lock_resource_pack_invokes_service():
    cl = client.ProductIntelligenceClient()
    pack_dict = {
        "summary": "Resource pack for TestProduct: 2 assets, 2 scenes",
        "assets_mapping": {"kw1_asset": "https://example.com/assets/kw1_asset.png",
                           "kw2_asset": "https://example.com/assets/kw2_asset.png"},
        "scene_plan": ["Scene 1: kw1_asset", "Scene 2: kw2_asset"]
    }
    # Configure mock service
    mock_service = MagicMock()
    mock_service.lock_resource_pack.return_value = {
        "resource_pack_id": "rp_123",
        "resource_pack_version": 1,
        "status": "locked",
        "assets": [
            {"asset_id": "kw1_asset", "local_path": "https://example.com/assets/kw1_asset.png"},
            {"asset_id": "kw2_asset", "local_path": "https://example.com/assets/kw2_asset.png"}
        ],
        "manifest_digest": "sha256:abcd1234",
    }
    # Replace client's service with mock
    cl.service = mock_service
    locked = cl.lock_resource_pack(pack_dict, owner_user_id="tester")
    mock_service.lock_resource_pack.assert_called_once()
    args, _ = mock_service.lock_resource_pack.call_args
    payload = args[0]
    assert payload["resource_pack_id"].startswith("rp_")
    assert payload["status"] == "unlocked"
    assert args[1] == "tester"
    assert locked["status"] == "locked"
    assert "manifest_digest" in locked


def test_lock_resource_pack_idempotent():
    cl = client.ProductIntelligenceClient()
    pack_dict = {
        "summary": "Resource pack for TestProduct: 2 assets, 2 scenes",
        "assets_mapping": {"kw1_asset": "https://example.com/assets/kw1_asset.png"},
        "scene_plan": ["Scene 1: kw1_asset"]
    }
    # deterministic mock based on summary hash
    def lock_side_effect(payload, uid):
        import hashlib
        h = hashlib.sha256(payload.get("summary", "").encode()).hexdigest()
        return {
            "resource_pack_id": f"rp_{int(h, 16) & 0xffffffff}",
            "resource_pack_version": 1,
            "status": "locked",
            "assets": payload.get("assets", []),
            "manifest_digest": f"sha256:{h}",
        }
    mock_service = MagicMock()
    mock_service.lock_resource_pack.side_effect = lock_side_effect
    cl.service = mock_service
    locked1 = cl.lock_resource_pack(pack_dict)
    locked2 = cl.lock_resource_pack(pack_dict)
    assert locked1["resource_pack_id"] == locked2["resource_pack_id"]
    assert locked1["manifest_digest"] == locked2["manifest_digest"]


def test_malformed_report_raises():
    cl = client.ProductIntelligenceClient()
    bad_report = {"summary": "x", "report": "not json"}
    try:
        cl.build_resource_pack(bad_report)
        assert False, "Expected ValueError"
    except ValueError as e:
        assert "Malformed research report" in str(e)


if __name__ == "__main__":
    test_research_returns_dict()
    test_build_resource_pack_parses_and_maps()
    test_lock_resource_pack_invokes_service()
    test_lock_resource_pack_idempotent()
    test_malformed_report_raises()
    print("All tests passed")