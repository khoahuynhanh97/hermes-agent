# Hermes Canonical Operations

## Runtime

The general-purpose runtime is NousResearch Hermes. Its non-secret model
configuration is:

`custom -> http://127.0.0.1:20128/v1 -> reason_combo`

9Router owns provider routing and fallback inside the logical combo. Project
code must not select individual reasoning models.

## Canonical capabilities

External Hermes loads the project-owned MCP servers:

- `hermes_product`
- `hermes_research`
- `hermes_knowledge`
- `hermes_video`

Skills are loaded from `skills/` and remain procedural guidance. Hermes owns
semantic composition; MCP servers own capability boundaries.

## Durable jobs and delivery

Use `workers/job_worker.py` for canonical deterministic job execution. Jobs
are stored by `hermes.jobs.JobRepository`; completion/failure/cancellation are
transactionally recorded as events and consumed by
`hermes.application.job_event_delivery.DeliveryConsumer`.

Inspect jobs with the Video MCP status tools or the canonical job repository.
Do not use the old `.agent_jobs` polling worker for migrated Video jobs.

## Scheduling and approvals

- Semantic recurring work: Hermes native cron.
- Deterministic maintenance: infrastructure/domain scheduler.
- Product and Knowledge approvals: application/domain lifecycle services;
  Telegram and GUI are adapters only.

## Verification

Run the relevant tests with:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Tests isolate the knowledge root in a temporary directory and do not require a
developer-specific mounted drive.
