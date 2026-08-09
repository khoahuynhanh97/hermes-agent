# P4B Scheduler, Events, and Delivery Plane

## Ownership decision

- **Hermes native cron** owns recurring agent-level instructions that require
  semantic reasoning. Hermes v0.20.0 exposes `hermes cron`, durable cron jobs,
  repeat counts, attached skills, explicit schedules such as `every 1h`, and
  `cron run`/`cron runs` controls.
- **Domain infrastructure** owns deterministic maintenance such as canonical
  job lease recovery and event delivery lease recovery. These paths do not
  invoke an LLM.
- **Legacy compatibility** remains with `auto_scheduler.py`, Telegram's
  legacy outbox poller, `core.job_watcher`, and affiliate-specific workers.
- **P4B does not migrate** the existing affiliate scheduler or redesign HITL.

## Current scheduler inventory

| Component | Purpose | Ownership | Classification |
| --- | --- | --- | --- |
| Hermes `cron` | Recurring semantic agent instructions | Hermes native | CANONICAL |
| `hermes/tools/auto_scheduler.py` | Affiliate crawl rules and interval runs | Domain/legacy | MIGRATE_LATER |
| `scripts/affiliate_research_worker.py` | Poll dedicated affiliate jobs | Canonical job consumer, legacy entrypoint | KEEP_TEMPORARY |
| `scripts/run_job_worker.py` | Legacy job watcher daemon | Legacy compatibility | KEEP_TEMPORARY |
| `core/job_watcher.py` | Learning execution and Telegram completion | Legacy compatibility | STILL_REQUIRED |
| `telegram_bot.py` outbox loop | Polls legacy file outbox every 4s | Legacy delivery | KEEP_TEMPORARY |
| canonical worker/repository | Lease recovery | Domain infrastructure | CANONICAL |

## Event model

The `job_events` SQLite table is a transactional outbox with bounded fields:

`event_id`, `event_type`, `aggregate_type`, `aggregate_id`, `owner_user_id`,
`occurred_at`, `payload`, `delivery_state`, `attempt_count`, `max_attempts`,
`last_error`, `next_attempt_at`, delivery worker/lease and `delivered_at`.

Meaningful events are `job.completed`, `job.failed`, and `job.cancelled`.
Terminal job state and event insertion occur in the same SQLite transaction.
Event payloads contain bounded structured references; output paths are reduced
to file names and raw provider/error data is not copied into the event.

## Delivery model

`DeliveryConsumer` independently claims pending events with a lease and sends
through an injected adapter. `FileDeliveryAdapter` is the safe local/CLI/GUI
destination used for acceptance and is idempotent by `event_id`. The existing
`TelegramNotificationAdapter` remains available through
`TelegramEventDeliveryAdapter`; no Telegram command or approval semantics were
changed.

Delivery states are `pending`, `sending`, `delivered`, and `failed`. Stale
delivery leases return to `pending`; transient errors retry up to
`max_attempts`. Delivery failure never changes the canonical job state.

## Acceptance

Native Hermes cron job `dffdbe2c5109` ran once successfully with the
`video-production` skill and offline Video MCP, and was removed after the test.

A real Video job `828be29a-635c-4770-b7cc-14870c434fa4` completed through the
P4A worker, created event `038cce39-f774-430b-a114-7dcead1260ed`, and was
delivered once to the safe local destination. Hermes subsequently read the
completed result through Video MCP.
