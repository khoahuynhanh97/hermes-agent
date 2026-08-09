# Implementation Plan: Dedicated Affiliate Research & Crawl4AI Pipeline

**Goal:** Implement a robust 4-layer pipeline for affiliate product ingestion, Crawl4AI web reference acquisition, LLM video script generation, and Google Sheets/Telegram distribution in `hermes-agent`.

---

## Task Breakdown & Verification Steps

### Task 1: Domain Models & Public URL Security Policy
- **Files:** `hermes/domain/affiliate_research.py`, `hermes/application/web_url_policy.py`, `tests/hermes/application/test_web_url_policy.py`
- **Action:** Define domain models (`AffiliateProduct`, `WebDocument`, `AffiliateRun`) and enforce SSRF policy (validating public HTTP/HTTPS URLs, rejecting localhost/private IPs/nonstandard ports).
- **Verification:** Run `pytest tests/hermes/application/test_web_url_policy.py`.

### Task 2: Crawl4AI & Static Fetcher Adapter
- **Files:** `hermes/adapters/web/crawl4ai_adapter.py`, `hermes/application/affiliate_web_reference_service.py`, `tests/hermes/application/test_affiliate_web_reference_service.py`
- **Action:** Implement `Crawl4AIAdapter` behind `WebDocumentFetcher` port with static fetcher fallback, 30s timeout limit, and SQLite V6 `web_documents` caching.
- **Verification:** Run `pytest tests/hermes/application/test_affiliate_web_reference_service.py`.

### Task 3: LLM Content & TikTok Video Script Generator
- **Files:** `hermes/application/affiliate_content_service.py`, `hermes/adapters/model/affiliate_content_gateway.py`, `tests/hermes/application/test_affiliate_content_service.py`
- **Action:** Connect LLM Gateway via 9Router proxy to parse product info + markdown into USPs, customer pain points, 3-act TikTok video script, and Flux/Runway visual prompts.
- **Verification:** Run `pytest tests/hermes/application/test_affiliate_content_service.py`.

### Task 4: Affiliate Research Job Worker Integration
- **Files:** `scripts/affiliate_research_worker.py`, `core/affiliate_research_jobs.py`, `tests/hermes/test_affiliate_research_job.py`
- **Action:** Update worker queue loop to process pending affiliate jobs end-to-end (ingest -> fetch -> generate -> save).
- **Verification:** Run `python scripts/affiliate_research_worker.py --once`.

### Task 5: Distribution (Google Sheets & Telegram Review Notifier)
- **Files:** `hermes/adapters/telegram/affiliate_review.py`, `hermes/adapters/sheets/exporter.py`, `tests/hermes/test_telegram_affiliate_review.py`
- **Action:** Push generated runs to Google Sheets and notify user on Telegram with interactive `[Approve]`, `[Regenerate]`, `[Reject]` inline buttons.
- **Verification:** Run `pytest tests/hermes/test_telegram_affiliate_review.py`.
