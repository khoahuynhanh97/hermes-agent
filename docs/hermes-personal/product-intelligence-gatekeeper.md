# Product Intelligence Gatekeeper & Daily Publisher

**Status:** Implemented  
**Version:** 1.0  
**Last Updated:** 2026-09-29

## Overview

The Product Intelligence Gatekeeper is an integrated quality filter and deduplication layer between the Product-Intelligence crawler and the Hermes Product Video pipeline. It enforces admission rules, tracks production history, and prevents duplicate video production within a configurable cooldown period.

## Architecture

### Design Principles

- **Extends existing infrastructure**: Built on top of `DailyImportRepository`, `ExchangeImporter`, and existing admission validation.
- **No parallel systems**: Reuses canonical contracts, workspace layout, and SQLite persistence.
- **Atomic READY publishing**: Follows established exchange inbox contract with READY marker.
- **Fail-closed validation**: Invalid products are rejected and logged, never silently admitted.

### Components

```
Product-Intelligence daily_runs/
  └── YYYY-MM-DD/products.json
            ↓
   [Gatekeeper Publisher]
     - Admission validation
     - Master catalog deduplication
     - Cooldown enforcement
     - Daily limit (max 5)
            ↓
Exchange Inbox/
  └── YYYY-MM-DD/run_XX/
      ├── manifest.json
      ├── READY
      └── products/...
            ↓
   [ProductVideoCoordinator]
     - Auto-start workflows
     - Research → Video generation
```

## Master Catalog Schema

```sql
CREATE TABLE product_master_catalog (
    canonical_product_key TEXT PRIMARY KEY,  -- brand:model[:variant]
    product_key TEXT NOT NULL,               -- SHA-256 hash
    brand TEXT NOT NULL,
    model TEXT NOT NULL,
    variant TEXT NOT NULL DEFAULT '',
    first_seen_date TEXT NOT NULL,
    last_produced_date TEXT,
    production_count INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL CHECK(status IN ('scouted', 'admitted', 'produced', 'cooldown', 'rejected')),
    cooldown_until TEXT,
    rejection_reason TEXT,
    source_url TEXT,
    raw_metadata_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

### Status Lifecycle

```
scouted → admitted → (workflow started) → produced → cooldown → (expires) → scouted
                  ↘ rejected (validation failure)
```

## Admission Rules

Products must pass **all** checks to be admitted:

### 1. Brand Identity Check
- Normalized brand name MUST appear in normalized product name
- Rejects generic names like "Tai nghe Bluetooth" without brand

### 2. Model Sanity Check
- Model must not be empty
- Model must not look like price (e.g., "100k", "2tr", "350.000đ")

### 3. Unambiguous Variant
- Rejects multi-variant bundles: `20/30W`, `32/64GB`, `X/Y`
- Pattern: `\b\d+\s*[a-zA-Z]*\s*/\s*\d+`

### 4. Image Integrity Gate
- Minimum 2 verified, readable images
- Each image must pass PIL.Image.verify()
- Prefer resolution ≥ 720x720

### 5. Cooldown Check
- Default: 30-day cooldown after production
- Blocks `canonical_product_key` duplicates
- Checks both explicit `cooldown_until` and `last_produced_date`

### 6. Daily Limit
- Maximum 5 products per published batch
- Enforced by publisher, preserves manifest priority order

## Usage

### Command Line

```powershell
# Publish latest daily run with gatekeeper
uv run python -m hermes_personal.product_video.automation.publisher \
    --source-root D:\work\Personal\Product-Intelligence\data\daily_runs \
    --inbox-root D:\work\Personal\hermes-product-video-exchange\inbox \
    --cooldown-days 30 \
    --limit 5

# Publish specific date
uv run python -m hermes_personal.product_video.automation.publisher \
    --date 2026-09-28 \
    --limit 3
```

### Automated Daily Script

```powershell
# scripts/publish_product_intelligence_daily.ps1
# Run via Windows Task Scheduler at 6:00 AM daily

.\scripts\publish_product_intelligence_daily.ps1
```

**Task Scheduler Setup:**
- Trigger: Daily at 6:00 AM
- Action: `PowerShell.exe -ExecutionPolicy Bypass -File "D:\work\hermes-upstream-rearchitecture\scripts\publish_product_intelligence_daily.ps1"`
- Run whether user is logged on or not
- Wake computer to run task

### Optional: Auto-Start Workflows

Set environment variable to automatically trigger coordinator after publishing:

```powershell
$env:HERMES_AUTO_START_AFTER_PUBLISH = "1"
.\scripts\publish_product_intelligence_daily.ps1
```

## Output Report

Publisher returns JSON report:

```json
{
  "succeeded": true,
  "batch_dir": "D:\\...\\exchange_inbox\\2026-09-29\\run_20260929_060015",
  "production_date": "2026-09-29",
  "batch_id": "run_20260929_060015",
  "total_products": 8,
  "admitted": 5,
  "rejected": 3,
  "ready": true
}
```

### Rejection Reasons

Common rejection codes:
- `COOLDOWN` / `IN_COOLDOWN_UNTIL_<date>` / `RECENTLY_PRODUCED_<date>`
- `MISSING_REQUIRED_FIELDS`
- `AMBIGUOUS_VARIANT`
- `URL_LIKE_NAME`
- `PRICE_LIKE_MODEL`
- `INSUFFICIENT_IMAGES`

## API Integration

### Python API

```python
from pathlib import Path
from hermes_personal.storage.sqlite import connect
from hermes_personal.product_video.automation.publisher import publish_daily_batch

db_path = Path("~/.hermes/hermes.db").expanduser()
conn = connect(db_path)

