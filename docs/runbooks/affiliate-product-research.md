# Affiliate Product Research

## Scope and prerequisites

This workflow accepts only an authorized Shopee Affiliate Product Feed or a user-exported CSV. Confirm that the Product Feed is enabled in the Shopee Affiliate portal for the account that produced the export. Hermes does not sign in to Shopee, discover feeds, scrape Shopee or TikTok pages, or download third-party media.

The import is research only. It does not purchase products, generate media, render video, publish, or schedule posts.

## Configuration

Set these environment variables in the host environment, not in source control:

```text
AFFILIATE_IMPORT_DIR=/secure/path/affiliate_imports
GOOGLE_SHEETS_ENABLED=0
GOOGLE_SHEETS_CREDENTIALS_FILE=/secure/path/google-service-account.json
GOOGLE_SHEETS_SPREADSHEET_ID=
AFFILIATE_RESEARCH_SHORTLIST_LIMIT=25
AFFILIATE_RESEARCH_PACKAGE_LIMIT=10
```

`AFFILIATE_IMPORT_DIR` defaults to `<HERMES_DATA_DIR>/affiliate_imports`. Shortlist limits must be 15 through 25; package limits must be 5 through 10. Create the import directory with host permissions restricted to the operator.

Google Sheets is disabled unless `GOOGLE_SHEETS_ENABLED=1`. Create a dedicated Google service account, share only the target workbook with that service-account email, and store its JSON key outside the repository. Point `GOOGLE_SHEETS_CREDENTIALS_FILE` at that protected file and set `GOOGLE_SHEETS_SPREADSHEET_ID`. Never commit the key, copy it into SQLite, paste it into Telegram, or add it to a run artifact.

The projection owns the canonical columns and rows in these tabs: `Products`, `Shortlist`, `Ideas`, `Scripts`, `Approval Queue`, and `Runs & Errors`. Operators may add their own columns to the right of the generated fields and may edit review notes. Do not edit stable IDs, generated canonical fields, package status, or projection rows: the next sync reconciles those from SQLite.

## CSV intake

Place an export directly under `AFFILIATE_IMPORT_DIR`; nested paths are allowed, but the resolved CSV path must remain inside that directory. The file must be UTF-8 or UTF-8-SIG, no larger than 10 MB, and contain at most 5,000 rows.

Required fields and aliases:

| Normalized field | Supported CSV columns |
| --- | --- |
| Product ID | `item_id`, `product_id`, `id` |
| Name | `product_name`, `name`, `item_name` |
| Category | `category`, `category_name` |
| Price | `price`, `price_vnd`, `product_price` |
| Product URL | `product_link`, `product_url`, `url`, `link` |

Optional aliases are `sold`/`sold_count`/`sales`, `rating`/`product_rating`, `review_count`/`reviews`/`rating_count`, `commission`/`commission_rate`/`commission_percent`, `shop_name`/`shop`/`seller_name`, `image`/`image_url`/`images`, and `visual_signals`/`visual_signal`.

## Enqueue and review

Use a unique job ID and idempotency key for each intended daily run. For example, from the Hermes Python environment:

```python
from hermes.db import Database
from hermes.jobs import JobRepository

JobRepository(Database()).enqueue(
    "affiliate-2026-08-01",
    "42",
    "affiliate_product_research",
    {
        "csv_path": "/secure/path/affiliate_imports/products-2026-08-01.csv",
        "idempotency_key": "daily-2026-08-01",
        "package_limit": 10,
        "reference_urls": [],
    },
)
```

The job's owner must match `owner_user_id` when that payload field is supplied. A same-owner, same-key retry reuses the completed canonical run; it does not import, package, or project again unless a failed projection is pending.

Telegram delivery is disabled until both `TELEGRAM_BOT_TOKEN` and `TELEGRAM_REVIEW_CHAT_ID` are set. Authorized users use the `Approve`, `Revise`, and `Reject` buttons. For a textual revision request, use `/affiliate_revise <package_id> <feedback>`. Callbacks from unauthorized users cannot change package state; repeat decisions are idempotent.

## Recovery

Validation failures, CSV paths outside the import directory, and non-retryable projection failures mark the job failed and require operator correction. Temporary Google Sheets or Telegram projection failures are recorded and requeued so the canonical SQLite run remains complete and only the pending projection is retried. Use the normal job cancellation operation for a queued or running job; cancellation is acknowledged before or after a handler run and leaves no completion result.

Do not use this workflow to scrape Shopee or TikTok, to fetch product/account pages without an authorized feed, or to download third-party video, audio, thumbnails, or other media. Reference metadata must remain reference-only and claims must retain evidence URLs and rights status.

## Offline acceptance

Run only the offline acceptance test when validating this workflow locally:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\hermes\test_affiliate_research_acceptance.py -q --basetemp .pytest-task9
```

It writes a temporary SQLite database and a 200-row CSV under the local test directory. Its deterministic gateway and explicit tripwires prevent live HTTP, LLM, Google Sheets, and Telegram calls.
