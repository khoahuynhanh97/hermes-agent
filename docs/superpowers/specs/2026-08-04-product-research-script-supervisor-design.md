# Product Research Script Supervisor Design

## Goal

Hermes remains a personal assistant first. TikTok affiliate, marketplace
research, sheets, and script generation are supporting modules that Hermes can
choose and run when the user asks for product research.

The first workflow is:

```text
User asks for a product category, price range, and script output
  -> Hermes collects product data
  -> filters and scores products
  -> exports a reviewable sheet
  -> generates short affiliate scripts for the top products
```

Video rendering, storyboard production, voice generation, and publishing are
out of scope for this phase.

## Primary User Request

Hermes should understand requests such as:

```text
crawl ngành bàn phím, giá 200k-500k, xuất sheet rồi tạo kịch bản
```

The request maps to a `product_research_script` intent with these fields:

- `category`: product category or keyword.
- `min_price_vnd` and `max_price_vnd`: requested price range.
- `source_preference`: crawler first.
- `sheet_targets`: local sheet always, Google Sheets when configured.
- `script_style`: short affiliate review.
- `script_limit`: number of top products to generate scripts for.

When the user omits a value, Hermes uses conservative defaults:

- `min_price_vnd`: `200000`.
- `max_price_vnd`: `500000`, except keyboard-like categories may allow up to
  `1500000` through the existing product policy.
- `script_limit`: `5`.
- `shortlist_limit`: `15` to `25`, following the existing affiliate pipeline.

## Architecture

```text
Hermes Assistant
  -> Intent Router
  -> ProductResearchScriptWorkflow
      -> Source Selector
          -> Shopee crawler
          -> CSV/feed fallback
      -> Product Catalog + Policy + Scorer
      -> Local Sheet Projection
      -> Google Sheets Projection
      -> Short Script Generator
      -> Run Report
```

The assistant core owns intent routing, user-facing status, permission gates,
and final reporting. The product research workflow owns the run lifecycle and
coordinates existing affiliate modules.

## Existing Modules To Reuse

- `hermes.adapters.shopee.experimental_scraper.ShopeeExperimentalScraper`
  for category and price-based Shopee discovery.
- `hermes.adapters.shopee.playwright_scraper.ShopeePlaywrightScraper`
  as an optional browser fallback when explicitly enabled.
- `hermes.adapters.affiliate.shopee_csv.ShopeeAffiliateCsvSource`
  for CSV/feed fallback.
- `hermes.application.affiliate_catalog_service.AffiliateCatalogService`
  for import, scoring, and shortlist.
- `hermes.domain.affiliate_research.ProductPolicy` and `ProductScorer`
  for eligibility and ranking.
- `hermes.application.affiliate_content_service.AffiliateContentService`
  for generating script packages, constrained to short affiliate output.
- `hermes.adapters.google.sheets_projection.GoogleSheetsProjection`
  for optional Google Sheets sync.

## New Modules

### ProductResearchScriptWorkflow

Coordinates one run from assistant request to sheet and scripts.

Responsibilities:

- Validate and normalize category, price, and output limits.
- Enforce source gates before marketplace crawling.
- Create or resume an idempotent run.
- Collect products from the selected source order.
- Import, score, and shortlist products through existing catalog services.
- Export local sheet files.
- Sync Google Sheets when configured.
- Generate short scripts for the selected top products.
- Produce a final report with paths, run id, counts, warnings, and next steps.

### LocalSheetProjection

Writes reviewable local files even when Google Sheets is unavailable.

Required outputs:

- `Products.csv`
- `Shortlist.csv`
- `Scripts.csv`
- `Runs_Errors.csv`

Optional output:

- `product_research_run.xlsx` when an XLSX writer dependency is available.

The local sheet projection must preserve stable IDs so later Google Sheets sync
or retries can reconcile rows.

### ProductResearchIntent

A small structured command object produced by the assistant runtime.

Fields:

- `owner_user_id`
- `raw_message`
- `category`
- `keyword`
- `min_price_vnd`
- `max_price_vnd`
- `source_preference`
- `script_limit`
- `idempotency_key`

