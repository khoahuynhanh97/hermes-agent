from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from hermes_personal.runtime.gateway_server import create_gateway_application


def _write_image(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (800, 800), color=(255, 255, 255)).save(path, format="PNG")


def _product(batch_dir: Path, index: int, *, name: str, brand: str, model: str) -> dict:
    images = []
    for image_index in range(2):
        image_path = batch_dir / "images" / f"prod-{index}" / f"img-{image_index}.png"
        _write_image(image_path)
        images.append(
            {
                "asset_id": f"asset-{index}-{image_index}",
                "absolute_path": str(image_path),
                "match_score": 1.0,
                "width": 800,
                "height": 800,
            }
        )
    return {
        "id": f"prod_{index:02d}",
        "name": name,
        "brand": brand,
        "model": model,
        "price_display": "200.000đ",
        "price_min": 200000,
        "price_max": 200000,
        "hot_reason": "Hot",
        "key_features": "Features",
        "keywords": [name],
        "image_count": len(images),
        "images": images,
    }


def test_product_video_routes(tmp_path: Path, monkeypatch) -> None:
    source_root = tmp_path / "daily_runs"
    batch_dir = source_root / "2026-09-12"
    batch_dir.mkdir(parents=True)

    products = [
        _product(batch_dir, 1, name="Quạt Jisulife Life 7", brand="Jisulife", model="Life 7"),
        _product(batch_dir, 2, name="Bàn phím AULA F75", brand="AULA", model="F75"),
    ]
    (batch_dir / "products.json").write_text(
        json.dumps({"version": "1.0", "date": "2026-09-12", "products": products}),
        encoding="utf-8",
    )

    monkeypatch.setenv("HERMES_PRODUCT_RUNS_ROOT", str(source_root))

    app = create_gateway_application(
        database_path=tmp_path / "runtime.sqlite3",
        api_key="test-api-key",
        provider_mode="fake",
    )

    with TestClient(app) as client:
        # 1. GET candidates
        res = client.get("/api/personal/product-video/candidates")
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        assert len(data["candidates"]) == 2
        f75 = next(c for c in data["candidates"] if c["model"] == "F75")
        assert f75["status"] == "unprocessed"

        # 2. POST start-batch (auto)
        start_res = client.post(
            "/api/personal/product-video/start-batch",
            json={"auto": True, "limit": 1},
        )
        assert start_res.status_code == 200
        start_data = start_res.json()
        assert start_data["ok"] is True
        assert len(start_data["started_workflows"]) == 1

        shortfall_res = client.post(
            "/api/personal/product-video/start-batch",
            json={"auto": True, "limit": 5, "minimum_daily": 3, "target_date": "2026-09-12"},
        )
        assert shortfall_res.status_code == 409
        shortfall = shortfall_res.json()
        assert shortfall["error"] == "INSUFFICIENT_DAILY_PRODUCTS"
        assert shortfall["daily_started_total"] == 2
