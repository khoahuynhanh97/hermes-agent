from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient


def test_product_research_run_endpoint_returns_phase_summary(monkeypatch):
    from hermes.channels.api.app import app
    from hermes.channels.api.routes import product_research

    class FakeWorkflow:
        def run(self, intent):
            assert intent.owner_user_id
            assert "bàn phím" in intent.raw_message
            return SimpleNamespace(
                to_payload=lambda: {
                    "run_id": "run-1",
                    "status": "completed",
                    "imported": 30,
                    "shortlisted": 15,
                    "package_ids": ["pkg-1"],
                    "local_sheet_paths": {"Scripts": "scripts.csv"},
                    "phase_summary": {
                        "research": "completed",
                        "analysis": "completed",
                        "script": "completed",
                        "prompt": "completed",
                    },
                    "content_previews": [{"script": "script", "ai_prompts": "prompt"}],
                }
            )

    monkeypatch.setattr(product_research, "build_product_research_workflow", lambda: FakeWorkflow())

    response = TestClient(app).post(
        "/api/products/research/run",
        json={"message": "crawl ngành bàn phím, giá 200k-500k"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "ok"
    assert body["result"]["phase_summary"]["prompt"] == "completed"
    assert body["result"]["content_previews"][0]["ai_prompts"] == "prompt"
