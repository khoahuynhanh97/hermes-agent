from __future__ import annotations

import json
from pathlib import Path
import sqlite3

import pytest
from PIL import Image

from hermes_personal.product_video.automation.contracts import (
    ExchangeProduct,
    compute_canonical_product_key,
    compute_product_key,
)
from hermes_personal.product_video.automation.coordinator import ProductVideoCoordinator
from hermes_personal.product_video.automation.importer import (
    ExchangeImporter,
    publish_daily_run_to_exchange,
)
from hermes_personal.product_video.automation.repository import DailyImportRepository
from hermes_personal.storage.sqlite import connect


def _write_image(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (800, 800), color=(255, 255, 255)).save(path, format="PNG")


def test_canonical_product_key_strips_brand_prefix() -> None:
    key1 = compute_canonical_product_key("Baseus", "Baseus Bowie WM02")
    assert key1 == "baseus:bowie-wm02"

    key2 = compute_canonical_product_key("AULA", "F75", "Grey Wood")
    assert key2 == "aula:f75:grey-wood"

    pkey = compute_product_key(key1)
    assert len(pkey) == 64
    assert pkey == compute_product_key("baseus:bowie-wm02")


def test_exchange_importer_ignores_unready_batch(tmp_path: Path) -> None:
    inbox_root = tmp_path / "inbox"
    batch_dir = inbox_root / "2026-09-12" / "run_0001"
    batch_dir.mkdir(parents=True)

    # Only manifest, no READY file
    (batch_dir / "manifest.json").write_text("{}", encoding="utf-8")

    importer = ExchangeImporter(inbox_root)
    with pytest.raises(FileNotFoundError):
        importer.find_latest_ready_batch()

    # Now write READY
    (batch_dir / "READY").write_text("READY\n", encoding="utf-8")
    found = importer.find_latest_ready_batch()
    assert found == batch_dir


@pytest.mark.parametrize(
    ("name", "brand", "model", "reason"),
    [
        ("shopee.vn/Đồng-hồ-Huawei-GT-2-Pro", "Huawei", "GT-2", "URL or marketplace slug"),
        ("Đèn Baseus Sunshine", "Baseus", "150k", "looks like a price"),
        ("Sản phẩm công nghệ mới ra mắt", "Xiaomi", "Xiaomi 17", "does not identify brand"),
    ],
)
def test_exchange_admission_rejects_unidentified_product(
    tmp_path: Path, name: str, brand: str, model: str, reason: str
) -> None:
    product = ExchangeProduct(
        priority=1,
        canonical_product_key="candidate:key",
        product_key="candidate-key",
        name=name,
        brand=brand,
        model=model,
    )
    valid, rejection, _images = ExchangeImporter(tmp_path).validate_admission(product, tmp_path)
    assert valid is False
    assert reason in str(rejection)


def test_concurrent_claim_protection(tmp_path: Path) -> None:
    conn = connect(tmp_path / "hermes.db")
    repo = DailyImportRepository(conn)

    # Worker 1 claims product
    claim1 = repo.claim_product(
        canonical_product_key="aula:f75",
        source_date="2026-09-12",
        source_batch_id="run_1",
        source_product_id="prod_01",
        source_path="manifest.json",
        worker_id="worker-1",
    )
    assert claim1.status == "claimed"
    assert claim1.workflow_id == f"pv-daily-{compute_product_key('aula:f75')[:16]}"
    assert claim1.claimed_by == "worker-1"

    # Worker 2 attempts to claim same product while lease is active
    claim2 = repo.claim_product(
        canonical_product_key="aula:f75",
        source_date="2026-09-12",
        source_batch_id="run_1",
        source_product_id="prod_01",
        source_path="manifest.json",
        worker_id="worker-2",
    )
    assert claim2.status == "already_claimed"
    assert claim2.claimed_by == "worker-1"

    # After marking started, new claims are also rejected
    repo.mark_started(compute_product_key("aula:f75"))
    claim3 = repo.claim_product(
        canonical_product_key="aula:f75",
        source_date="2026-09-12",
        source_batch_id="run_1",
        source_product_id="prod_01",
        source_path="manifest.json",
        worker_id="worker-3",
    )
    assert claim3.status == "already_started"


