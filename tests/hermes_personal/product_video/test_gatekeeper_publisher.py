"""Tests for Product Intelligence Gatekeeper & Publisher with Master Catalog deduplication."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from hermes_personal.product_video.automation.contracts import (
    compute_canonical_product_key,
    compute_product_key,
)
from hermes_personal.product_video.automation.importer import publish_daily_run_to_exchange
from hermes_personal.product_video.automation.repository import DailyImportRepository


@pytest.fixture
def temp_db(tmp_path: Path) -> sqlite3.Connection:
    """Temporary SQLite database with master catalog schema."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    repo = DailyImportRepository(conn)
    return conn


@pytest.fixture
def mock_daily_run(tmp_path: Path) -> Path:
    """Create mock Product-Intelligence daily run directory."""
    run_dir = tmp_path / "daily_runs" / "2026-09-29"
    run_dir.mkdir(parents=True)

    # Create sample products.json
    products_data = {
        "date": "2026-09-29",
        "products": [
            {
                "id": "prod_001",
                "name": "Xiaomi Redmi Watch 5 Active",
                "brand": "Xiaomi",
                "model": "Redmi Watch 5 Active",
                "variant": None,
                "category": "Smartwatch",
                "price_display": "790.000đ",
                "price_min": 790000,
                "price_max": 790000,
                "currency": "VND",
                "hot_reason": "Top trending smartwatch with 18-day battery life",
                "key_features": "18-day battery, 140+ sports modes, 5ATM waterproof",
                "keywords": ["xiaomi", "smartwatch", "fitness"],
                "pdp_url": "https://shopee.vn/product/...",
                "images": [
                    {
                        "asset_id": "img_001_01",
                        "local_path": "images/prod_001_01.jpg",
                        "original_url": "https://example.com/img1.jpg",
                        "match_score": 1.0,
                        "width": 1080,
                        "height": 1920,
                    },
                    {
                        "asset_id": "img_001_02",
                        "local_path": "images/prod_001_02.jpg",
                        "original_url": "https://example.com/img2.jpg",
                        "match_score": 0.95,
                        "width": 1080,
                        "height": 1920,
                    },
                ],
            },
            {
                "id": "prod_002",
                "name": "Baseus Bowie WM02 Plus",
                "brand": "Baseus",
                "model": "Bowie WM02 Plus",
                "variant": None,
                "hot_reason": "Best-selling wireless earbuds under 300k",
                "key_features": "ANC, 48h battery, dual-device pairing",
                "keywords": ["baseus", "earbuds", "anc"],
                "images": [
                    {
                        "asset_id": "img_002_01",
                        "local_path": "images/prod_002_01.jpg",
                        "match_score": 1.0,
                    },
                    {
                        "asset_id": "img_002_02",
                        "local_path": "images/prod_002_02.jpg",
                        "match_score": 0.8,
                    },
                ],
            },
            {
                "id": "prod_003",
                "name": "Ugreen Uno 30W/65W GaN Charger",  # Ambiguous variant
                "brand": "Ugreen",
                "model": "Uno GaN Charger",
                "hot_reason": "Fast charging",
                "images": [
                    {"asset_id": "img_003_01", "local_path": "images/prod_003_01.jpg"},
                    {"asset_id": "img_003_02", "local_path": "images/prod_003_02.jpg"},
                ],
            },
        ],
    }

    (run_dir / "products.json").write_text(json.dumps(products_data, ensure_ascii=False), encoding="utf-8")

    # Create dummy images
    img_dir = run_dir / "images"
    img_dir.mkdir()
    for i in range(1, 4):
        for j in range(1, 3):
            img_file = img_dir / f"prod_00{i}_0{j}.jpg"
            img_file.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)  # Minimal JPEG header

    return run_dir


def test_master_catalog_schema_creation(temp_db: sqlite3.Connection):
    """Verify master catalog table is created with correct schema."""
    cursor = temp_db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='product_master_catalog'"
    )
    assert cursor.fetchone() is not None

    # Check columns
    cols = [row[1] for row in temp_db.execute("PRAGMA table_info(product_master_catalog)")]
    assert "canonical_product_key" in cols
    assert "product_key" in cols
    assert "status" in cols
    assert "cooldown_until" in cols
    assert "production_count" in cols


def test_upsert_scouted_product(temp_db: sqlite3.Connection):
    """Test recording newly discovered products."""
    repo = DailyImportRepository(temp_db)

    canonical_key = compute_canonical_product_key("Xiaomi", "Redmi Watch 5 Active", None)
    product_key = compute_product_key(canonical_key)

    repo.upsert_scouted_product(
        canonical_product_key=canonical_key,
        product_key=product_key,
        brand="Xiaomi",
        model="Redmi Watch 5 Active",
        variant="",
        source_url="https://shopee.vn/product/123",
    )

    entry = repo.get_master_catalog_entry(canonical_key)
    assert entry is not None
    assert entry["canonical_product_key"] == canonical_key
    assert entry["product_key"] == product_key
    assert entry["brand"] == "Xiaomi"
    assert entry["model"] == "Redmi Watch 5 Active"
    assert entry["status"] == "scouted"


def test_cooldown_check_new_product(temp_db: sqlite3.Connection):
    """New products should pass cooldown check."""
    repo = DailyImportRepository(temp_db)
    canonical_key = "xiaomi:redmi-watch-5-active"

    is_available, reason = repo.check_cooldown(canonical_key, cooldown_days=30)

    assert is_available is True
    assert reason is None


