# TikTok Content Posting API research for Hermes

Date: 2026-08-07

Scope: official TikTok for Developers (developers.tiktok.com) documentation only, fetched directly from developers.tiktok.com and open.tiktokapis.com referenced docs. No third-party write-ups. Where a doc is ambiguous or silent, that is stated explicitly. All claim URLs are official doc pages.

## Executive conclusion

Hermes should use the **Content Posting API - Direct Post** flow for a personal, single-account project:

1. Register a developer app at developers.tiktok.com (personal developer account is fine for a single user).
2. Add the Content Posting API product, enable **Direct Post** configuration, add the `video.publish` scope (and `user.info.basic` for profile display if needed).
3. User authorizes via the OAuth 2.0 Authorization Code flow → get `access_token` (24 h) + `refresh_token` (365 days, rotating).
4. Post: `creator_info/query/` → `video/init/` (`FILE_UPLOAD` or `PULL_FROM_URL`) → PUT video to returned `upload_url` → poll `status/fetch/`.

Required provisioning from the user (cannot be done by code): TikTok developer account, registered app, **Client key + Client secret**, **redirect URI**, verified **URL property** (only if using `PULL_FROM_URL`), app review submission for `video.publish` scope, and (to lift the private-viewing restriction) a **client audit**.

Two constraints matter for a personal project:

- **No audit = private posts only.** "All content posted by unaudited clients will be restricted to private viewing mode." This is enforced with error `unaudited_client_can_only_post_to_private_accounts` and confirmed in the App Review FAQ. To post publicly visible content the API client must pass a TikTok audit.
- **Sandbox mode does not include Content Posting for public videos.** "Sandbox mode does not offer access to Content Posting API for public videos or Data Portability API." So testing posting realistically requires a Production app (draft/in-review) rather than a sandbox.

No newer/alternative posting API exists. The current product is the Content Posting API (launched Apr 2023, Direct Post added Jun 2023, photos Nov 2023). The predecessor "Share Video API" (`open-api.tiktok.com/share/video/upload/` and `.../publish/`) is deprecated and sunset on 2023-09-10.

---

## 1. Available publishing APIs and current status

All current Content Posting endpoints live under `https://open.tiktokapis.com/v2/post/publish/`. There is **no** current `POST /video/publish/` endpoint; the direct-post endpoint is `POST /v2/post/publish/video/init/`. The old `/share/video/publish/` and `/share/video/upload/` endpoints belong to the deprecated Share Video API (sunset 2023-09-10).

| Flow | Endpoint (HTTP) | Scope | Publish model |
|---|---|---|---|
| Direct Post video init | `POST /v2/post/publish/video/init/` | `video.publish` | Posts directly to profile |
| Direct Post video upload | `PUT {upload_url}` returned by init | (same token) | Chunked/whole file PUT |
| Upload-to-inbox (draft) init | `POST /v2/post/publish/inbox/video/init/` | `video.upload` | Video lands in user inbox; user must finish post in TikTok app |
| Upload-to-inbox upload | `PUT {upload_url}` returned by init | (same token) | Chunked/whole file PUT |
| Query Creator Info | `POST /v2/post/publish/creator_info/query/` | `video.publish` | Fetch privacy/UX options before posting |
| Get Post Status | `POST /v2/post/publish/status/fetch/` | `video.upload`/`video.publish` | Poll `publish_id` |
| Cancel ongoing pull | `POST /v2/post/publish/cancel/` | video scopes | Best-effort cancel of `PULL_FROM_URL` |
| Photo post/upload | `POST /v2/post/publish/content/init/` | `video.publish`/`video.upload` | Photos only, `post_mode` + `media_type` required |

Sources:
- Direct Post get-started: https://developers.tiktok.com/doc/content-posting-api-get-started/
- Direct Post reference: https://developers.tiktok.com/doc/content-posting-api-reference-direct-post/
- Upload reference: https://developers.tiktok.com/doc/content-posting-api-reference-upload-video/
- Get Post Status reference: https://developers.tiktok.com/doc/content-posting-api-reference-get-video-status/
- Query Creator Info reference: https://developers.tiktok.com/doc/content-posting-api-reference-query-creator-info/
- Changelog (product history, no posting deprecations): https://developers.tiktok.com/doc/changelog/
- Deprecated Share Video API: https://developers.tiktok.com/doc/web-video-kit-with-web/

Deprecation facts from the legacy page: "This Share Video API is now deprecated and will sunset on September 10th, 2023. Please migrate to our Content Posting API immediately." Changelog: Video Kit for Web (Share Video API) deprecation + Content Posting API launch announced 2023-04-27; Direct Post API live 2023-06-07; photo support 2023-11-03. No Content Posting API endpoint deprecation appears in the changelog as of this research date.

