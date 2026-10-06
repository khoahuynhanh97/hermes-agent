# Google Flow Render Provider Selection — Design Specification

**Status:** Single-provider contract implemented; concrete Playwright adapter remains intentionally unstarted (Task 5)  
**Date:** 2026-09-20  
**Scope:** Hermes Video Factory scene rendering only

## Decision

Product Video production has one render provider: `google_flow`. `VideoGenerationPort`
remains vendor-neutral, while Product Video composition injects one Google Flow
Playwright adapter and persists its `provider_kind` for audit/recovery. There is
no provider preference, selector, or Vertex fallback in this workflow.

This document does not claim live Google Flow support exists. Task 5 (the
concrete Playwright adapter) remains intentionally unstarted. Until it is
implemented and configured, the production composition fails closed; it does
not instantiate Vertex.

## Configuration

Behavioral configuration belongs in `config.yaml`:

```yaml
video_factory:
  render_provider: google_flow
```

`render_provider` is required and must be `google_flow`; any other configured
value fails validation. Browser credentials and session state are protected
profile state, never YAML, SQLite, logs, artifacts, or model context.

## Provider Boundary

`GoogleFlowPlaywrightProvider` will implement the existing `VideoGenerationPort`
at the Video Factory edge. `VertexVideoProvider` remains available only for
legacy/manual tooling; Product Video neither imports nor instantiates it.

The common scene result remains `VideoGenerationResult`. The Video Factory server—not either provider—validates downloaded media, persists SHA-256, composes clips, registers the canonical composite artifact, and returns the final six-field contract:

```json
{
  "owner_user_id": "...",
  "project_id": "...",
  "workflow_id": "...",
  "artifact_id": "...",
  "artifact_version": 2,
  "sha256": "..."
}
```

No provider may invent or default any of those fields.

## Durable Selection Contract

`video_factory_scene_operation` must persist at least:

- `provider_kind` (`google_flow` or `vertex_ai`);
- `provider_operation_id`;
- selection/submission state;
- the existing request digest, render batch, scene, validation contract, output path, and output SHA.

Provider pinning and transition to `submitting` are one SQLite `BEGIN IMMEDIATE`/CAS claim. The claim returns one of `claimed`, `already_claimed_same_provider`, `provider_conflict`, `invalid_state`, or `digest_conflict`; only `claimed` may call `provider.submit()`. The current operation identity remains the existing request/render-batch contract; `workflow_id` is still carried by the surrounding render batch and is not duplicated in this focused migration.

Restart behavior is determined only from the durable row:

| Durable state | Allowed action |
|---|---|
| planned, no provider selected | atomically pin `google_flow` and transition to submitting |
| selected, not submitted | submit to the pinned Google Flow provider |
| submitting, no operation ID | reconcile or pause for operator; never select fallback |
| submitted/running with operation ID | poll the pinned provider only |
| completed | validate/reuse the canonical output only |
| Google Flow unavailable | fail closed; do not submit another provider |
| terminal post-submit failure | require explicit retry policy/operator approval before a new paid attempt |
| ambiguous/timeout/login/MFA/CAPTCHA | pause for reconciliation or user action; never fall back |

## No-fallback and legacy policy

Google Flow unavailability, failure, login, MFA, CAPTCHA, timeout, and ambiguous
submission never select Vertex. A row pinned to `vertex_ai` returns
`LEGACY_PROVIDER_RECONCILIATION_REQUIRED`; it is neither polled as Flow nor
resubmitted. A row with an external operation ID but no `provider_kind` likewise
requires operator reconciliation.

`submitting` without a provider operation ID is never reported as indefinitely
`running`. The pinned provider's canonical `lookup_by_request_id()` capability
is attempted once. Before binding anything, a shared no-I/O validator requires
the exact requested `request_id`, a nonempty provider operation ID, and an
optional `metadata.provider_kind` that matches the durable provider pin. A
missing capability, unavailable provider, exception, identity mismatch, or
ambiguous result returns `RECONCILIATION_REQUIRED` without changing the
durable state or submitting any other provider. Concurrent operation-ID binds are CAS
protected: the first identity wins and a different identity cannot overwrite
it.

## Google Flow Page Object

All selectors and browser interpretation live in one page object owned by `google_flow_provider.py`. The provider must support deterministic handling of:

- prompt and reference upload;
- a single Generate action;
- accepted project/generation URL capture as `provider_operation_id`;
- running and completed states;
- downloadable MP4 ingestion into a staging location;
- terminal pre-submit failure;
- ambiguous/timeout state;
- login, MFA, and CAPTCHA as `user_action_required`.

Selectors must not appear in workflow handlers, `server.py`, or provider-selection code. Browser contexts use explicit user-managed profile/session configuration; storage state, cookies, tokens, and page secrets are never serialized to SQLite or logs.

## Integrity and Security Invariants

- Provider selection cannot change the canonical render/QC/export lineage tuple.
- Downloaded Flow media passes through the same full decode, duration, aspect-ratio, SHA, clip registration, composition, and approval invalidation path as Vertex media.
- No accepted operation is resubmitted automatically.
- No browser automation bypasses Product Lock, Brief, Scene Plan, Storyboard, or Final approval.
- No live Google Flow generation or paid Vertex call is part of the implementation test suite.
