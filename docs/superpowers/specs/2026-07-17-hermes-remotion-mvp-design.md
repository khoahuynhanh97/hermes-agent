# Hermes Remotion MVP Design

## Goal

Build a small, reversible MVP that improves TikTok product review video output without expanding Hermes into a large orchestration platform.

The MVP adds focused adapters around the existing Hermes project structure:

- crawl4ai for product-page extraction.
- ComfyUI as an external asset generator, connected through prompt and asset folders only.
- Remotion as an optional template renderer driven by a JSON contract.
- FFmpeg as the final media normalization and fallback processing layer.

Hermes remains the coordinator. The existing MoviePy path is not removed.

## Non-Goals

- Do not add Dify, n8n, or RVC in this MVP.
- Do not replace the existing video editor pipeline globally.
- Do not embed ComfyUI workflow execution deeply into Hermes.
- Do not add a large GUI redesign.
- Do not auto-publish to TikTok.

## Architecture

```text
Product URL or manual product data
  -> crawl4ai adapter
  -> Hermes product brief
  -> existing script/storyboard generation
  -> ComfyUI prompt pack
  -> optional asset import from ComfyUI output folder
  -> Remotion JSON input
  -> Remotion render output
  -> FFmpeg final normalize/fallback
  -> projects/{slug}/exports/final.mp4
```

The integration is adapter-first. Each new component communicates through files in a project folder, so failures remain isolated and the current Hermes workflow can still run.

## Project Folder Contract

For each product project, Hermes may create:

```text
projects/{slug}/research/product_brief.json
projects/{slug}/research/product_brief.md
projects/{slug}/assets/comfyui_prompts.json
projects/{slug}/assets/comfyui_import/
projects/{slug}/render/remotion_input.json
projects/{slug}/render/remotion_status.json
projects/{slug}/exports/remotion_final.mp4
projects/{slug}/exports/final.mp4
```

The contract is intentionally file-based so Remotion and ComfyUI can be developed or run independently.

## Components

### crawl4ai Product Extractor

Input: product URL.

Output: `product_brief.json` and `product_brief.md`.

The brief should contain title, selling points, target customer, pain points, claims, objections, source URL, and extraction warnings. If crawl4ai is unavailable, Hermes should allow manual product data to be used.

### ComfyUI Asset Adapter

Input: product brief and storyboard.

Output: `comfyui_prompts.json`.

Hermes will not run ComfyUI in the first MVP. It writes clear prompts and expects generated assets to be copied into `assets/comfyui_import/`. The renderer should use imported assets when present and fall back to existing materials if not.

### Remotion Renderer Adapter

Input: `remotion_input.json`.

Output: `exports/remotion_final.mp4`.

Remotion should be implemented as a separate Node project or package folder, with one vertical TikTok composition. It should accept props for:

- video dimensions: 1080x1920.
- duration and fps.
- hook text.
- voiceover or audio path.
- scene list.
- asset paths.
- subtitles or timed caption blocks.
- CTA text.

Hermes calls Remotion through a small Python adapter using a subprocess command. If the command fails, Hermes records the error in `remotion_status.json` and does not break the existing pipeline.

### FFmpeg Finalizer

Input: `remotion_final.mp4` or existing pipeline output.

Output: `final.mp4`.

FFmpeg handles final normalization: H.264 MP4, 1080x1920 or configured vertical size, audio compatibility, and optional subtitle/audio mixing. This keeps final media handling deterministic even if the renderer changes later.

## Data Flow

1. User starts a product video job from Telegram, GUI, or CLI.
2. Hermes creates or opens `projects/{slug}`.
3. If a URL is provided, crawl4ai extracts a product brief.
4. Existing Hermes generation produces script, storyboard, and prompt files.
5. ComfyUI adapter writes prompt pack and waits for optional imported assets.
6. Remotion adapter writes `remotion_input.json`.
7. Remotion renders `remotion_final.mp4`.
8. FFmpeg finalizer writes `final.mp4`.
9. Hermes reports the output path and any warnings.

## Error Handling

- Missing crawl4ai: log warning and use manual product data.
- Crawl failure: preserve URL and error in `product_brief.json`.
- Missing ComfyUI assets: use existing materials or simple text-first template.
- Remotion dependency missing: skip Remotion and keep existing render path.
- Remotion render failure: write `remotion_status.json` with command, exit code, and stderr summary.
- FFmpeg failure: return a clear blocking error because no final MP4 can be trusted.

## Testing

Add focused tests around contracts and adapters:

- Product brief JSON can be written from normalized input.
- ComfyUI prompt pack contains scene prompts and product context.
- Remotion input JSON validates required fields and paths.
- Remotion adapter handles missing Node/Remotion without crashing Hermes.
- FFmpeg finalizer builds the expected command without requiring a real long render in unit tests.

Use one optional smoke command for local verification when dependencies are installed:

```text
python scripts/hermes_tool.py render-remotion-demo
```

## MVP Acceptance Criteria

- A sample product project can produce `render/remotion_input.json`.
- The Remotion project can render a vertical MP4 from that JSON.
- FFmpeg can normalize that MP4 to `exports/final.mp4`.
- If Remotion is unavailable or fails, Hermes records the failure and the old pipeline remains usable.
- No Dify, n8n, RVC, or full ComfyUI automation is introduced.