def test_cooldown_check_recently_produced(temp_db: sqlite3.Connection):
    """Recently produced products should be blocked."""
    repo = DailyImportRepository(temp_db)

    canonical_key = compute_canonical_product_key("Xiaomi", "Redmi Watch 5 Active", None)
    product_key = compute_product_key(canonical_key)

    # Record and mark as produced
    repo.upsert_scouted_product(
        canonical_product_key=canonical_key,
        product_key=product_key,
        brand="Xiaomi",
        model="Redmi Watch 5 Active",
        variant="",
    )
    repo.mark_produced(canonical_key, cooldown_days=30)

    # Check cooldown
    is_available, reason = repo.check_cooldown(canonical_key, cooldown_days=30)

    assert is_available is False
    assert reason is not None
    assert "COOLDOWN" in reason or "RECENTLY_PRODUCED" in reason


def test_cooldown_expired(temp_db: sqlite3.Connection):
    """Products past cooldown period should be available."""
    repo = DailyImportRepository(temp_db)

    canonical_key = compute_canonical_product_key("Xiaomi", "Redmi Watch 5 Active", None)
    product_key = compute_product_key(canonical_key)

    repo.upsert_scouted_product(
        canonical_product_key=canonical_key,
        product_key=product_key,
        brand="Xiaomi",
        model="Redmi Watch 5 Active",
        variant="",
    )

    # Manually set old production date
    old_date = (datetime.now(timezone.utc) - timedelta(days=35)).isoformat()
    temp_db.execute(
        "UPDATE product_master_catalog SET status='produced', last_produced_date=?, cooldown_until=? WHERE canonical_product_key=?",
        (old_date, old_date, canonical_key),
    )

    is_available, reason = repo.check_cooldown(canonical_key, cooldown_days=30)

    assert is_available is True
    assert reason is None


def test_publish_with_gatekeeper_validation(mock_daily_run: Path, temp_db: sqlite3.Connection, tmp_path: Path):
    """Test full publish flow with gatekeeper checks."""
    inbox_root = tmp_path / "exchange_inbox"

    batch_dir = publish_daily_run_to_exchange(
        source_run_dir=mock_daily_run,
        inbox_root=inbox_root,
        batch_id="test_batch_001",
        master_catalog_conn=temp_db,
        cooldown_days=30,
        max_products=5,
    )

    # Verify READY marker
    assert (batch_dir / "READY").is_file()

    # Verify manifest
    manifest_file = batch_dir / "manifest.json"
    assert manifest_file.is_file()

    manifest_data = json.loads(manifest_file.read_text(encoding="utf-8"))
    products = manifest_data.get("products") or []

    # Should have 2 admitted products (prod_001, prod_002)
    # prod_003 rejected due to ambiguous variant "30W/65W"
    assert len(products) == 2

    product_names = [p["name"] for p in products]
    assert "Xiaomi Redmi Watch 5 Active" in product_names
    assert "Baseus Bowie WM02 Plus" in product_names

    # Verify master catalog entries
    repo = DailyImportRepository(temp_db)
    xiaomi_key = compute_canonical_product_key("Xiaomi", "Redmi Watch 5 Active", None)
    xiaomi_entry = repo.get_master_catalog_entry(xiaomi_key)

    assert xiaomi_entry is not None
    assert xiaomi_entry["status"] == "admitted"

    # Verify ambiguous variant was rejected
    ugreen_key = compute_canonical_product_key("Ugreen", "Uno GaN Charger", None)
    ugreen_entry = repo.get_master_catalog_entry(ugreen_key)
    assert ugreen_entry is not None
    assert ugreen_entry["status"] == "rejected"
    assert "AMBIGUOUS_VARIANT" in (ugreen_entry["rejection_reason"] or "")


def test_daily_limit_enforcement(mock_daily_run: Path, temp_db: sqlite3.Connection, tmp_path: Path):
    """Test max_products limit is enforced."""
    inbox_root = tmp_path / "exchange_inbox"

    batch_dir = publish_daily_run_to_exchange(
        source_run_dir=mock_daily_run,
        inbox_root=inbox_root,
        master_catalog_conn=temp_db,
        max_products=1,  # Limit to 1 product
    )

    manifest_file = batch_dir / "manifest.json"
    manifest_data = json.loads(manifest_file.read_text(encoding="utf-8"))
    products = manifest_data.get("products") or []

    # Should only admit 1 product despite having 2 valid candidates
    assert len(products) == 1


def test_deduplication_across_batches(mock_daily_run: Path, temp_db: sqlite3.Connection, tmp_path: Path):
    """Test product is blocked on second publish attempt."""
    inbox_root = tmp_path / "exchange_inbox"

    # First publish
    batch_dir_1 = publish_daily_run_to_exchange(
        source_run_dir=mock_daily_run,
        inbox_root=inbox_root,
        batch_id="batch_001",
        master_catalog_conn=temp_db,
        cooldown_days=30,
        max_products=5,
    )

    manifest_1 = json.loads((batch_dir_1 / "manifest.json").read_text(encoding="utf-8"))
    assert len(manifest_1["products"]) == 2

    # Mark first product as produced
    repo = DailyImportRepository(temp_db)
    xiaomi_key = compute_canonical_product_key("Xiaomi", "Redmi Watch 5 Active", None)
    repo.mark_produced(xiaomi_key, cooldown_days=30)

    # Second publish (same source)
    batch_dir_2 = publish_daily_run_to_exchange(
        source_run_dir=mock_daily_run,
        inbox_root=inbox_root,
        batch_id="batch_002",
        master_catalog_conn=temp_db,
        cooldown_days=30,
        max_products=5,
    )

    manifest_2 = json.loads((batch_dir_2 / "manifest.json").read_text(encoding="utf-8"))

    # Should only have 1 product now (Baseus), Xiaomi blocked by cooldown
    assert len(manifest_2["products"]) == 1
    assert manifest_2["products"][0]["brand"] == "Baseus"
