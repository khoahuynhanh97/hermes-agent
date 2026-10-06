# Implementation Plan: Playwright-First Browser Flow for Hermes Personal Product Video

**Status:** Proposed / Awaiting Review  
**Author:** DeepMind Antigravity / Hermes Personal Team  
**Date:** 2026-09-19  
**Specification Reference:** [docs/superpowers/specs/2026-09-19-product-video-playwright-first-browser-flow.md](file:///d:/work/hermes-upstream-rearchitecture/docs/superpowers/specs/2026-09-19-product-video-playwright-first-browser-flow.md)  

---

## 1. Plan Overview

This plan details the step-by-step implementation of the Playwright-first browser navigation and evidence capture adapter for the Hermes Personal Product Video pipeline, while strictly maintaining the existing Vertex AI Gemini & Veo generation workflows and SQLite durability invariants.

---

## 2. Implementation Tasks

### Task 1: Durable Browser Capture Contracts & SQLite Repository
- **Files:**
  - `hermes_personal/product_video/browser/contracts.py` (NEW)
  - `hermes_personal/product_video/browser/repository.py` (NEW)
  - `tests/hermes_personal/product_video/browser/test_contracts_and_repo.py` (NEW)
- **Work:**
  - Define `BrowserCaptureRequest`, `BrowserCaptureResult`, `BrowserEvidenceArtifact`, and status enums.
  - Implement `BrowserCaptureRepository` backed by SQLite tables: `product_video_browser_captures` and `product_video_browser_artifacts`.
  - Enforce foreign key constraints, JSON serialization, and unique index on `(workflow_id, capture_id)`.

### Task 2: Playwright MCP Edge Adapter
- **Files:**
  - `hermes_personal/product_video/browser/adapter.py` (NEW)
  - `tests/hermes_personal/product_video/browser/test_playwright_adapter.py` (NEW)
- **Work:**
  - Implement `PlaywrightBrowserAdapter` supporting `capture_pdp(request)` with isolated browser context per execution.
  - Implement selector wait, DOM snapshot, full-page screenshot, and media extraction.
  - Detect login forms / CAPTCHAs and return `BLOCKED_FOR_LOGIN` / `BLOCKED_CAPTCHA` without crashing.

### Task 3: Workspace Ingestion, Hashing, & Containment
- **Files:**
  - `hermes_personal/product_video/browser/ingestion.py` (NEW)
  - `tests/hermes_personal/product_video/browser/test_ingestion_containment.py` (NEW)
- **Work:**
  - Implement `BrowserMediaIngestionService` which streams remote media into staging, verifies byte size, computes SHA256, and moves atomically into `workspace/references/`.
  - Enforce `ProductVideoWorkspaceLayout.resolve_path()` containment check; reject path traversal attempts (`../`, absolute paths outside workspace).

### Task 4: Workflow & Outbox Wiring
- **Files:**
  - `hermes_personal/product_video/handlers.py` (MODIFY)
  - `hermes_personal/product_video/workflow.py` (MODIFY)
  - `tests/hermes_personal/product_video/test_browser_workflow_wiring.py` (NEW)
- **Work:**
  - Add `ProductVideoWorkflowState.DISCOVERING_SOURCES` before `BUILDING_RESOURCE_PACK` in workflow state enum and transition matrix.
  - Wire `product_video.discover_sources` job handler to invoke `PlaywrightBrowserAdapter` and save evidence to `latest_artifact`.
  - Pass ingested evidence artifacts to `MCPProductIntelligenceAdapter.build_resource_pack()`.

### Task 5: Restart & Idempotency Recovery
- **Files:**
  - `hermes_personal/product_video/browser/adapter.py` (MODIFY)
  - `tests/hermes_personal/product_video/browser/test_browser_recovery.py` (NEW)
- **Work:**
  - Compute action key from `sha256(workflow_id + target_url + wait_selector)`.
  - On worker restart, query `BrowserCaptureRepository`; if matching capture is `completed`, return cached result immediately without launching browser.

### Task 6: Security & Query/Header Redaction
- **Files:**
  - `hermes_personal/product_video/browser/sanitization.py` (NEW)
  - `tests/hermes_personal/product_video/browser/test_sanitization.py` (NEW)
- **Work:**
  - Implement `sanitize_url()` to strip sensitive query parameters (`token`, `auth`, `key`, `signature`, `session_id`).
  - Sanitize HTTP headers to ensure no cookies or credentials are saved to database or logged.
  - Wrap extracted text in structured JSON tagged `untrusted_web_evidence`.

### Task 7: Deterministic Unit Tests
- **Files:**
  - `tests/hermes_personal/product_video/browser/` (NEW suite)
- **Work:**
  - Test all error paths: `BROWSER_TIMEOUT`, `NAVIGATION_FAILED`, `BLOCKED_FOR_LOGIN`, `BLOCKED_CAPTCHA`, `CONTAINMENT_VIOLATION`.
  - Test mock browser execution with simulated DOM and fixture images.

### Task 8: One Playwright Production-Path E2E with Local Fixture Website
- **Files:**
  - `tests/hermes_personal/product_video/test_playwright_e2e.py` (NEW)
- **Work:**
  - Create a lightweight `http.server` fixture serving a mock PDP page with product images, specs, and claims.
  - Run the complete production path from URL -> Playwright Capture -> Ingestion -> Resource Pack -> Product Lock -> Gemini Brief -> Gemini Storyboard -> Veo Render -> QC -> Export.

### Task 9: Vertex AI Regression Verification
- **Files:**
  - `tests/hermes_personal/product_video/test_vertex_preservation_regression.py` (NEW)
- **Work:**
  - Verify that `VertexVideoProvider`, `predictLongRunning`, operation checkpointing, polling, and `ProductVideoQCService` are 100% identical and undisturbed.
  - Verify zero Veo re-submissions on workflow retry.

### Task 10: Documentation & Runbook Updates
- **Files:**
  - `docs/hermes-personal/product-video-runbook.md` (MODIFY)
  - `docs/known-gaps.md` (MODIFY)
- **Work:**
  - Document `product_video.browser_capture` configuration options and troubleshooting steps for Playwright.
  - Update runbook with operator steps when browser reports `BLOCKED_FOR_LOGIN`.

---

## 3. Test Matrix

| Test Suite | Scenario Covered | Expected Result |
|---|---|---|
| `test_contracts_and_repo.py` | Save / load capture records and evidence artifacts | Exact SQLite persistence, round-trip serialization |
| `test_playwright_adapter.py` | Navigation, timeout, selector wait, login detection | Status `completed`, `blocked_for_login`, or `failed` |
| `test_ingestion_containment.py` | Media streaming, SHA256 computation, path traversal rejection | File written to workspace with correct hash; traversal raises error |
| `test_browser_workflow_wiring.py` | State transitions through `DISCOVERING_SOURCES` | Outbox dispatches `product_video.discover_sources` cleanly |
| `test_browser_recovery.py` | Process restart after capture completion | Browser is NOT relaunched; cached result returned |
| `test_sanitization.py` | URL query token redaction, header scrubbing | Sensitive params replaced with `[REDACTED]` |
| `test_playwright_e2e.py` | Full pipeline with local HTTP fixture server | Real MP4 exported with verified lineage from browser capture |
| `test_vertex_preservation_regression.py` | Veo generation & Gemini QC compatibility | 0 API regressions; provider port contract preserved |

---

## 4. Key Assumptions & Decisions Requiring Confirmation

1. **Browser Engine**: Playwright Chromium in headless mode is the default engine.
2. **Local Staging**: Downloaded images and screenshots are stored under `<workspace>/references/<capture_id>/` with content-addressed SHA256 filenames.
3. **Untrusted Content Handling**: Text scraped from web pages is passed to Gemini as passive reference data (`untrusted_web_evidence`) to prevent prompt injection.
4. **Vertex Provider Invariance**: `VertexVideoProvider` and `MultimodalEvaluator` interfaces remain completely unchanged.

---

## 5. Risks & Blockers

- **Playwright Installation on Host**: Playwright Chromium binaries must be available (`npx playwright install chromium`). If absent, the system fails gracefully with `PLAYWRIGHT_NOT_INSTALLED` and alerts the operator.
- **Strict Lineage Prerequisite**: Export strictly requires the 6-tuple lineage (`owner_user_id`, `project_id`, `workflow_id`, `artifact_id`, `artifact_version`, `sha256`) established in Task 4. Any browser-discovered asset must properly register its lineage into the Resource Pack before reaching Video QC.