def test_coordinator_auto_start_preserves_manifest_priority(tmp_path: Path) -> None:
    # Build exchange batch
    src_run = tmp_path / "src_run"
    src_run.mkdir()
    # Six products prove the daily cap across repeated scheduler calls.
    prods = []
    for i in range(1, 7):
        name, model = f"Zippo {i}", f"M{i}"
        img = src_run / "images" / f"ig{i}" / "img1.png"
        _write_image(img)
        img2 = src_run / "images" / f"ig{i}" / "img2.png"
        _write_image(img2)
        prods.append({
            "id": f"prod{i}",
            "name": name,
            "brand": "Zippo",
            "model": model,
            "price_display": "100.000đ",
            "price_min": 100000,
            "price_max": 100000,
            "hot_reason": "Hot",
            "key_features": "Features",
            "keywords": [name],
            "images": [
                {"asset_id": f"a1{i}", "absolute_path": str(img), "match_score": 1.0, "width": 800, "height": 800},
                {"asset_id": f"a2{i}", "absolute_path": str(img2), "match_score": 1.0, "width": 800, "height": 800},
            ],
        })
    (src_run / "products.json").write_text(
        json.dumps({"version": "1.0", "date": "2026-09-12", "products": prods}),
        encoding="utf-8",
    )

    inbox = tmp_path / "exchange_inbox"
    publish_daily_run_to_exchange(src_run, inbox, batch_id="run_01")

    conn = connect(tmp_path / "hermes.db")
    coordinator = ProductVideoCoordinator(connection=conn, inbox_root=inbox)

    # Start auto with limit 2
    res = coordinator.start_auto(limit=2)
    assert len(res.started) == 2
    # Preserves manifest priority 1 and 2
    assert res.started[0]["canonical_product_key"] == "zippo:m1"
    assert res.started[1]["canonical_product_key"] == "zippo:m2"

    # List candidates shows zippo:m1 and zippo:m2 in_production, zippo:m3 unprocessed
    candidates = coordinator.list_candidates()
    status_map = {c.canonical_product_key: c.status for c in candidates}
    assert status_map["zippo:m1"] == "in_production"
    assert status_map["zippo:m2"] == "in_production"
    assert status_map["zippo:m3"] == "unprocessed"

    top_up = coordinator.start_auto(limit=5)
    assert [item.canonical_product_key for item in top_up.started] == [
        "zippo:m3", "zippo:m4", "zippo:m5"
    ]
    assert coordinator.start_auto(limit=5).started == ()
    assert coordinator.list_candidates()[-1].status == "unprocessed"


def test_coordinator_write_time_revalidation_skips_stale_or_invalid(tmp_path: Path) -> None:
    src_run = tmp_path / "src_run"
    src_run.mkdir()
    img = src_run / "img1.png"
    _write_image(img)
    (src_run / "products.json").write_text(
        json.dumps({
            "version": "1.0",
            "date": "2026-09-12",
            "products": [
                {
                    "id": "p1",
                    "name": "Sample P",
                    "brand": "Sample",
                    "model": "P1",
                    "price_display": "100đ",
                    "features": "F",
                    "keywords": ["s"],
                    "images": [{"asset_id": "a", "absolute_path": str(img), "match_score": 1.0}],
                }
            ],
        }),
        encoding="utf-8",
    )
    inbox = tmp_path / "exchange_inbox"
    publish_daily_run_to_exchange(src_run, inbox, batch_id="run_02")

    conn = connect(tmp_path / "hermes.db")
    coordinator = ProductVideoCoordinator(connection=conn, inbox_root=inbox)

    # Try starting with non-existent key
    res = coordinator.start_selection(["non_existent_key"])
    assert len(res.started) == 0
    assert len(res.skipped) == 1
    assert res.skipped[0]["reason"] == "NOT_FOUND_IN_MANIFEST"


