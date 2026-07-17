# Hermes Remotion MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a reversible MVP that lets Hermes create a product brief, ComfyUI prompt pack, Remotion render JSON, optional Remotion MP4, and FFmpeg-normalized final MP4 without replacing the existing MoviePy pipeline.

**Architecture:** Add small Python adapters that communicate through files under `projects/{slug}`. Add a separate `remotion_renderer/` Node project that renders one 1080x1920 TikTok product review composition from JSON props. Keep failures isolated by writing status JSON and preserving the existing Hermes path as fallback.

**Tech Stack:** Python 3.10+, standard library subprocess/pathlib/json/dataclasses, optional crawl4ai import, FFmpeg CLI, Node.js, Remotion React renderer.

## Global Constraints

- Hermes remains the coordinator. The existing MoviePy path is not removed.
- Do not add Dify, n8n, or RVC in this MVP.
- Do not replace the existing video editor pipeline globally.
- Do not embed ComfyUI workflow execution deeply into Hermes.
- Do not add a large GUI redesign.
- Do not auto-publish to TikTok.
- ComfyUI is external: Hermes writes prompts and reads optional assets from `projects/{slug}/assets/comfyui_import/`.
- Remotion is optional: render failure writes `projects/{slug}/render/remotion_status.json` and does not crash Hermes.
- FFmpeg finalization is the blocking final media step when a render source exists.

---

## File Structure

- Create `core/video_mvp_contracts.py`: shared project path creation, JSON writing, product brief normalization, Remotion input validation.
- Create `providers/crawl4ai_product_extractor.py`: optional crawl4ai integration with manual fallback and structured warnings.
- Create `core/comfyui_asset_adapter.py`: generate prompt pack JSON from product brief and scene data, list imported assets.
- Create `core/remotion_renderer.py`: write Remotion input JSON and invoke `remotion_renderer` through subprocess.
- Create `editor/ffmpeg_finalizer.py`: resolve FFmpeg path and normalize a rendered MP4 into `exports/final.mp4`.
- Create `remotion_renderer/package.json`: Node scripts and Remotion dependencies.
- Create `remotion_renderer/src/Root.tsx`: register the Remotion composition.
- Create `remotion_renderer/src/TikTokProductReview.tsx`: vertical TikTok template using JSON props.
- Create `remotion_renderer/render.mjs`: server-side render entrypoint using Remotion renderer APIs.
- Modify `scripts/hermes_tool.py`: add `render-remotion-demo` command for an end-to-end local smoke demo.
- Add focused script tests under `scripts/test_video_mvp_contracts.py`, `scripts/test_comfyui_asset_adapter.py`, `scripts/test_remotion_renderer_adapter.py`, and `scripts/test_ffmpeg_finalizer.py`.
- Modify `.env.example`: document optional `REMOTION_RENDERER_DIR`, `NODE_PATH`, and `CRAWL4AI_ENABLED` settings.

---

### Task 1: File Contract And Product Brief

**Files:**
- Create: `core/video_mvp_contracts.py`
- Test: `scripts/test_video_mvp_contracts.py`

