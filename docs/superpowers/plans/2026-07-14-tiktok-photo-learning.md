# TikTok Photo Learning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable Hermes to create reliable learning jobs for TikTok videos and Photo Mode posts while keeping temporary job data on `D:`.

**Architecture:** Hermes retains ownership of routing, job state, analysis, and knowledge approval. A small optional adapter calls a locally-run clone of `Evil0ctal/Douyin_TikTok_Download_API` to resolve TikTok media into files under the job output directory. The adapter returns a bounded result and HTML/metadata and user-upload fallback preserve transparent confidence when external crawling is unavailable.

**Tech Stack:** Python 3.12, python-telegram-bot, existing file job queue, HTTPX/stdlib HTTP client, pytest-style script tests, external Python/FastAPI GitHub crawler.

## Global Constraints

- Keep all downloaded media, intake notes, and raw artifacts under `D:\work\hermes-agent\projects`.
- Keep `G:\My Drive\Hermes Knowledge Base\knowledge_base` for structured knowledge only.
- Do not persist TikTok cookies in Hermes source, logs, or the Drive knowledge store.
- Do not retry a confirmed TikTok `/photo/` post through `yt-dlp` as video.
- Limit carousel resolution to 20 images and 50 MB total before vision analysis.
- Do not create a lesson from metadata-only source evidence.

---

### Task 1: Move Intake Notes Off Google Drive and Fix Telegram Copy

**Files:**
- Modify: `telegram_bot.py:686-788`
- Test: `scripts/test_telegram_learning_delivery.py`

**Interfaces:**
- Consumes: `job["target"]["output_dir"]` created by `AgentJobManager.create_job()`.
- Produces: `create_learning_intake_note(...) -> str`, returning a path below that job output directory.

- [ ] **Step 1: Write the failing test**

```python
def test_learning_intake_stays_under_job_output(tmp_path):
    job = {"job_id": "job_photo", "target": {"output_dir": str(tmp_path / "output")}}
    path = telegram_bot.create_learning_intake_note(
        job=job,
        source_value="https://vt.tiktok.com/example",
        source_kind="tiktok_url",
        extra_note="",
        local_video_path=None,
        telegram_info={},
    )
    assert Path(path).parent == Path(job["target"]["output_dir"])
    assert Path(path).name == "learning_intake.md"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `$env:PYTHONUTF8='1'; .\.venv\Scripts\python.exe scripts\test_telegram_learning_delivery.py`

Expected: the intake note assertion fails because the current function writes to `LEARNING_STORE.root / "video_intake"`.

- [ ] **Step 3: Write the minimal implementation**

```python
output_dir = Path(job["target"]["output_dir"])
output_dir.mkdir(parents=True, exist_ok=True)
path = output_dir / "learning_intake.md"
path.write_text(body.strip() + "\n", encoding="utf-8")
return str(path)
```

Replace the ASCII acknowledgement with:

```python
await update.message.reply_text(
    "Đã nhận yêu cầu. Mình đang tạo job để worker phân tích nội dung..."
)
```

- [ ] **Step 4: Run the focused test to verify it passes**

Run: `$env:PYTHONUTF8='1'; .\.venv\Scripts\python.exe scripts\test_telegram_learning_delivery.py`

Expected: PASS.

### Task 2: Add a Bounded TikTok Media Resolver Adapter

**Files:**
- Create: `tools/tiktok_media_resolver.py`
- Modify: `.env.example`
- Test: `scripts/test_tiktok_media_resolver.py`

**Interfaces:**
- Produces: `resolve_tiktok_media(url: str, output_dir: Path) -> TikTokMediaResult`.
- `TikTokMediaResult` fields: `source_kind`, `media_paths`, `audio_path`, `metadata`, `confidence`, and `error`.
- Consumes: `TIKTOK_CRAWLER_BASE_URL`, `TIKTOK_CRAWLER_TIMEOUT_SECONDS`, and `TIKTOK_MAX_CAROUSEL_IMAGES` from environment configuration.

- [ ] **Step 1: Write failing adapter tests**

```python
def test_photo_result_keeps_only_existing_images(tmp_path, monkeypatch):
    slide = tmp_path / "slide-01.jpg"
    slide.write_bytes(b"image")
    monkeypatch.setattr(resolver, "_call_crawler", lambda *_: {
        "images": [str(slide), str(tmp_path / "missing.jpg")],
        "title": "Photo post",
    })
    result = resolver.resolve_tiktok_media("https://www.tiktok.com/@u/photo/1", tmp_path)
    assert result.source_kind == "photo"
    assert result.media_paths == [slide]

def test_photo_failure_is_needs_source(tmp_path, monkeypatch):
    monkeypatch.setattr(resolver, "_call_crawler", lambda *_: None)
    result = resolver.resolve_tiktok_media("https://www.tiktok.com/@u/photo/1", tmp_path)
    assert result.source_kind == "photo"
    assert result.confidence == "needs_source"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `$env:PYTHONUTF8='1'; .\.venv\Scripts\python.exe scripts\test_tiktok_media_resolver.py`

Expected: FAIL because the resolver module does not exist.

- [ ] **Step 3: Implement the adapter**