def test_top_level_cli_personal_video(tmp_path: Path, capsys, monkeypatch) -> None:
    import sys
    from hermes_cli.main import main

    src_run = tmp_path / "src_run"
    src_run.mkdir()
    img = src_run / "img1.png"
    _write_image(img)
    img2 = src_run / "img2.png"
    _write_image(img2)
    (src_run / "products.json").write_text(
        json.dumps({
            "version": "1.0",
            "date": "2026-09-12",
            "products": [
                {
                    "id": "p1",
                    "name": "Super Mouse",
                    "brand": "Super",
                    "model": "M1",
                    "price_display": "200.000đ",
                    "features": "Fast",
                    "keywords": ["mouse"],
                    "images": [
                        {"asset_id": "a1", "absolute_path": str(img), "match_score": 1.0},
                        {"asset_id": "a2", "absolute_path": str(img2), "match_score": 1.0},
                    ],
                }
            ],
        }),
        encoding="utf-8",
    )
    inbox = tmp_path / "exchange_inbox"
    publish_daily_run_to_exchange(src_run, inbox, batch_id="run_03")

    db_path = tmp_path / "hermes.db"

    # Test hermes personal video list
    monkeypatch.setattr(sys, "argv", [
        "hermes", "personal", "video",
        "--db-path", str(db_path),
        "--inbox-root", str(inbox),
        "list",
    ])
    code = main()
    assert code is None or code == 0
    out = capsys.readouterr().out
    assert "Super Mouse" in out
    assert "[CHƯA TẠO VIDEO]" in out


LEGACY_LEDGER_DDL = """
CREATE TABLE daily_product_video_import (
    product_key TEXT PRIMARY KEY,
    source_date TEXT NOT NULL,
    source_product_id TEXT NOT NULL,
    source_path TEXT NOT NULL,
    workflow_id TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL CHECK(status IN ('reserved', 'started', 'error')),
    last_error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    canonical_product_key TEXT NOT NULL DEFAULT '',
    source_batch_id TEXT NOT NULL DEFAULT '',
    worker_id TEXT,
    claimed_at TEXT,
    lease_expires_at TEXT
);
"""


