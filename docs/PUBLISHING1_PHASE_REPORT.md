# Publishing1 — TikTok Integration — PHASE REPORT

**Status**: ✅ **PARTIAL PASS** (implementation + mock tests pass; LIVE BLOCKED by external resources)

---

## Implemented

- `hermes/domain/publisher.py` — `Publication` + `PublicationStatus` (not_published/uploading/processing/published/failed)
- `hermes/ports/publisher.py` — `PublisherPort`, `PublishRequest/PublishResult`, `PublicationStore`
- `providers/tiktok_publisher.py` — `TikTokPublisher` (Content Posting API Direct Post flow: video/init FILE_UPLOAD → PUT upload_url → status/fetch) + `authorize_url`, `exchange_code`, `refresh_token` helpers. All mockable.
- `hermes/adapters/sqlite/publisher_repository.py` + `schema_v13` (`publications` table, owner-scoped, one row per project+platform)
- `video_factory_api.py` — `POST /publish` (explicit, requires ready_to_publish), `GET /publication`, `GET /auth/tiktok` (returns OAuth authorize URL)
- UI: "9. Publish to TikTok" card (caption, status, Publish button, Refresh status)

## Live acceptance

**BLOCKED** — requires user-provisioned external resources (not code-able, not created by me):
- TikTok developer app: client key + client secret
- Redirect URI (https, registered)
- Content Posting API + Direct Post + `video.publish` scope
- User OAuth authorization (creator consents)
- App audit for public posts (unaudited clients post private-only)

## Files changed

- `hermes/db.py`, `hermes/adapters/sqlite/schema_v13.py`
- `hermes/domain/publisher.py`, `hermes/ports/publisher.py`
- `hermes/adapters/sqlite/publisher_repository.py`
- `providers/tiktok_publisher.py`
- `video_factory_api.py`
- `web/src/features/video-factory/VideoFactoryPage.tsx`
- `docs/research/2026-08-07-tiktok-content-posting-api.md`
- `tests/hermes/test_publishing1.py`

## Tests

- **6/6 Publishing1 tests** (all HTTP mocked, fail-fast guard blocks real TikTok):
  - requires access token
  - init→upload flow (post_id)
  - API error (audit-required)
  - publication store roundtrip/update
  - API publish requires ready_to_publish (no auto-publish)
  - authorize URL construction
- **49/49** focused regression | `npm run build` PASS | `py_compile` PASS | `git diff --check` clean
- DB migration v13 verified (fresh + upgrade, data intact)

## Simplicity review

- ✅ No new Agent/MCP/scheduler/global-store
- ✅ Reused existing API/UI patterns, `vertex` untouched
- ✅ No fallback provider
- ✅ Publish is explicit-only; no auto-publish
- ✅ One provider (TikTok only)

## Remaining blocker

Live publish + token exchange need TikTok app credentials + user OAuth authorization (external).

## Next evidence-backed step

To enable live: user provisions TikTok developer app + authorizes. Then run live acceptance: `Publish to TikTok` on the existing ready_to_publish fixture, verify post_id + status/fetch.