```python
@dataclass
class TikTokMediaResult:
    source_kind: str
    media_paths: list[Path]
    audio_path: Path | None
    metadata: dict
    confidence: str
    error: str = ""

def is_photo_url(url: str) -> bool:
    return "/photo/" in urlparse(url).path.lower()
```

Use an HTTP request only to the configured localhost crawler URL. Validate every returned path resolves below `output_dir`; discard paths outside it, missing paths, non-image extensions, images beyond the configured count, and files above the configured aggregate limit. Return `needs_source` when no valid images remain. Do not send cookies, model credentials, or Google Drive paths.

- [ ] **Step 4: Run tests to verify they pass**

Run: `$env:PYTHONUTF8='1'; .\.venv\Scripts\python.exe scripts\test_tiktok_media_resolver.py`

Expected: PASS.

### Task 3: Route Photo Posts Through Image Analysis and Stop Invalid Retries

**Files:**
- Modify: `core/job_watcher.py:536-690`
- Modify: `tools/video_downloader.py:70-150`
- Test: `scripts/test_learning_fallback.py`

**Interfaces:**
- Consumes: `TikTokMediaResult` from `tools.tiktok_media_resolver`.
- Produces: `analysis_source="photo_carousel"`, `confidence` based on resolved media, and a source-bound analysis prompt containing ordered slide paths.

- [ ] **Step 1: Write failing workflow tests**

```python
def test_photo_post_uses_photo_resolver_not_video_downloader(monkeypatch, tmp_path):
    worker = JobWorker()
    slide = tmp_path / "slide-01.jpg"
    slide.write_bytes(b"image")
    monkeypatch.setattr(job_watcher, "resolve_tiktok_media", lambda *_: TikTokMediaResult(
        source_kind="photo", media_paths=[slide], audio_path=None,
        metadata={"title": "Slides"}, confidence="high",
    ))
    monkeypatch.setattr(job_watcher, "download_video", lambda *_: (_ for _ in ()).throw(AssertionError()))
    assert worker._resolve_media_for_analysis("https://www.tiktok.com/@u/photo/1", tmp_path) is None
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `$env:PYTHONUTF8='1'; .\.venv\Scripts\python.exe scripts\test_learning_fallback.py`

Expected: FAIL because `/photo/` is passed to `download_video()` today.

- [ ] **Step 3: Implement the minimal routing change**

```python
if is_tiktok_photo_source(source_val):
    photo_result = resolve_tiktok_media(source_val, output_dir / "source_images")
    if not photo_result.media_paths:
        raise NeedsSourceError(photo_result.error or "TikTok photo slides could not be retrieved.")
    analysis_text = analyze_images([str(path) for path in photo_result.media_paths], prompt_text)
    analysis_source = "photo_carousel"
    confidence = photo_result.confidence
```

Use one dedicated `NeedsSourceError` path in `_handle_legacy_job_failure` so it moves directly to failed with a user-actionable reason, without consuming retries. Keep the existing video path unchanged. Only call audio transcription when `audio_path` exists.

- [ ] **Step 4: Run focused workflow tests to verify they pass**

Run: `$env:PYTHONUTF8='1'; .\.venv\Scripts\python.exe scripts\test_learning_fallback.py; .\.venv\Scripts\python.exe scripts\test_worker_json_and_transcript.py`

Expected: both PASS.

### Task 4: Configure and Verify the External Crawler Locally

**Files:**
- Create: `docs/runbooks/tiktok-crawler-local.md`
- Modify: `.env.example`
- Test: `scripts/test_tiktok_media_resolver.py`

**Interfaces:**
- External clone root: `D:\HERMES\external\Douyin_TikTok_Download_API`.
- Local-only endpoint: `TIKTOK_CRAWLER_BASE_URL=http://127.0.0.1:<configured-port>`.

- [ ] **Step 1: Document a local-only setup and health contract**

```text
Clone the repository below D:\HERMES\external.
Run it only on 127.0.0.1.
Set TIKTOK_CRAWLER_BASE_URL only after its health endpoint responds.
Keep TikTok cookies in that external repository's ignored configuration file.
```

- [ ] **Step 2: Add a failing health-check test**

```python
def test_unreachable_crawler_returns_needs_source(tmp_path, monkeypatch):
    monkeypatch.setenv("TIKTOK_CRAWLER_BASE_URL", "http://127.0.0.1:1")
    result = resolver.resolve_tiktok_media("https://www.tiktok.com/@u/photo/1", tmp_path)
    assert result.confidence == "needs_source"
```

- [ ] **Step 3: Implement bounded timeout and error mapping**

```python
except (OSError, TimeoutError, urllib.error.URLError) as exc:
    return TikTokMediaResult(
        source_kind="photo", media_paths=[], audio_path=None,
        metadata={}, confidence="needs_source",
        error=f"TikTok photo crawler unavailable: {exc}",
    )
```

- [ ] **Step 4: Run the final regression suite**

Run: `$env:PYTHONUTF8='1'; $tests = @('scripts/test_telegram_learning_delivery.py','scripts/test_tiktok_media_resolver.py','scripts/test_learning_fallback.py','scripts/test_learning_job_metadata.py','scripts/test_worker_json_and_transcript.py','scripts/test_job_operations.py'); foreach ($test in $tests) { & .\.venv\Scripts\python.exe $test; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE } }`

Expected: all scripts exit `0`.