This object should be serializable so Telegram, CLI, GUI, and future web API
can enqueue the same workflow without each interface reimplementing parsing.

## Source Selection

Default order:

1. Shopee crawler.
2. CSV/feed fallback.

The crawler-first path only runs when:

- `HERMES_ENABLE_MARKETPLACE_CRAWLER=true`.
- The user request is owner-scoped.
- The requested host and category are supported.
- Price and page limits are bounded.

If the crawler is disabled, blocked, rate-limited, returns captcha, or produces
too few usable rows, Hermes keeps the run and asks the user for CSV/feed import.

CSV/feed fallback remains the preferred production-safe source because it can
include affiliate-specific fields such as commission rate.

## Permission And Risk Gates

Hermes can run these steps without further confirmation after the user requests
the workflow:

- Parse and normalize the request.
- Check configuration.
- Score imported products.
- Write local CSV/XLSX files under the configured output directory.
- Produce a run report.

Hermes must gate or explicitly require configuration before these steps:

- Marketplace crawler: requires `HERMES_ENABLE_MARKETPLACE_CRAWLER=true`.
- Playwright/browser crawler: requires a separate explicit enable flag.
- Google Sheets sync: requires configured credentials and spreadsheet id.
- LLM script generation: may run automatically only when the model provider is
  configured for assistant workflows; otherwise the sheet is still exported and
  script rows are marked `pending_generation`.

The workflow must not store Shopee cookies, passwords, session tokens, or
private media in jobs, sheets, reports, or logs.

## Short Script Output

The default script is for fast affiliate review, not video production.

Each script row contains:

- `product_id`
- `product_name`
- `rank`
- `hook_3s`
- `script_30_45s`
- `cta`
- `caption`
- `claim_warnings`
- `evidence_ids`
- `generation_status`

The script must avoid first-hand claims unless the user supplied first-hand
evidence. Price, discount, rating, sales count, and commission claims must be
grounded in the product row or explicit evidence. Missing commission data is a
warning, not a hard failure.

## Data Flow

```text
ProductResearchIntent
  -> SourceSelector.load()
  -> ProductCandidate[]
  -> AffiliateCatalogService.import_candidates()
  -> AffiliateCatalogService.score_and_shortlist()
  -> LocalSheetProjection.sync()
  -> Optional GoogleSheetsProjection.sync()
  -> ShortScriptGenerator.generate()
  -> LocalSheetProjection.sync()
  -> Optional GoogleSheetsProjection.sync()
  -> ProductResearchRunReport
```

SQLite remains the canonical run store. Local CSV/XLSX and Google Sheets are
projections for review and editing.

## Failure Handling

- Crawler blocked: record the error, keep the run, ask for CSV/feed fallback.
- Too few products: export what was found and mark the run
  `needs_more_source_data`.
- Google Sheets unavailable: keep local sheet output and record a retryable
  projection failure.
- LLM unavailable: keep product sheets and mark scripts `pending_generation`.
- Partial script failure: save successful scripts and mark failed product rows
  with an error status.
- Retry: reuse successful imported products, evidence, and scripts by stable
  run and product IDs.

## Acceptance Criteria

- A natural request for category, price range, sheet, and script routes to
  `product_research_script`.
- With crawler enabled and a fake crawler source, the workflow imports products,
  filters by price/category, shortlists products, exports local CSV files, and
  creates short script rows.
- With crawler disabled, the workflow does not call the crawler and returns a
  clear fallback request for CSV/feed.
- With Google Sheets unconfigured, the workflow still succeeds with local sheet
  output.
- With Google Sheets configured but failing, the workflow records a retryable
  projection failure without losing local output.
- With LLM unavailable, script rows are marked `pending_generation` and product
  sheets remain usable.
- Existing affiliate tests continue to pass.

## Out Of Scope

- Rendering final videos.
- Creating detailed storyboards.
- Voice generation.
- Publishing to TikTok or Shopee.
- Storing marketplace credentials or cookies.
- Bypassing anti-bot controls.
- Treating scraped public marketplace data as production-safe affiliate feed.

