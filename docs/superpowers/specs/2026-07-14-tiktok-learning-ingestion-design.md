# TikTok Learning Ingestion Design

## Goal

Make Hermes learn accurately from both TikTok videos and TikTok Photo Mode posts
without treating an image carousel as a failed video. Keep temporary processing
artifacts on `D:` and reserve Google Drive for the final knowledge store.

## Source Handling

1. Standard TikTok video: retain the existing yt-dlp video/audio path, then
   analyze visual evidence plus transcript or speech when available.
2. TikTok Photo Mode: use `Evil0ctal/Douyin_TikTok_Download_API` through one
   bounded adapter as the primary media resolver. The adapter returns a local
   ordered image list, optional audio, caption, and source metadata.
3. A `photo` result must never be retried through the video downloader.
4. If the adapter is unavailable or returns no image files, use HTML extraction
   only for public metadata and image URLs. If that fails, create a
   `needs_source` result asking for screenshots; do not create a lesson from
   metadata alone.

## Storage

- Job output, intake notes, downloaded media, and raw analysis remain under the
  existing per-job output directory on `D:`.
- `G:\My Drive\Hermes Knowledge Base\knowledge_base` retains only the approved
  or pending knowledge record and its structured detail JSON.
- The Telegram intake note is written under the job output directory, so a
  full Google Drive cache cannot prevent job creation.

## Adapter Boundary

The adapter accepts a TikTok URL and a destination directory and returns a
small result contract:

```python
{
  "source_kind": "video" | "photo" | "unknown",
  "media_paths": ["D:/.../slide-01.jpg"],
  "audio_path": "D:/.../sound.mp3" | None,
  "metadata": {"title": "", "description": ""},
  "confidence": "high" | "medium" | "low" | "needs_source",
  "error": ""
}
```

Hermes owns job routing and analysis. The external repository only resolves
untrusted source media; it does not receive Hermes secrets or Drive paths.

## Fallbacks

1. External GitHub crawler adapter.
2. Existing yt-dlp for standard video/audio only.
3. Bounded public-page HTML/media metadata extraction.
4. Metadata-only response with low confidence and no lesson.
5. Request screenshots or the original media from the user.

## User Experience

- Telegram uses UTF-8 Vietnamese responses.
- Video results identify whether conclusions came from visual, transcript, or
  both.
- Photo-post results identify the number of images analyzed and state that no
  voice claim was made unless audio evidence exists.
- Each learning job sends one concise text summary and one `summary_analysis.md`
  artifact.

## Tests

- Intake note is written below job output, not the Drive knowledge root.
- Video sources continue using the video downloader path.
- Photo sources use the photo resolver and never call the video downloader.
- Resolver fallback classification and `needs_source` behavior.
- Vietnamese Telegram creation response has the expected UTF-8 wording.