## 2. OAuth 2.0 requirements

**Flow: Authorization Code (server-side web app).** The docs' web integration expects a server that holds `client_secret` and `refresh_token`, creates an anti-CSRF `state`, redirects the browser to TikTok, exchanges the returned `code`, and refreshes tokens in the background.

- **Authorize URL:** `https://www.tiktok.com/v2/auth/authorize/` with `client_key`, `response_type=code`, `scope` (comma-separated), `redirect_uri`, `state`. Legacy clients on `https://www.tiktok.com/auth/authorize/` must migrate. HTTPS only.
- **Token exchange:** `POST https://open.tiktokapis.com/v2/oauth/token/`, `Content-Type: application/x-www-form-urlencoded`, params `client_key`, `client_secret`, `code` (URL-decoded), `grant_type=authorization_code`, `redirect_uri` (must exactly match the one used to request the code). `code_verifier` is required **for mobile/desktop apps only** (PKCE), not for web.
- **Credentials:** Client key and Client secret are in the app's Credentials section on the developer portal. Secret must be stored server-side.
- **Redirect URI rules (Login Kit web):** must be registered in the app's product configuration; absolute, `https`, static (no query params), no `#` fragment, < 512 chars, max 10 URIs per app. For web apps this URI is required and must be provided at app review time.
- **Token lifetime:** `access_token` valid **24 hours** (`expires_in: 86400`); `refresh_token` valid **365 days** (`refresh_expires_in: 31536000`). User access tokens can be extended to a **maximum of one year** (App Review FAQ).
- **Refresh:** same token endpoint with `grant_type=refresh_token` + `client_key`, `client_secret`, `refresh_token`. Refresh tokens are **rotating** — use the newly returned `refresh_token` if it differs. No user consent needed to refresh; run background jobs to keep tokens alive.
- **Revoke:** `POST https://open.tiktokapis.com/v2/oauth/revoke/` with `client_key`, `client_secret`, `token`.

Required scopes for publishing (from the Scopes Reference):

- `video.publish` — "Directly post content to a user's TikTok profile." Used by Direct Post, Query Creator Info, Get Post Status.
- `video.upload` — "Share content to creator's account as a draft to further edit and post in TikTok." Used by Upload, Get Post Status, (legacy Share Video API).
- `video.list` — read-only; lists/queries a user's public videos. **Not required for posting.**
- `user.info.basic` — read profile info; useful for display but not required for posting.

Client access tokens (`grant_type=client_credentials`, 2-hour tokens) are documented **only** for Research API and Commercial Content API — not usable for content posting, which requires a user access token.

Sources:
- OAuth user token management: https://developers.tiktok.com/doc/oauth-user-access-token-management/
- Client token management: https://developers.tiktok.com/doc/client-access-token-management/
- Login Kit web (authorization URL + redirect URI rules): https://developers.tiktok.com/doc/login-kit-web/
- Scopes reference: https://developers.tiktok.com/doc/tiktok-api-scopes/
- App Review FAQ (token length, review process): https://developers.tiktok.com/doc/getting-started-faq/

## 3. Creator authorization

Flow: the user opens the authorize URL in a browser → logs in to TikTok → TikTok shows a consent page listing the app name/description and the scopes being requested → on approval TikTok redirects to `redirect_uri` with `code`, `scopes`, `state` (plus `error`/`error_description` on denial) → server exchanges the code for tokens.

- Consent is **per-user, one-time** for the token grant; afterwards the `refresh_token` keeps the grant alive without re-prompting, up to 365 days (extendable to 1 year per FAQ).
- "Long-lived" is achieved by refresh-token rotation, not by issuing a permanent access token.
- Scopes shown on the consent page can be toggleable per scope; if a scope is toggleable, the user can deny one while granting others. Scope grants are enforced by `scope_not_authorized` errors.
- The user can later revoke the app from their TikTok app-permissions page; revoking kills the grant (and produces `auth_removed` / `access_token_invalid` behavior on in-flight posts).
- The app description is displayed on the authorization page, so it is part of the consent UX.

Sources:
- https://developers.tiktok.com/doc/login-kit-web/
- https://developers.tiktok.com/doc/oauth-user-access-token-management/
- https://developers.tiktok.com/doc/getting-started-create-an-app/ (app description shown to users)

## 4. App review / audit requirements

