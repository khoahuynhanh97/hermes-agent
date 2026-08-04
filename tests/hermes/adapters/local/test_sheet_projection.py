from __future__ import annotations

import csv
import json


class FakeRepository:
    def projection_rows(self, owner_user_id: str, run_id: str):
        assert owner_user_id == "42"
        assert run_id == "run-1"
        return {
            "products": [
                {
                    "id": "product-1",
                    "name": "Keyboard A",
                    "price_vnd": 350000,
                    "image_urls": ["https://example.test/image.jpg"],
                }
            ],
            "packages": [
                {
                    "id": "pkg-1",
                    "product_id": "product-1",
                    "hook": "Góc bàn làm việc cần gọn hơn?",
                    "script": "Đây là kịch bản ngắn.",
                    "warnings": ["Verify price"],
                }
            ],
            "runs": [{"id": "run-1", "status": "completed"}],
        }


def test_local_sheet_projection_writes_required_csv_files_with_stable_id(tmp_path):
    from hermes.adapters.local.sheet_projection import LocalSheetProjection

    projection = LocalSheetProjection(FakeRepository(), tmp_path)
    result = projection.sync("42", "run-1")

    assert result.ok is True
    paths = projection.output_paths("42", "run-1")
    assert set(paths) >= {"Products", "Shortlist", "Scripts", "Runs_Errors"}

    with open(paths["Products"], encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert rows[0]["stable_id"] == "product-1"
    assert rows[0]["name"] == "Keyboard A"
    assert json.loads(rows[0]["image_urls"]) == ["https://example.test/image.jpg"]


def test_local_sheet_projection_returns_retryable_failure_without_leaking_secret(tmp_path):
    from hermes.adapters.local.sheet_projection import LocalSheetProjection

    class BrokenRepository:
        def projection_rows(self, owner_user_id: str, run_id: str):
            raise RuntimeError("failed with token secret-value")

    result = LocalSheetProjection(BrokenRepository(), tmp_path).sync("42", "run-1")

    assert result.ok is False
    assert result.retryable is True
    assert "secret-value" not in result.detail