**Interfaces:**
- Produces: `VideoMvpPaths`, `ensure_video_mvp_paths(project_root: str | Path) -> VideoMvpPaths`
- Produces: `normalize_product_brief(raw: dict, source_url: str = "", warnings: list[str] | None = None) -> dict`
- Produces: `write_json(path: str | Path, payload: dict) -> Path`
- Produces: `build_remotion_input(...) -> dict`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for Hermes video MVP file contracts."""

from pathlib import Path
import json
import sys
from tempfile import TemporaryDirectory

sys.path.append(str(Path(__file__).resolve().parent.parent))

from core.video_mvp_contracts import (
    build_remotion_input,
    ensure_video_mvp_paths,
    normalize_product_brief,
    write_json,
)


def run_tests():
    with TemporaryDirectory() as tmp:
        root = Path(tmp) / "demo-product"
        paths = ensure_video_mvp_paths(root)
        assert paths.research_dir.exists()
        assert paths.assets_dir.exists()
        assert paths.comfyui_import_dir.exists()
        assert paths.render_dir.exists()
        assert paths.exports_dir.exists()

        brief = normalize_product_brief(
            {"title": "Mini Blender", "description": "Portable blender for smoothies."},
            source_url="https://example.com/blender",
            warnings=["crawl used fallback parser"],
        )
        assert brief["title"] == "Mini Blender"
        assert brief["source_url"] == "https://example.com/blender"
        assert brief["warnings"] == ["crawl used fallback parser"]
        assert "Portable blender" in brief["description"]

        saved = write_json(paths.product_brief_json, brief)
        assert json.loads(saved.read_text(encoding="utf-8"))["title"] == "Mini Blender"

        remotion_input = build_remotion_input(
            project_root=root,
            product_brief=brief,
            hook_text="Blend anywhere",
            voiceover_text="This mini blender helps you make smoothies anywhere.",
            scenes=[{"id": "scene-1", "caption": "Portable size", "asset_path": ""}],
            asset_paths=[],
            duration_seconds=18,
            fps=30,
            cta_text="Check it today",
        )
        assert remotion_input["width"] == 1080
        assert remotion_input["height"] == 1920
        assert remotion_input["fps"] == 30
        assert remotion_input["duration_seconds"] == 18
        assert remotion_input["product"]["title"] == "Mini Blender"
        assert remotion_input["scenes"][0]["caption"] == "Portable size"
    print("video mvp contract tests: PASS")


if __name__ == "__main__":
    run_tests()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/test_video_mvp_contracts.py`

Expected: FAIL with `ModuleNotFoundError: No module named 'core.video_mvp_contracts'`.

- [ ] **Step 3: Write minimal implementation**

Create `core/video_mvp_contracts.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class VideoMvpPaths:
    project_root: Path
    research_dir: Path
    assets_dir: Path
    comfyui_import_dir: Path
    render_dir: Path
    exports_dir: Path
    product_brief_json: Path
    product_brief_md: Path
    comfyui_prompts_json: Path
    remotion_input_json: Path
    remotion_status_json: Path
    remotion_final_mp4: Path
    final_mp4: Path


def ensure_video_mvp_paths(project_root: str | Path) -> VideoMvpPaths:
    root = Path(project_root)
    research_dir = root / "research"
    assets_dir = root / "assets"
    comfyui_import_dir = assets_dir / "comfyui_import"
    render_dir = root / "render"
    exports_dir = root / "exports"
    for path in [research_dir, assets_dir, comfyui_import_dir, render_dir, exports_dir]:
        path.mkdir(parents=True, exist_ok=True)
    return VideoMvpPaths(
        project_root=root,
        research_dir=research_dir,
        assets_dir=assets_dir,
        comfyui_import_dir=comfyui_import_dir,
        render_dir=render_dir,
        exports_dir=exports_dir,
        product_brief_json=research_dir / "product_brief.json",
        product_brief_md=research_dir / "product_brief.md",
        comfyui_prompts_json=assets_dir / "comfyui_prompts.json",
        remotion_input_json=render_dir / "remotion_input.json",
        remotion_status_json=render_dir / "remotion_status.json",
        remotion_final_mp4=exports_dir / "remotion_final.mp4",
        final_mp4=exports_dir / "final.mp4",
    )


def normalize_product_brief(raw: dict[str, Any], source_url: str = "", warnings: list[str] | None = None) -> dict[str, Any]:
    selling_points = raw.get("selling_points") or raw.get("benefits") or []
    if isinstance(selling_points, str):
        selling_points = [line.strip() for line in selling_points.splitlines() if line.strip()]
    return {
        "title": str(raw.get("title") or raw.get("name") or "Untitled product").strip(),
        "description": str(raw.get("description") or raw.get("summary") or "").strip(),
        "selling_points": list(selling_points),
        "target_customer": str(raw.get("target_customer") or raw.get("audience") or "").strip(),
        "pain_points": list(raw.get("pain_points") or []),
        "claims": list(raw.get("claims") or []),
        "objections": list(raw.get("objections") or []),
        "source_url": source_url or str(raw.get("source_url") or "").strip(),
        "warnings": list(warnings or raw.get("warnings") or []),
    }


def write_json(path: str | Path, payload: dict[str, Any]) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def build_remotion_input(
    project_root: str | Path,
    product_brief: dict[str, Any],
    hook_text: str,
    voiceover_text: str,
    scenes: list[dict[str, Any]],
    asset_paths: list[str],
    duration_seconds: int = 24,
    fps: int = 30,
    cta_text: str = "",
) -> dict[str, Any]:
    return {
        "project_root": str(Path(project_root).resolve()),
        "width": 1080,
        "height": 1920,
        "fps": int(fps),
        "duration_seconds": int(duration_seconds),
        "product": product_brief,
        "hook_text": hook_text.strip(),
        "voiceover_text": voiceover_text.strip(),
        "scenes": scenes,
        "asset_paths": asset_paths,
        "cta_text": cta_text.strip(),
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python scripts/test_video_mvp_contracts.py`

Expected: `video mvp contract tests: PASS`.

- [ ] **Step 5: Commit**

```bash
git add core/video_mvp_contracts.py scripts/test_video_mvp_contracts.py
git commit -m "feat: add video mvp file contracts"
```

---

### Task 2: crawl4ai Product Extractor

**Files:**
- Create: `providers/crawl4ai_product_extractor.py`
- Test: `scripts/test_crawl4ai_product_extractor.py`

**Interfaces:**
- Consumes: `normalize_product_brief(raw, source_url, warnings)` from `core.video_mvp_contracts`
- Produces: `extract_product_brief(url: str, manual_data: dict | None = None) -> dict`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for optional crawl4ai product extraction."""

from pathlib import Path
import sys
from unittest.mock import patch

