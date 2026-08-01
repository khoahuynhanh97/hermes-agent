# Task 8 Report: Telegram Package Review And Revision Feedback

Status: DONE

## Changed Files

- `hermes/application/affiliate_review_service.py`
  - Adds owner-scoped `AffiliateReviewService` over canonical, idempotent repository transitions.
  - Maps missing owner-scoped packages to `PackageNotFound`.
- `hermes/adapters/telegram/affiliate_review.py`
  - Adds safe HTML renderer, compact callback parser/keyboard builder, and injected-bot `TelegramReviewDelivery`.
  - Transport errors return retryable `ProjectionResult` failures.
- `telegram_bot.py`
  - Adds lazy dependency factories, authorized affiliate callback handling, `/affiliate_revise`, and command registration.
  - Does not create affiliate persistence, model clients, credentials, or network connections at import time.
- `tests/hermes/test_telegram_affiliate_review.py`
  - Covers lifecycle idempotency and owner scope, HTML escaping, callback length, delivery transport failure, callback authorization, and revision feedback.

## Verification

Exact command:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\hermes\test_telegram_affiliate_review.py tests\hermes\test_telegram_authorization.py tests\hermes\test_telegram_memory.py -q
```

Result:

```text
15 passed in 0.96s
```

No live Telegram or network calls were made.

## Commit

`feat: review affiliate packages in Telegram`

## Concerns

- `git diff --check` reports existing trailing whitespace in unrelated `gui/app.py`; it was not modified.
- The canonical content package model does not expose a product score breakdown. The Telegram renderer uses `angle_reason` as the score-reason fallback.

## Follow-up Fix: Production Delivery Wiring

`review_delivery_from_environment` now returns `DisabledReviewDelivery` unless both
`TELEGRAM_BOT_TOKEN` and `TELEGRAM_REVIEW_CHAT_ID` are configured. When configured,
it creates the injected Telegram bot only inside the factory and returns
`TelegramReviewDelivery`. `build_affiliate_research_job_handler` injects that delivery
into the production `AffiliateRunService` composition.

Focused tests cover the disabled default, configured fake-bot construction, and job
handler injection without real Telegram or network access.

Exact verification command:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\hermes\test_telegram_affiliate_review.py tests\hermes\test_telegram_authorization.py tests\hermes\test_telegram_memory.py -q
```

Result:

```text
18 passed in 0.98s
```
