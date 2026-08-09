# Local TikTok Crawler

Hermes uses the optional local clone at `D:\HERMES\external\Douyin_TikTok_Download_API`
to classify TikTok links and download Photo Mode slides into each job folder. The
installed version is pinned to upstream tag `V4.1.2`.

## Start

```powershell
cd D:\work\hermes-agent
.\scripts\start_tiktok_crawler_local.ps1
```

The script starts the crawler hidden, writes logs under
`D:\HermesData\logs`, and checks the exact OpenAPI route Hermes needs. Check it
manually with:

```powershell
$schema = Invoke-RestMethod http://127.0.0.1:5556/openapi.json
$schema.paths.PSObject.Properties.Name -contains '/api/hybrid/video_data'
```

Hermes defaults to `http://127.0.0.1:5556`. The optional variables are in
`.env.example`: `TIKTOK_CRAWLER_BASE_URL`, timeout, image count, and size limit.

## Safety

- Keep the crawler bound to `127.0.0.1`; never expose port `5556` publicly.
- Hermes's structured HTML fallback normally works without a TikTok cookie. Do not add
  a cookie unless both the crawler and fallback fail for a source you can access manually.
- Upstream tracks `crawlers/tiktok/app/config.yaml`. Before adding a real cookie locally,
  protect the file from routine staging and verify it is absent from every diff:

  ```powershell
  cd D:\HERMES\external\Douyin_TikTok_Download_API
  git update-index --skip-worktree crawlers/tiktok/app/config.yaml
  git diff -- crawlers/tiktok/app/config.yaml
  ```

  Never sync, commit, log, or paste that cookie into Hermes `.env`.
- Hermes downloads at most 20 slides and 50 MB total into `projects/<job>/source_images`.
- Downloaded responses are accepted only when their content type and bytes form a valid image.
- SQLite under `D:\HermesData` remains the source of truth. Google Drive is backup/export only.

## Fallback Behavior

1. Hermes requests the local crawler's `api/hybrid/video_data` endpoint.
2. For a carousel response, Hermes downloads the returned slide URLs into the job directory and sends them to the vision analyzer.
3. If the crawler fails, Hermes uses bounded `curl-cffi` browser impersonation and
   parses TikTok's structured `api-data`/rehydration JSON. A successful HTML fallback
   is marked `medium` confidence.
4. Every downloaded slide must have an image content type and pass Pillow decoding.
5. If no usable slide/video evidence is available, the job completes with
   `needs_source`, writes `summary_analysis.md`, creates no lesson, and asks for an
   upload or a new link.

The crawler can be affected by TikTok changes, rate limits, cookies, or anti-bot behavior. A
successful OpenAPI check verifies the local service contract, but does not prove a particular
TikTok post is downloadable. In the 2026-07-16 smoke test, the upstream App API returned
HTTP 429 without an authenticated cookie, while Hermes's structured HTML fallback downloaded
and validated all six slides from a public Photo Mode post.

## Runtime Verification

```powershell
cd D:\work\hermes-agent

# API contract
.\.venv\Scripts\python.exe -c "from tools.tiktok_media_resolver import check_crawler_health; print(check_crawler_health())"

# Unit/contract checks
.\.venv\Scripts\python.exe -m unittest tests.hermes.test_tiktok_media_resolver -v
```

Do not use `/docs` alone as a health check, and do not approve a lesson based only on
the post title, thumbnail, or metadata.