sys.path.append(str(Path(__file__).resolve().parent.parent))

from providers.crawl4ai_product_extractor import extract_product_brief


class FakeCrawler:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return None

    def run(self, url):
        return type("Result", (), {"markdown": "# Travel Mug\nKeeps coffee hot."})()


def run_tests():
    manual = extract_product_brief("", manual_data={"title": "Manual Lamp", "description": "Desk lamp"})
    assert manual["title"] == "Manual Lamp"
    assert manual["warnings"] == ["manual product data used"]

    with patch("providers.crawl4ai_product_extractor._load_crawler", return_value=FakeCrawler):
        brief = extract_product_brief("https://example.com/mug")
    assert brief["title"] == "Travel Mug"
    assert "Keeps coffee hot" in brief["description"]
    assert brief["source_url"] == "https://example.com/mug"

    with patch("providers.crawl4ai_product_extractor._load_crawler", side_effect=ImportError("missing")):
        fallback = extract_product_brief("https://example.com/fallback", manual_data={"title": "Fallback"})
    assert fallback["title"] == "Fallback"
    assert "crawl4ai unavailable: missing" in fallback["warnings"][0]
    print("crawl4ai product extractor tests: PASS")


if __name__ == "__main__":
    run_tests()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/test_crawl4ai_product_extractor.py`

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

Create `providers/crawl4ai_product_extractor.py`:

```python
from __future__ import annotations

from typing import Any

from core.video_mvp_contracts import normalize_product_brief


def _load_crawler():
    from crawl4ai import WebCrawler

    return WebCrawler


def _brief_from_markdown(markdown: str, url: str) -> dict[str, Any]:
    lines = [line.strip(" #\t") for line in markdown.splitlines() if line.strip()]
    title = lines[0] if lines else "Untitled product"
    description = "\n".join(lines[1:20])
    return normalize_product_brief(
        {"title": title, "description": description},
        source_url=url,
        warnings=[],
    )


def extract_product_brief(url: str, manual_data: dict[str, Any] | None = None) -> dict[str, Any]:
    if not url:
        return normalize_product_brief(manual_data or {}, warnings=["manual product data used"])
    try:
        crawler_cls = _load_crawler()
        with crawler_cls() as crawler:
            result = crawler.run(url)
        markdown = getattr(result, "markdown", "") or str(result)
        return _brief_from_markdown(markdown, url)
    except Exception as exc:
        warnings = [f"crawl4ai unavailable: {exc}"]
        if manual_data:
            return normalize_product_brief(manual_data, source_url=url, warnings=warnings)
        return normalize_product_brief({"title": url, "description": ""}, source_url=url, warnings=warnings)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python scripts/test_crawl4ai_product_extractor.py`

Expected: `crawl4ai product extractor tests: PASS`.

- [ ] **Step 5: Commit**

```bash
git add providers/crawl4ai_product_extractor.py scripts/test_crawl4ai_product_extractor.py
git commit -m "feat: add crawl4ai product extractor"
```

---

### Task 3: ComfyUI Prompt And Asset Adapter

**Files:**
- Create: `core/comfyui_asset_adapter.py`
- Test: `scripts/test_comfyui_asset_adapter.py`

**Interfaces:**
- Consumes: `VideoMvpPaths`
- Produces: `build_comfyui_prompt_pack(product_brief: dict, scenes: list[dict]) -> dict`
- Produces: `write_comfyui_prompt_pack(paths: VideoMvpPaths, product_brief: dict, scenes: list[dict]) -> Path`
- Produces: `list_comfyui_assets(paths: VideoMvpPaths) -> list[str]`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for ComfyUI prompt pack adapter."""

from pathlib import Path
import json
import sys
from tempfile import TemporaryDirectory

sys.path.append(str(Path(__file__).resolve().parent.parent))

from core.comfyui_asset_adapter import (
    build_comfyui_prompt_pack,
    list_comfyui_assets,
    write_comfyui_prompt_pack,
)
from core.video_mvp_contracts import ensure_video_mvp_paths


def run_tests():
    product = {"title": "Mini Blender", "description": "Portable smoothie blender"}
    scenes = [{"id": "hook", "caption": "Blend anywhere"}]
    pack = build_comfyui_prompt_pack(product, scenes)
    assert pack["product_title"] == "Mini Blender"
    assert "vertical 9:16" in pack["prompts"][0]["prompt"]

    with TemporaryDirectory() as tmp:
        paths = ensure_video_mvp_paths(Path(tmp) / "project")
        saved = write_comfyui_prompt_pack(paths, product, scenes)
        assert json.loads(saved.read_text(encoding="utf-8"))["prompts"][0]["scene_id"] == "hook"
        image = paths.comfyui_import_dir / "asset.png"
        image.write_text("fake", encoding="utf-8")
        assert list_comfyui_assets(paths) == [str(image)]
    print("comfyui asset adapter tests: PASS")


if __name__ == "__main__":
    run_tests()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/test_comfyui_asset_adapter.py`

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

