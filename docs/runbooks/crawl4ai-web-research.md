# Crawl4AI Web Research Operations Runbook

## Overview

Hermes Agent provides an optional web document acquisition capability that allows explicit public web references to be fetched, normalized, and persisted as canonical evidence for affiliate product research runs.

Acquisition uses a **static-first, Crawl4AI-fallback** architecture. Standard HTTP requests fetch static web content first. If a dynamic JavaScript shell is detected, Crawl4AI 0.9.2 runs in headless Chromium to render the page content behind strict security and boundary policies.

---

## 1. Optional Installation & Setup

Crawl4AI is **not** included in the base `requirements.txt`. It is an optional dependency pinned in `requirements-crawl4ai.txt`.

### Installation Steps

Run the setup script from the Hermes workspace root:

```powershell
.\scripts\setup_crawl4ai.ps1
```

This script automatically:
1. Installs `requirements-crawl4ai.txt` into the Python virtual environment (`crawl4ai==0.9.2`).
2. Runs `crawl4ai-setup` to install and configure Playwright Chromium.
3. Runs `crawl4ai-doctor` to verify browser runtime health.

### Disabling / Uninstalling Crawl4AI

To disable dynamic Crawl4AI acquisition without uninstalling:
```text
CRAWL4AI_ENABLED=0
```
When disabled, Hermes operates in static HTTP mode only. Dynamic pages receive a `dynamic_content_not_rendered` warning instead of causing a worker error.

To completely uninstall Crawl4AI:
```powershell
.\.venv\Scripts\python.exe -m pip uninstall crawl4ai -y
```

---

## 2. Configuration & Environment Variables

The following environment variables configure web research behavior:

| Environment Variable | Default | Hard Maximum | Description |
| :--- | :--- | :--- | :--- |
| `CRAWL4AI_ENABLED` | `0` | `1` | Set to `1` to enable dynamic Crawl4AI fallback |
| `WEB_RESEARCH_MAX_URLS_PER_RUN` | `20` | `20` | Maximum URLs permitted per affiliate run |
| `WEB_RESEARCH_MAX_URLS_PER_HOST` | `5` | `5` | Maximum URLs permitted per domain host |
| `WEB_RESEARCH_TIMEOUT_SECONDS` | `30` | `30` | Network request timeout per URL |
| `WEB_RESEARCH_MAX_HTML_BYTES` | `2097152` | `2097152` | Max raw HTML payload size (2 MiB) |
| `WEB_RESEARCH_MAX_MARKDOWN_CHARS` | `200000` | `200000` | Max normalized Markdown length (200k chars) |

> **Note:** Hard maximums enforced in code equal global system constraints. Environment values may lower limits, but cannot raise them.

---

## 3. URL Security & SSRF Policy

Every URL must pass strict validation before fetching and after every redirect.

### Allowed URLs
- Public `http://` and `https://` schemes only.
- Ports `80` (HTTP) and `443` (HTTPS) only.
- Hostnames resolving strictly to **globally routable public IP addresses**.

### Prohibited / Blocked URLs
- Private, loopback, link-local, multicast, or reserved IPs (`127.0.0.1`, `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, `169.254.169.254`).
- Credentials embedded in URLs (`http://user:pass@example.com/`).
- Non-standard ports (e.g., `:8443`).
- Social media and marketplace hosts: `shopee.vn`, `shopee.com`, `tiktok.com`, `douyin.com`, `youtube.com`, `youtu.be`, `facebook.com`, `instagram.com`.

---

## 4. Job Payload Format

Jobs accept optional public web references under `web_references`:

```json
{
  "csv_path": "data/imports/feed.csv",
  "idempotency_key": "run-2026-08-01-001",
  "web_references": [
    {
      "external_product_id": "SKU-123",
      "url": "https://manufacturer.example.com/specs/desk-lamp",
      "source_kind": "manufacturer"
    },
    {
      "external_product_id": "SKU-123",
      "url": "https://reviewsite.example.com/desk-lamp-review",
      "source_kind": "editorial_review"
    }
  ]
}
```

Allowed `source_kind` values: `manufacturer`, `editorial_review`, `documentation`, `public_article`.

---

## 5. Storage & Evidence Ownership (SQLite V6)

All acquired web documents are stored in SQLite database schema V6:

- **`web_documents`**: Stores canonical title, Markdown body, metadata, `content_hash`, and acquisition method (`static_http` or `crawl4ai`). Unique constraint on `(owner_user_id, final_url, content_hash)`.
- **`affiliate_run_web_documents`**: Links documents to specific `run_id` and `product_id` with `source_kind`.

All records are strictly owner-isolated and content-addressed. Rerunning a job reuses existing documents by content hash without re-fetching.

---

## 6. Google Sheets Projection

When Google Sheets projection is enabled, a 7th tab named **`Web Evidence`** is synchronized with the following columns:

`stable_id`, `run_id`, `product_id`, `source_kind`, `title`, `final_url`, `acquisition_method`, `content_hash`, `rights_status`, `warnings`, `acquired_at`, `operator_notes`.

- Raw Markdown text is **not** sent to Google Sheets; SQLite remains the canonical store.
- `operator_notes` and any `custom_*` columns remain user-editable and survive resyncs.

---

## 7. Pilot Execution Guide

To test 10-20 public URLs in a controlled environment:

1. Create a JSON input file `scratch/pilot-urls.json`:
```json
{
  "urls": [
    "https://example.com/product-specs-1",
    "https://example.com/product-specs-2"
  ]
}
```

2. Run the pilot tool:
```powershell
.\.venv\Scripts\python.exe scripts\crawl4ai_pilot.py `
  --input .\scratch\pilot-urls.json `
  --output .\scratch\pilot-report.json
```

3. Inspect `scratch/pilot-report.json` to verify success rates, latencies, and output sizes.

---

## 8. Security & Upgrade Checklist

When upgrading Crawl4AI or Playwright dependencies:

- [ ] Verify `requirements-crawl4ai.txt` pins exact release version.
- [ ] Confirm no proxy, stealth mode, or raw JS injection is enabled in `Crawl4AIWebDocumentFetcher`.
- [ ] Run test suite: `pytest tests/hermes/test_crawl4ai_affiliate_acceptance.py`.
- [ ] Run `crawl4ai-doctor` to verify browser sandbox security.