- **Registration:** you need a TikTok developer account (signup with email), then "Connect an app" under Manage apps; app owner should be an organization (recommended) or the individual account. The app gets **Client key + Client secret** in its Credentials section.
- **Products/scopes:** add the Content Posting API product, enable **Direct Post** configuration, and add the needed scopes. URL ownership verification is mandatory for Content Posting API upload URLs (`PULL_FROM_URL`): verify a **Domain** (DNS signature) or **URL prefix** (signature file) in the "URL properties" widget.
- **Submission:** the app is submitted for review with per-product/per-scope explanations plus at least one demo video (max 5, up to 50 MB each). Statuses: Draft → In review → Live (or Not approved with comments). Review takes "several days to two weeks". A web app needs a valid redirect URI at submission.
- **Audit for public posting:** "All content posted by unaudited clients will be restricted to private viewing mode. Once you have successfully tested your integration, to lift the restrictions on content visibility, your API client must undergo an audit to verify compliance with our Terms of Service." Enforcement error: `unaudited_client_can_only_post_to_private_accounts` — "Unaudited clients can only post to a private account."
- **Unpublished/personal apps:** the FAQ is strict — "Beta or development versions, incomplete apps, and test versions are not encouraged and will not be approved for integration with TikTok in most cases." New, unreleased apps can apply for an **integration assessment for unreleased apps** and may be approved based on credibility/benefit to users. A personal single-user app that posts only private content is lower-risk; public posting requires the audit.
- **Sandbox/development mode:** Sandbox mode avoids review but is not a posting playground — "Sandbox mode does not offer access to Content Posting API for public videos or Data Portability API." Sandboxes: up to 5 per app, up to 10 target users (accounts you own, added via login). Production Draft/In-review is the realistic test path for posting (with private-viewing restriction until audit).

Sources:
- https://developers.tiktok.com/doc/getting-started-create-an-app/
- https://developers.tiktok.com/doc/getting-started-faq/
- https://developers.tiktok.com/doc/add-a-sandbox/
- https://developers.tiktok.com/doc/content-posting-api-get-started/ (unaudited note)
- https://developers.tiktok.com/doc/content-posting-api-reference-direct-post/ (unaudited error code)

## 5. Upload / publish request shape

**Direct Post init** — `POST /v2/post/publish/video/init/`, `Authorization: Bearer {UserAccessToken}`, `Content-Type: application/json; charset=UTF-8`. Rate: **6 requests/minute per access token**.

Body:
```json
{
  "post_info": {
    "title": "caption text",
    "privacy_level": "MUTUAL_FOLLOW_FRIENDS",
    "disable_duet": false,
    "disable_comment": true,
    "disable_stitch": false,
    "video_cover_timestamp_ms": 1000,
    "brand_content_toggle": false,
    "brand_organic_toggle": false,
    "is_aigc": false
  },
  "source_info": {
    "source": "FILE_UPLOAD",
    "video_size": 50000123,
    "chunk_size": 10000000,
    "total_chunk_count": 5
  }
}
```
- `post_info.title`: max **2200 UTF-16 runes**; hashtags `#` and mentions `@` matched, delimited by spaces/newlines. Optional.
- `post_info.privacy_level` (required): one of `PUBLIC_TO_EVERYONE`, `MUTUAL_FOLLOW_FRIENDS`, `FOLLOWER_OF_CREATOR`, `SELF_ONLY`. Must match the `privacy_level_options` returned by `creator_info/query/` (public accounts: `PUBLIC_TO_EVERYONE`, `MUTUAL_FOLLOW_FRIENDS`, `SELF_ONLY`; private accounts: `FOLLOWER_OF_CREATOR`, `MUTUAL_FOLLOW_FRIENDS`, `SELF_ONLY`). Mismatch → `privacy_level_option_mismatch`.
- `source_info.source` (required): `FILE_UPLOAD` (fields `video_size`, `chunk_size`, `total_chunk_count`) or `PULL_FROM_URL` (field `video_url` on a verified domain/prefix).

**Init response** (Direct Post):
```json
{ "data": { "publish_id": "v_pub_file~v2-1.123456789",
            "upload_url": "https://open-upload.tiktokapis.com/video/?upload_id=...&upload_token=..." },
  "error": { "code": "ok", "message": "", "log_id": "..." } }
```
`upload_url` exists only for `FILE_UPLOAD` and is **valid for 1 hour**; use the entire URL including query params. `publish_id` max length 64.

**Upload-to-inbox init** — `POST /v2/post/publish/inbox/video/init/`, same 6 req/min limit, same `source_info` shape, returns `publish_id` + `upload_url`. The upload lands in the user's TikTok inbox as a draft; "You should inform users that they must click on inbox notifications to continue the editing flow in TikTok and complete the post." (Status `SEND_TO_USER_INBOX`.)