Create `core/comfyui_asset_adapter.py`:

```python
from __future__ import annotations

from pathlib import Path
from typing import Any

from core.video_mvp_contracts import VideoMvpPaths, write_json


ASSET_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".mp4", ".mov", ".webm"}


def build_comfyui_prompt_pack(product_brief: dict[str, Any], scenes: list[dict[str, Any]]) -> dict[str, Any]:
    title = product_brief.get("title", "Product")
    description = product_brief.get("description", "")
    prompts = []
    for index, scene in enumerate(scenes or [{"id": "hero", "caption": "Hero product shot"}], start=1):
        caption = scene.get("caption") or scene.get("text") or "Product benefit"
        prompts.append({
            "scene_id": scene.get("id", f"scene-{index}"),
            "prompt": (
                f"vertical 9:16 TikTok product review scene, {title}, {caption}, "
                f"realistic commercial lighting, clean background, high detail. Product context: {description}"
            ),
        })
    return {"product_title": title, "source": "hermes", "prompts": prompts}


def write_comfyui_prompt_pack(paths: VideoMvpPaths, product_brief: dict[str, Any], scenes: list[dict[str, Any]]) -> Path:
    return write_json(paths.comfyui_prompts_json, build_comfyui_prompt_pack(product_brief, scenes))


def list_comfyui_assets(paths: VideoMvpPaths) -> list[str]:
    if not paths.comfyui_import_dir.exists():
        return []
    files = [
        item for item in paths.comfyui_import_dir.iterdir()
        if item.is_file() and item.suffix.lower() in ASSET_EXTENSIONS
    ]
    return [str(item) for item in sorted(files)]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python scripts/test_comfyui_asset_adapter.py`

Expected: `comfyui asset adapter tests: PASS`.

- [ ] **Step 5: Commit**

```bash
git add core/comfyui_asset_adapter.py scripts/test_comfyui_asset_adapter.py
git commit -m "feat: add comfyui prompt adapter"
```

---

### Task 4: Remotion Python Adapter

**Files:**
- Create: `core/remotion_renderer.py`
- Test: `scripts/test_remotion_renderer_adapter.py`

**Interfaces:**
- Consumes: `VideoMvpPaths`, `write_json`
- Produces: `write_remotion_input(paths: VideoMvpPaths, payload: dict) -> Path`
- Produces: `render_with_remotion(paths: VideoMvpPaths, renderer_dir: str | Path | None = None, node_executable: str = "node", timeout_seconds: int = 300) -> dict`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for Remotion subprocess adapter."""

from pathlib import Path
import json
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.append(str(Path(__file__).resolve().parent.parent))

from core.remotion_renderer import render_with_remotion, write_remotion_input
from core.video_mvp_contracts import ensure_video_mvp_paths


def run_tests():
    with TemporaryDirectory() as tmp:
        paths = ensure_video_mvp_paths(Path(tmp) / "project")
        payload = {"width": 1080, "height": 1920, "fps": 30, "duration_seconds": 10}
        saved = write_remotion_input(paths, payload)
        assert json.loads(saved.read_text(encoding="utf-8"))["width"] == 1080

        missing = render_with_remotion(paths, renderer_dir=Path(tmp) / "missing")
        assert missing["ok"] is False
        assert missing["reason"] == "renderer_dir_missing"
        assert paths.remotion_status_json.exists()

        renderer = Path(tmp) / "renderer"
        renderer.mkdir()
        (renderer / "render.mjs").write_text("", encoding="utf-8")

        class Completed:
            returncode = 0
            stdout = "rendered"
            stderr = ""

        with patch("core.remotion_renderer.subprocess.run", return_value=Completed()) as mocked:
            result = render_with_remotion(paths, renderer_dir=renderer, node_executable="node", timeout_seconds=5)
        assert result["ok"] is True
        assert mocked.call_args.args[0][0] == "node"
        assert str(paths.remotion_input_json) in mocked.call_args.args[0]
    print("remotion renderer adapter tests: PASS")


if __name__ == "__main__":
    run_tests()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/test_remotion_renderer_adapter.py`

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

Create `core/remotion_renderer.py`:

```python
from __future__ import annotations

from pathlib import Path
import subprocess
from typing import Any

from core.video_mvp_contracts import VideoMvpPaths, write_json


def write_remotion_input(paths: VideoMvpPaths, payload: dict[str, Any]) -> Path:
    return write_json(paths.remotion_input_json, payload)


def _write_status(paths: VideoMvpPaths, status: dict[str, Any]) -> dict[str, Any]:
    write_json(paths.remotion_status_json, status)
    return status


def render_with_remotion(
    paths: VideoMvpPaths,
    renderer_dir: str | Path | None = None,
    node_executable: str = "node",
    timeout_seconds: int = 300,
) -> dict[str, Any]:
    renderer = Path(renderer_dir or "remotion_renderer")
    render_script = renderer / "render.mjs"
    if not renderer.exists():
        return _write_status(paths, {"ok": False, "reason": "renderer_dir_missing", "renderer_dir": str(renderer)})
    if not render_script.exists():
        return _write_status(paths, {"ok": False, "reason": "render_script_missing", "render_script": str(render_script)})
    command = [
        node_executable,
        str(render_script),
        str(paths.remotion_input_json),
        str(paths.remotion_final_mp4),
    ]
    try:
        completed = subprocess.run(
            command,
            cwd=str(renderer),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except Exception as exc:
        return _write_status(paths, {"ok": False, "reason": "subprocess_error", "error": str(exc), "command": command})
    status = {
        "ok": completed.returncode == 0,
        "reason": "rendered" if completed.returncode == 0 else "render_failed",
        "returncode": completed.returncode,
        "stdout": completed.stdout[-2000:],
        "stderr": completed.stderr[-2000:],
        "command": command,
        "output": str(paths.remotion_final_mp4),
    }
    return _write_status(paths, status)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python scripts/test_remotion_renderer_adapter.py`

Expected: `remotion renderer adapter tests: PASS`.

- [ ] **Step 5: Commit**

```bash
git add core/remotion_renderer.py scripts/test_remotion_renderer_adapter.py
git commit -m "feat: add remotion renderer adapter"
```

---

### Task 5: FFmpeg Finalizer

**Files:**
- Create: `editor/ffmpeg_finalizer.py`
- Test: `scripts/test_ffmpeg_finalizer.py`

**Interfaces:**
- Produces: `build_ffmpeg_normalize_command(input_path: str | Path, output_path: str | Path, ffmpeg_path: str = "") -> list[str]`
- Produces: `finalize_video(input_path: str | Path, output_path: str | Path, ffmpeg_path: str = "", timeout_seconds: int = 300) -> dict`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for FFmpeg finalization command builder."""