report = publish_daily_batch(
    source_root=Path("D:/work/Personal/Product-Intelligence/data/daily_runs"),
    inbox_root=Path("D:/work/Personal/hermes-product-video-exchange/inbox"),
    connection=conn,
    cooldown_days=30,
    max_products=5,
    target_date=None,  # Latest
)

print(f"Admitted: {report['admitted']}, Rejected: {report['rejected']}")
```

### Mark as Produced (Callback)

After successful video export, mark product as produced:

```python
from hermes_personal.product_video.automation.repository import DailyImportRepository

repo = DailyImportRepository(connection)
repo.mark_produced(
    canonical_product_key="xiaomi:redmi-watch-5-active",
    cooldown_days=30
)
```

## Repository Methods

### Gatekeeper Operations

```python
repo = DailyImportRepository(connection)

# Record discovered product
repo.upsert_scouted_product(
    canonical_product_key="xiaomi:redmi-watch-5-active",
    product_key="8f4e2c...",
    brand="Xiaomi",
    model="Redmi Watch 5 Active",
    variant="",
    source_url="https://shopee.vn/...",
    raw_metadata={...}
)

# Check cooldown before admission
is_available, reason = repo.check_cooldown("xiaomi:redmi-watch-5-active", cooldown_days=30)
if not is_available:
    repo.mark_rejected("xiaomi:redmi-watch-5-active", reason)
else:
    repo.mark_admitted("xiaomi:redmi-watch-5-active")

# After successful video production
repo.mark_produced("xiaomi:redmi-watch-5-active", cooldown_days=30)

# Query master catalog
entry = repo.get_master_catalog_entry("xiaomi:redmi-watch-5-active")
```

## Testing

```bash
# Run gatekeeper tests
uv run pytest tests/hermes_personal/product_video/test_gatekeeper_publisher.py -v

# Test scenarios covered:
# - Master catalog schema creation
# - Upsert scouted products
# - Cooldown enforcement (new, active, expired)
# - Full publish with validation
# - Daily limit enforcement
# - Deduplication across batches
```

## Monitoring & Observability

### Logs

Publisher logs are written to standard output (captured by Task Scheduler):

```
Publishing Product-Intelligence daily batch with gatekeeper...
  Source: D:\work\Personal\Product-Intelligence\data\daily_runs
  Inbox:  D:\work\Personal\hermes-product-video-exchange\inbox

✓ Daily batch published successfully

Report:
{
  "succeeded": true,
  "admitted": 5,
  "rejected": 3
}
```

### Database Queries

```sql
-- Check recent admissions
SELECT canonical_product_key, brand, model, status, created_at
FROM product_master_catalog
WHERE status = 'admitted'
ORDER BY created_at DESC
LIMIT 10;

-- Check products in cooldown
SELECT canonical_product_key, brand, model, last_produced_date, cooldown_until
FROM product_master_catalog
WHERE status = 'cooldown' AND cooldown_until > datetime('now')
ORDER BY cooldown_until;

-- Rejection statistics
SELECT rejection_reason, COUNT(*) as count
FROM product_master_catalog
WHERE status = 'rejected'
GROUP BY rejection_reason
ORDER BY count DESC;

-- Production history
SELECT canonical_product_key, brand, model, production_count, last_produced_date
FROM product_master_catalog
WHERE production_count > 0
ORDER BY last_produced_date DESC;
```

## Operational Runbook

### Daily Operations

1. **Morning Check (6:30 AM)**
   - Verify Task Scheduler ran successfully
   - Check `exchange_inbox/YYYY-MM-DD/run_XX/READY` exists
   - Review published manifest product count

2. **Workflow Start**
   - Manual: `hermes product-video start-auto --limit 5`
   - Or wait for scheduled coordinator run

3. **Monitor Rejections**
   - Query rejected products by reason
   - Investigate patterns (e.g., all from specific seller)

### Troubleshooting

**No products admitted:**
```sql
SELECT rejection_reason, COUNT(*) FROM product_master_catalog
WHERE first_seen_date = date('now') GROUP BY rejection_reason;
```

**Too many cooldowns:**
```sql
-- Manually expire cooldown for testing
UPDATE product_master_catalog
SET status = 'scouted', cooldown_until = NULL
WHERE canonical_product_key = 'xiaomi:redmi-watch-5-active';
```

**Reset master catalog (development only):**
```sql
DELETE FROM product_master_catalog;
```

## Architecture Compliance

✅ Extends `DailyImportRepository` (no parallel database)  
✅ Reuses `ExchangeImporter` validation logic  
✅ Preserves atomic READY marker pattern  
✅ SQLite-only persistence (no Redis/Kafka/RabbitMQ)  
✅ Uses canonical `compute_canonical_product_key`  
✅ Integrates with existing `ProductVideoCoordinator`  
✅ Tests against real SQLite (not mocks)  
✅ Follows `docs/README.md` authority order  

## Related Documentation

- [Product Video Master Spec](../superpowers/specs/product-video-master-spec.md)
- [Product Video Runbook](product-video-runbook.md)
- [Exchange Inbox Contract](../data-contracts.md#exchange-manifest)
- [Hermes Personal Architecture Governance](../../.agents/skills/hermes-personal-architecture-governance/SKILL.md)

## Change Log

### 2026-09-29 - Initial Implementation
- Added `product_master_catalog` table to repository schema
- Extended `DailyImportRepository` with gatekeeper methods
- Enhanced `publish_daily_run_to_exchange` with validation gates
- Created standalone `publisher.py` CLI module
- Added `publish_product_intelligence_daily.ps1` automation script
- Full test coverage (8 tests, 100% pass)