**File transfer (chunked PUT):**
- Headers per chunk: `Content-Type` (`video/mp4` | `video/quicktime` | `video/webm`), `Content-Length` (byte size of this chunk), `Content-Range: bytes {FIRST_BYTE}-{LAST_BYTE}/{TOTAL_BYTE_LENGTH}`. Body = binary chunk.
- Chunk rules (Media Transfer Guide): each chunk 5 MB–64 MB; final chunk up to 128 MB to absorb trailing bytes; files < 5 MB upload whole (`chunk_size` = full size, `total_chunk_count` = 1); files > 64 MB must be multi-chunk; 1–1000 chunks; sequential order; `total_chunk_count` = `floor(video_size / chunk_size)`.
- Responses: `206 PartialContent` = chunk accepted, more to come; `201 Created` = all parts uploaded, processing starts; `400` malformed headers/length mismatch; `403` `upload_url` expired; `404` upload task not found; `416` bad `Content-Range`; `5xx` retry chunk. Response header `Content-Range: bytes 0-{UPLOADED_BYTES}/{TOTAL}` reports progress.

**Pull from URL:**
- `video_url` must be on a **verified domain or URL prefix** owned by the app (`url_ownership_unverified` otherwise), must be `https`, must not redirect, and must stay accessible for the full download window (times out 1 hour after initiation). TikTok ingress ~100 Mbps.

**Media restrictions (Video Restrictions table):**
- Formats: MP4 (recommended), WebM, MOV. Codecs: H.264 (recommended), H.265, VP8, VP9.
- Frame rate: 23–60 FPS. Picture size: 360–4096 px per dimension.
- Duration: developers can send up to **10 minutes** via the API; account max is 3/5/10 minutes depending on creator privileges — use `max_video_post_duration_sec` from `creator_info/query/` to stop over-long posts.
- File size: **maximum 4 GB**.

**Photos:** use `POST /v2/post/publish/content/init/` with `post_info` + `source_info` + `post_mode` (`DIRECT_POST` or `MEDIA_UPLOAD`) + `media_type: "PHOTO"`; photos are `PULL_FROM_URL`-only (verified domain), formats WebP/JPEG, max 1080p, max 20 MB per image.

Sources:
- https://developers.tiktok.com/doc/content-posting-api-get-started/
- https://developers.tiktok.com/doc/content-posting-api-get-started-upload-content/
- https://developers.tiktok.com/doc/content-posting-api-reference-direct-post/
- https://developers.tiktok.com/doc/content-posting-api-reference-upload-video/
- https://developers.tiktok.com/doc/content-posting-api-reference-query-creator-info/
- https://developers.tiktok.com/doc/content-posting-api-media-transfer-guide/

## 6. Status polling

- **Endpoint:** `POST /v2/post/publish/status/fetch/`, `Authorization: Bearer {UserAccessToken}`, body `{ "publish_id": "{PUBLISH_ID}" }`. Rate: **30 requests/minute per access token**.
- **Response `data` fields:**
  - `status`: `PROCESSING_UPLOAD` (FILE_UPLOAD), `PROCESSING_DOWNLOAD` (PULL_FROM_URL), `SEND_TO_USER_INBOX` (upload/draft flow only), `PUBLISH_COMPLETE`, `FAILED`.
  - `fail_reason`: enum string (see below).
  - `publicaly_available_post_id` (sic, list of int64): post IDs returned **only** when the post is public and passed moderation; non-public posts return empty until made public.
  - `uploaded_bytes` / `downloaded_bytes`: progress for FILE_UPLOAD / PULL_FROM_URL.
- **Error codes:** `invalid_publish_id`, `token_not_authorized_for_specified_publish_id`, `access_token_invalid`, `scope_not_authorized`, `rate_limit_exceeded`, 5xx `internal_error`.
- **Timing (documented, approximate):** processing ~<30 s for 512 MB, ~1 min for 1 GB, >2 min for 4 GB; moderation for public posts usually finishes within 1 minute but "may take a few hours"; `post_id` is withheld until moderation passes.
- **Fail reasons (subset):** `file_format_check_failed`, `duration_check_failed`, `frame_rate_check_failed`, `picture_size_check_failed`, `internal` (retryable), `video_pull_failed`/`photo_pull_failed` (URL unreachable or 1-h timeout; retry OK), `publish_cancelled`, `auth_removed` (user revoked; do not retry), `spam_risk_too_many_posts` (user exceeded daily post cap), `spam_risk_user_banned_from_posting`, `spam_risk_text`, `spam_risk` (do not retry the last three).
- **Webhooks (alternative to polling):** `post.publish.failed`, `post.publish.complete`, `post.publish.inbox_delivered`, `post.publish.publicaly_available`, `post.publish.no_longer_publicaly_available`. Configured per app on the developer website.