from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.append(str(Path(__file__).resolve().parent.parent))

from editor.ffmpeg_finalizer import build_ffmpeg_normalize_command, finalize_video


def run_tests():
    cmd = build_ffmpeg_normalize_command("in.mp4", "out.mp4", ffmpeg_path="ffmpeg")
    assert cmd[:4] == ["ffmpeg", "-y", "-i", "in.mp4"]
    assert "scale=1080:1920:force_original_aspect_ratio=decrease" in " ".join(cmd)
    assert cmd[-1] == "out.mp4"

    with TemporaryDirectory() as tmp:
        src = Path(tmp) / "in.mp4"
        dst = Path(tmp) / "out.mp4"
        missing = finalize_video(src, dst, ffmpeg_path="ffmpeg")
        assert missing["ok"] is False
        assert missing["reason"] == "input_missing"

        src.write_text("fake", encoding="utf-8")

        class Completed:
            returncode = 0
            stdout = ""
            stderr = ""

        with patch("editor.ffmpeg_finalizer.subprocess.run", return_value=Completed()) as mocked:
            result = finalize_video(src, dst, ffmpeg_path="ffmpeg", timeout_seconds=5)
        assert result["ok"] is True
        assert mocked.call_args.args[0][0] == "ffmpeg"
    print("ffmpeg finalizer tests: PASS")


if __name__ == "__main__":
    run_tests()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/test_ffmpeg_finalizer.py`

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

Create `editor/ffmpeg_finalizer.py`:

```python
from __future__ import annotations

from pathlib import Path
import subprocess


def build_ffmpeg_normalize_command(input_path: str | Path, output_path: str | Path, ffmpeg_path: str = "") -> list[str]:
    ffmpeg = ffmpeg_path or "ffmpeg"
    vf = "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,setsar=1"
    return [
        ffmpeg,
        "-y",
        "-i",
        str(input_path),
        "-vf",
        vf,
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-movflags",
        "+faststart",
        str(output_path),
    ]