def test_legacy_ddl_migration_and_claim_preserves_history(tmp_path: Path) -> None:
    db_file = tmp_path / "hermes_legacy.db"
    raw_conn = sqlite3.connect(db_file)
    raw_conn.executescript(LEGACY_LEDGER_DDL)

    legacy_rows = [
        (
            "1e96ac740ec2f41f35a92194ca77c69fa3249fd103fc4e792321eca63eafd38b",
            "2026-09-12",
            "prod_01",
            r"D:\work\Personal\Product-Intelligence\data\daily_runs\2026-09-12\products.json",
            "pv-daily-1e96ac740ec2f41f",
            "started",
            None,
            "2026-09-12T09:13:44.033665+00:00",
            "2026-09-12T09:13:44.035194+00:00",
            "",
            "",
            None,
            None,
            None,
        ),
        (
            "c56349cc02be2276d5578a1c3b081b4a6349ff4bba199d19c355ef838b3adff3",
            "2026-09-12",
            "prod_02",
            r"D:\work\Personal\Product-Intelligence\data\daily_runs\2026-09-12\products.json",
            "pv-daily-c56349cc02be2276",
            "started",
            None,
            "2026-09-12T09:13:44.037251+00:00",
            "2026-09-12T09:13:44.037251+00:00",
            "",
            "",
            None,
            None,
            None,
        ),
        (
            "1dd69d4052bfb08a68fe47e13e0d73535f50d9a1d487fa4b307cb9d42930c8c8",
            "2026-09-12",
            "prod_06",
            r"D:\work\Personal\Product-Intelligence\data\daily_runs\2026-09-12\products.json",
            "pv-daily-1dd69d4052bfb08a",
            "started",
            None,
            "2026-09-12T09:13:44.047127+00:00",
            "2026-09-12T09:13:44.047127+00:00",
            "",
            "",
            None,
            None,
            None,
        ),
    ]
    raw_conn.executemany(
        """
        INSERT INTO daily_product_video_import VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        legacy_rows,
    )
    raw_conn.commit()
    raw_conn.close()

    # Open with central connect, which should perform migration
    conn = connect(db_file)
    repo = DailyImportRepository(conn)

    # Claim a new product for 2026-09-13
    claim = repo.claim_product(
        canonical_product_key="jisulife:life-7",
        source_date="2026-09-13",
        source_batch_id="run_20260913_000105",
        source_product_id="prod_jisulife",
        source_path="manifest.json",
        worker_id="worker-test",
    )
    assert claim.status == "claimed", f"Claim failed: {claim.error}"

    # Verify legacy rows preserved byte-for-byte
    rows_0912 = conn.execute(
        "SELECT product_key, status, created_at, workflow_id FROM daily_product_video_import WHERE source_date = '2026-09-12' ORDER BY source_product_id"
    ).fetchall()
    assert len(rows_0912) == 3
    assert rows_0912[0]["workflow_id"] == "pv-daily-1e96ac740ec2f41f"
    assert rows_0912[0]["status"] == "started"
    assert rows_0912[1]["workflow_id"] == "pv-daily-c56349cc02be2276"
    assert rows_0912[2]["workflow_id"] == "pv-daily-1dd69d4052bfb08a"

    # Idempotency check: rerun migration does not alter data or fail
    from hermes_personal.storage.sqlite import _migrate_daily_product_video_import
    _migrate_daily_product_video_import(conn)
    rows_after = conn.execute("SELECT COUNT(*) FROM daily_product_video_import").fetchone()[0]
    assert rows_after == 4  # 3 legacy + 1 new claimed


def test_migration_failure_rolls_back_safely(tmp_path: Path) -> None:
    db_file = tmp_path / "hermes_rollback.db"
    raw_conn = sqlite3.connect(db_file)
    raw_conn.executescript(LEGACY_LEDGER_DDL)
    raw_conn.execute(
        """
        INSERT INTO daily_product_video_import (
            product_key, source_date, source_product_id, source_path, workflow_id, status, created_at, updated_at
        ) VALUES ('key1', '2026-09-12', 'p1', 'path', 'wf1', 'started', '2026-09-12T00:00:00', '2026-09-12T00:00:00')
        """
    )
    raw_conn.commit()

    from hermes_personal.storage.sqlite import _migrate_daily_product_video_import

    class FailingConnection:
        def __init__(self, conn: sqlite3.Connection) -> None:
            self._conn = conn
        def execute(self, sql: str, *args, **kwargs):
            if "DROP TABLE daily_product_video_import" in sql:
                raise sqlite3.OperationalError("Simulated drop failure")
            return self._conn.execute(sql, *args, **kwargs)
        def __enter__(self):
            return self._conn.__enter__()
        def __exit__(self, *args):
            return self._conn.__exit__(*args)
        def __getattr__(self, name: str):
            return getattr(self._conn, name)

    proxy = FailingConnection(raw_conn)

    with pytest.raises(sqlite3.OperationalError, match="Simulated drop failure"):
        with raw_conn:
            _migrate_daily_product_video_import(proxy)

    # Verify original table is intact
    count = raw_conn.execute("SELECT COUNT(*) FROM daily_product_video_import").fetchone()[0]
    assert count == 1
    raw_conn.close()


def test_coordinator_enforces_hard_daily_bound_of_five(tmp_path: Path) -> None:
    conn = connect(tmp_path / "hermes_limit.db")
    coord = ProductVideoCoordinator(conn, inbox_root=tmp_path / "inbox")

    with pytest.raises(ValueError, match="Limit must be between 1 and 5"):
        coord.start_auto(limit=0)

    with pytest.raises(ValueError, match="Limit must be between 1 and 5"):
        coord.start_auto(limit=6)

    with pytest.raises(ValueError, match="Cannot select more than 5 products"):
        coord.start_selection(["k1", "k2", "k3", "k4", "k5", "k6"])