Sources:
- https://developers.tiktok.com/doc/content-posting-api-reference-get-video-status/

## 7. Rate limits relevant to a personal single-account project

- Per-endpoint limits (per user access token, one-minute sliding window; over-limit → HTTP `429`, `rate_limit_exceeded`):
  - `creator_info/query/`: **20/min**
  - `video/init/` (Direct Post) and `inbox/video/init/` (Upload): **6/min**
  - `status/fetch/`: **30/min**
  - General Display API defaults (shown on the generic rate-limit page): 600/min per token for `/v2/user/info/`, `/v2/video/query/`, `/v2/video/list/` — not relevant to posting.
- Daily caps (enforced, not configurable):
  - Direct Post: per-user daily post cap via API — `spam_risk_too_many_posts` ("The daily post cap from the API is reached for the current user"), `spam_risk_user_banned_from_posting`. The docs do not publish the exact daily number for Direct Post.
  - Upload flow: "at most **5 pending shares** within any 24-hour period" — `spam_risk_too_many_pending_share`.
  - Client-level: `reached_active_user_cap` — "The daily quota for active publishing users from your client is reached." Default quota is not published; increases are by support request, production apps only.
- For a single account posting a handful of videos/day, the 6 req/min init limit and 30 req/min status limit are the operative ones; a modest poll interval (e.g. 5–10 s) fits comfortably.

Sources:
- https://developers.tiktok.com/doc/content-posting-api-reference-direct-post/ (per-endpoint limits + error codes)
- https://developers.tiktok.com/doc/content-posting-api-reference-upload-video/
- https://developers.tiktok.com/doc/content-posting-api-reference-get-video-status/
- https://developers.tiktok.com/doc/content-posting-api-reference-query-creator-info/
- https://developers.tiktok.com/doc/tiktok-api-v2-rate-limit/
- https://developers.tiktok.com/doc/getting-started-faq/ (active user cap increase)

## 8. Newer/alternative paths

- **No alternative posting API exists.** The Content Posting API is the current, maintained product; the changelog (through 2026-06-04) shows no new posting product and no deprecation of the current endpoints. Direct Post (Jun 2023) and photo posting (Nov 2023) are the last posting additions.
- The only replacement in the past was: **Share Video API** (web) → Content Posting API, sunset 2023-09-10 (legacy endpoints `POST https://open-api.tiktok.com/share/video/upload/` and `.../share/video/publish/`, 50 MB / MP4 / 3–60 s constraints). Do not use those.
- **Client access tokens** cannot publish; publishing always requires a **user access token** with `video.publish` (Direct Post) or `video.upload` (Upload).
- Sandbox does not offer Content Posting for public videos; unaudited clients post only privately. Both constraints are unchanged in the current docs.
- Uncertain / not stated in official docs: the exact daily Direct Post cap per user, the default `active user cap` per client, and the exact scope-approval criteria for a personal single-user app — those are decided by TikTok review/audit on a case-by-case basis.

---

## Appendix: exact endpoints (base `https://open.tiktokapis.com`)

| Purpose | Method + path |
|---|---|
| Authorize (browser redirect) | `GET https://www.tiktok.com/v2/auth/authorize/?client_key=...&response_type=code&scope=...&redirect_uri=...&state=...` |
| Token exchange / refresh | `POST /v2/oauth/token/` |
| Revoke token | `POST /v2/oauth/revoke/` |
| Query creator info | `POST /v2/post/publish/creator_info/query/` |
| Direct Post init | `POST /v2/post/publish/video/init/` |
| Upload-to-inbox init (draft) | `POST /v2/post/publish/inbox/video/init/` |
| Photo post/upload init | `POST /v2/post/publish/content/init/` |
| Upload media file | `PUT {upload_url}` (from init; `open-upload.tiktokapis.com`) |
| Get post status | `POST /v2/post/publish/status/fetch/` |
| Cancel pull | `POST /v2/post/publish/cancel/` |

## Summary

Changed files: `docs/research/2026-08-07-tiktok-content-posting-api.md` (new).

Risk: Content Posting for public videos is gated behind app review + client audit; unaudited apps post only privately. Sandbox mode excludes Content Posting for public videos. Token grant requires the user's TikTok login consent.

Remaining work: user provisions developer app, Client key/secret, redirect URI, applies `video.publish` scope, and (for public posts) submits for review/audit before Hermes can post.