def finalize_video(input_path: str | Path, output_path: str | Path, ffmpeg_path: str = "", timeout_seconds: int = 300) -> dict:
    src = Path(input_path)
    dst = Path(output_path)
    if not src.exists():
        return {"ok": False, "reason": "input_missing", "input": str(src)}
    dst.parent.mkdir(parents=True, exist_ok=True)
    command = build_ffmpeg_normalize_command(src, dst, ffmpeg_path=ffmpeg_path)
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=timeout_seconds)
    except Exception as exc:
        return {"ok": False, "reason": "subprocess_error", "error": str(exc), "command": command}
    return {
        "ok": completed.returncode == 0,
        "reason": "finalized" if completed.returncode == 0 else "ffmpeg_failed",
        "returncode": completed.returncode,
        "stdout": completed.stdout[-2000:],
        "stderr": completed.stderr[-2000:],
        "command": command,
        "output": str(dst),
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python scripts/test_ffmpeg_finalizer.py`

Expected: `ffmpeg finalizer tests: PASS`.

- [ ] **Step 5: Commit**

```bash
git add editor/ffmpeg_finalizer.py scripts/test_ffmpeg_finalizer.py
git commit -m "feat: add ffmpeg finalizer"
```

---

### Task 6: Remotion Node Project

**Files:**
- Create: `remotion_renderer/package.json`
- Create: `remotion_renderer/src/Root.tsx`
- Create: `remotion_renderer/src/TikTokProductReview.tsx`
- Create: `remotion_renderer/render.mjs`

**Interfaces:**
- Consumes: `render/remotion_input.json`
- Produces: MP4 path supplied as the second CLI argument

- [ ] **Step 1: Create Node project files**

Create `remotion_renderer/package.json`:

```json
{
  "name": "hermes-remotion-renderer",
  "private": true,
  "type": "module",
  "scripts": {
    "render": "node render.mjs",
    "preview": "remotion studio src/Root.tsx"
  },
  "dependencies": {
    "@remotion/bundler": "^4.0.0",
    "@remotion/renderer": "^4.0.0",
    "remotion": "^4.0.0",
    "react": "^18.2.0",
    "react-dom": "^18.2.0"
  },
  "devDependencies": {
    "typescript": "^5.0.0"
  }
}
```

Create `remotion_renderer/src/Root.tsx`:

```tsx
import React from 'react';
import {Composition} from 'remotion';
import {TikTokProductReview, RemotionVideoProps} from './TikTokProductReview';

export const RemotionRoot: React.FC = () => {
  return (
    <Composition<RemotionVideoProps>
      id="TikTokProductReview"
      component={TikTokProductReview}
      durationInFrames={720}
      fps={30}
      width={1080}
      height={1920}
      defaultProps={{
        width: 1080,
        height: 1920,
        fps: 30,
        duration_seconds: 24,
        product: {title: 'Demo Product', description: ''},
        hook_text: 'Demo Hook',
        voiceover_text: '',
        scenes: [],
        asset_paths: [],
        cta_text: 'Learn more',
      }}
    />
  );
};
```

Create `remotion_renderer/src/TikTokProductReview.tsx`:

```tsx
import React from 'react';
import {AbsoluteFill, Img, interpolate, Sequence, useCurrentFrame, useVideoConfig} from 'remotion';

export type RemotionVideoProps = {
  width: number;
  height: number;
  fps: number;
  duration_seconds: number;
  product: {title: string; description?: string};
  hook_text: string;
  voiceover_text: string;
  scenes: Array<{id?: string; caption?: string; asset_path?: string}>;
  asset_paths: string[];
  cta_text: string;
};

const titleStyle: React.CSSProperties = {
  color: 'white',
  fontFamily: 'Arial, sans-serif',
  fontSize: 82,
  fontWeight: 800,
  lineHeight: 1.05,
  textAlign: 'center',
  textShadow: '0 8px 28px rgba(0,0,0,0.55)',
  padding: '0 72px',
};

export const TikTokProductReview: React.FC<RemotionVideoProps> = (props) => {
  const frame = useCurrentFrame();
  const {fps, durationInFrames} = useVideoConfig();
  const opacity = interpolate(frame, [0, 20], [0, 1], {extrapolateRight: 'clamp'});
  const scenes = props.scenes.length ? props.scenes : [{caption: props.product.description || props.product.title}];
  const sceneFrames = Math.max(45, Math.floor(durationInFrames / scenes.length));

  return (
    <AbsoluteFill style={{backgroundColor: '#111318'}}>
      <AbsoluteFill style={{background: 'linear-gradient(180deg, #20242c 0%, #111318 100%)'}} />
      {props.asset_paths[0] ? (
        <AbsoluteFill style={{opacity: 0.42}}>
          <Img src={`file://${props.asset_paths[0]}`} style={{width: '100%', height: '100%', objectFit: 'cover'}} />
        </AbsoluteFill>
      ) : null}
      <Sequence from={0} durationInFrames={Math.min(durationInFrames, fps * 4)}>
        <AbsoluteFill style={{alignItems: 'center', justifyContent: 'center', opacity}}>
          <div style={titleStyle}>{props.hook_text || props.product.title}</div>
        </AbsoluteFill>
      </Sequence>
      {scenes.map((scene, index) => (
        <Sequence key={scene.id || index} from={fps * 4 + index * sceneFrames} durationInFrames={sceneFrames}>
          <AbsoluteFill style={{alignItems: 'center', justifyContent: 'center', padding: 80}}>
            <div style={{...titleStyle, fontSize: 58}}>{scene.caption || props.product.title}</div>
          </AbsoluteFill>
        </Sequence>
      ))}
      <Sequence from={Math.max(0, durationInFrames - fps * 4)} durationInFrames={fps * 4}>
        <AbsoluteFill style={{alignItems: 'center', justifyContent: 'center', padding: 80}}>
          <div style={{...titleStyle, fontSize: 68}}>{props.cta_text || 'Check it today'}</div>
        </AbsoluteFill>
      </Sequence>
    </AbsoluteFill>
  );
};
```

Create `remotion_renderer/render.mjs`:

```javascript
import fs from 'node:fs';
import path from 'node:path';
import {bundle} from '@remotion/bundler';
import {renderMedia, selectComposition} from '@remotion/renderer';

const inputPath = process.argv[2];
const outputPath = process.argv[3];

if (!inputPath || !outputPath) {
  console.error('Usage: node render.mjs <remotion_input.json> <output.mp4>');
  process.exit(2);
}

const inputProps = JSON.parse(fs.readFileSync(inputPath, 'utf8'));
const entryPoint = path.join(process.cwd(), 'src', 'Root.tsx');
const serveUrl = await bundle({entryPoint});
const composition = await selectComposition({
  serveUrl,
  id: 'TikTokProductReview',
  inputProps,
});

await renderMedia({
  composition,
  serveUrl,
  codec: 'h264',
  outputLocation: outputPath,
  inputProps,
});

console.log(`Rendered ${outputPath}`);
```

- [ ] **Step 2: Install dependencies if Node is available**

Run: `cd remotion_renderer; npm install`

Expected: dependencies install and `package-lock.json` is created. If Node/npm is unavailable, skip install and note it in the task report.

- [ ] **Step 3: Commit**

```bash
git add remotion_renderer/package.json remotion_renderer/package-lock.json remotion_renderer/render.mjs remotion_renderer/src/Root.tsx remotion_renderer/src/TikTokProductReview.tsx
git commit -m "feat: add remotion renderer project"
```

---

### Task 7: CLI Demo Command

**Files:**
- Modify: `scripts/hermes_tool.py`
- Test: `scripts/test_remotion_demo_command.py`

**Interfaces:**
- Consumes: all adapters from Tasks 1-5
- Produces: CLI command `python scripts/hermes_tool.py render-remotion-demo --project demo-remotion-mvp`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for Remotion MVP demo command wiring."""

from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.append(str(Path(__file__).resolve().parent.parent))

import scripts.hermes_tool as hermes_tool


def run_tests():
    with TemporaryDirectory() as tmp:
        with patch.object(sys, "argv", ["hermes_tool.py", "render-remotion-demo", "--project-root", tmp, "--project", "demo"]):
            args = hermes_tool.parse_args()
        assert args.command == "render-remotion-demo"
        assert args.project == "demo"

        with patch("scripts.hermes_tool.render_with_remotion", return_value={"ok": False, "reason": "renderer_dir_missing"}), \
             patch("scripts.hermes_tool.finalize_video", return_value={"ok": False, "reason": "input_missing"}):
            result = hermes_tool.run_remotion_demo(Path(tmp), "demo", skip_render=False)
        assert result["project"].endswith("demo")
        assert result["remotion"]["ok"] is False
        assert (Path(tmp) / "demo" / "render" / "remotion_input.json").exists()
    print("remotion demo command tests: PASS")


if __name__ == "__main__":
    run_tests()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/test_remotion_demo_command.py`

Expected: FAIL because `render-remotion-demo` and `run_remotion_demo` do not exist.

- [ ] **Step 3: Modify CLI**

In `scripts/hermes_tool.py`, add imports:

```python
from core.comfyui_asset_adapter import list_comfyui_assets, write_comfyui_prompt_pack
from core.remotion_renderer import render_with_remotion, write_remotion_input
from core.video_mvp_contracts import build_remotion_input, ensure_video_mvp_paths, normalize_product_brief, write_json
from editor.ffmpeg_finalizer import finalize_video
```

Add parser setup:

```python
    demo = sub.add_parser("render-remotion-demo", help="Create and optionally render a Remotion MVP demo project")
    demo.add_argument("--project-root", default="projects", help="Projects root directory")
    demo.add_argument("--project", default="remotion-demo", help="Demo project folder name")
    demo.add_argument("--skip-render", action="store_true", help="Only write contracts and JSON files")
```

Add function before `main()`:

```python
def run_remotion_demo(project_root: Path, project_name: str, skip_render: bool = False) -> dict:
    project_dir = Path(project_root) / project_name
    paths = ensure_video_mvp_paths(project_dir)
    product = normalize_product_brief({
        "title": "Hermes Demo Product",
        "description": "A compact product review demo for validating the Remotion MVP pipeline.",
        "selling_points": ["Clear hook", "Readable captions", "Fast vertical render"],
    }, warnings=["demo data"])
    scenes = [
        {"id": "scene-1", "caption": "Show the product clearly in the first seconds"},
        {"id": "scene-2", "caption": "Explain the main benefit with one simple sentence"},
        {"id": "scene-3", "caption": "Close with a direct call to action"},
    ]
    write_json(paths.product_brief_json, product)
    paths.product_brief_md.write_text(
        f"# {product['title']}\n\n{product['description']}\n",
        encoding="utf-8",
    )
    write_comfyui_prompt_pack(paths, product, scenes)
    remotion_payload = build_remotion_input(
        project_root=project_dir,
        product_brief=product,
        hook_text="Stop scrolling for this product",
        voiceover_text="This demo validates the Hermes Remotion MVP pipeline.",
        scenes=scenes,
        asset_paths=list_comfyui_assets(paths),
        duration_seconds=24,
        fps=30,
        cta_text="Save this product idea",
    )
    write_remotion_input(paths, remotion_payload)
    remotion_status = {"ok": False, "reason": "skipped"}
    final_status = {"ok": False, "reason": "skipped"}
    if not skip_render:
        remotion_status = render_with_remotion(paths)
        if remotion_status.get("ok"):
            final_status = finalize_video(paths.remotion_final_mp4, paths.final_mp4)
        else:
            final_status = finalize_video(paths.remotion_final_mp4, paths.final_mp4)
    return {
        "project": str(project_dir),
        "remotion_input": str(paths.remotion_input_json),
        "comfyui_prompts": str(paths.comfyui_prompts_json),
        "remotion": remotion_status,
        "final": final_status,
    }
```

Add `main()` branch before generated tool commands:

```python
    if args.command == "render-remotion-demo":
        result = run_remotion_demo(Path(args.project_root), args.project, skip_render=args.skip_render)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["remotion"].get("ok") or args.skip_render else 1
```

Also add `import json` at the top.

- [ ] **Step 4: Run test to verify it passes**

Run: `python scripts/test_remotion_demo_command.py`

Expected: `remotion demo command tests: PASS`.

- [ ] **Step 5: Run contract-only smoke**

Run: `python scripts/hermes_tool.py render-remotion-demo --project remotion-demo --skip-render`

Expected: JSON output with paths to `projects/remotion-demo/render/remotion_input.json` and `projects/remotion-demo/assets/comfyui_prompts.json`.

- [ ] **Step 6: Commit**

```bash
git add scripts/hermes_tool.py scripts/test_remotion_demo_command.py
git commit -m "feat: add remotion mvp demo command"
```

---

### Task 8: Config Documentation And Verification

**Files:**
- Modify: `.env.example`
- Modify: `README.md`
- Test: run focused script tests

**Interfaces:**
- Documents optional settings: `REMOTION_RENDERER_DIR`, `NODE_PATH`, `CRAWL4AI_ENABLED`

- [ ] **Step 1: Update `.env.example`**

Add:

```text
# Optional Remotion MVP adapter settings
REMOTION_RENDERER_DIR=remotion_renderer
NODE_PATH=node
CRAWL4AI_ENABLED=0
```

- [ ] **Step 2: Update `README.md`**

Add a short section:

```markdown
## Remotion MVP Renderer

Hermes can generate a Remotion MVP project contract without replacing the existing MoviePy renderer:

```powershell
python scripts\hermes_tool.py render-remotion-demo --project remotion-demo --skip-render
```

When Node dependencies are installed in `remotion_renderer/`, omit `--skip-render` to try rendering. The command writes `render/remotion_input.json`, `assets/comfyui_prompts.json`, `exports/remotion_final.mp4`, and `exports/final.mp4` when rendering succeeds.
```

- [ ] **Step 3: Run all focused MVP tests**

Run:

```powershell
python scripts/test_video_mvp_contracts.py
python scripts/test_crawl4ai_product_extractor.py
python scripts/test_comfyui_asset_adapter.py
python scripts/test_remotion_renderer_adapter.py
python scripts/test_ffmpeg_finalizer.py
python scripts/test_remotion_demo_command.py
```

Expected: every script prints `PASS`.

- [ ] **Step 4: Run optional render smoke**

Run:

```powershell
cd remotion_renderer
npm install
cd ..
python scripts/hermes_tool.py render-remotion-demo --project remotion-demo
```

Expected if Node/npm/Remotion/FFmpeg are installed: `projects/remotion-demo/exports/final.mp4` exists. If dependencies are missing, record which dependency is missing and keep the contract-only smoke as the verified baseline.

- [ ] **Step 5: Commit**

```bash
git add .env.example README.md
git commit -m "docs: document remotion mvp workflow"
```

---

## Self-Review

- Spec coverage: crawl4ai extraction is Task 2; ComfyUI prompt/import adapter is Task 3; Remotion JSON and subprocess adapter are Tasks 4 and 6; FFmpeg finalization is Task 5; demo smoke is Task 7; docs and verification are Task 8.
- Scope check: Dify, n8n, RVC, full ComfyUI automation, GUI redesign, TikTok publishing, and MoviePy replacement are explicitly excluded.
- Type consistency: `VideoMvpPaths`, `ensure_video_mvp_paths`, `write_json`, `build_remotion_input`, `render_with_remotion`, and `finalize_video` signatures match across tasks.
- Placeholder scan: no unresolved placeholder markers or open-ended implementation instructions remain.
