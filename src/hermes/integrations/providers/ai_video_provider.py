import json
import os
import time
from datetime import datetime

import requests

from hermes.runtime import config
from hermes.application.core.file_manager import clean_filename
from hermes.integrations.downloaders.direct_downloader import download_direct


AI_VIDEO_PROVIDER_CHOICES = [
    "Grok Imagine",
    "Pika",
    "Krea",
    "Leonardo.Ai",
    "Runway",
    "Custom API",
]


PROVIDERS = {
    "Grok Imagine": {
        "id": "grok",
        "key_attr": "GROK_API_KEY",
        "endpoint_attr": "GROK_VIDEO_ENDPOINT",
        "default_endpoint": "",
        "model_attr": "GROK_VIDEO_MODEL",
        "default_model": "grok-imagine",
        "site_url": "https://grok.com/",
        "extra_headers": {},
    },
    "Runway": {
        "id": "runway",
        "key_attr": "RUNWAY_API_KEY",
        "endpoint_attr": "RUNWAY_VIDEO_ENDPOINT",
        "default_endpoint": "",
        "model_attr": "RUNWAY_VIDEO_MODEL",
        "default_model": "gen4_turbo",
        "site_url": "https://runwayml.com/",
        "extra_headers": {"X-Runway-Version": "2024-11-06"},
    },
    "Pika": {
        "id": "pika",
        "key_attr": "PIKA_API_KEY",
        "endpoint_attr": "PIKA_VIDEO_ENDPOINT",
        "default_endpoint": "",
        "model_attr": "PIKA_VIDEO_MODEL",
        "default_model": "pika-2.5",
        "site_url": "https://pika.art/",
        "extra_headers": {},
    },
    "Krea": {
        "id": "krea",
        "key_attr": "KREA_API_KEY",
        "endpoint_attr": "KREA_VIDEO_ENDPOINT",
        "default_endpoint": "",
        "model_attr": "KREA_VIDEO_MODEL",
        "default_model": "auto",
        "site_url": "https://www.krea.ai/",
        "extra_headers": {},
    },
    "Leonardo.Ai": {
        "id": "leonardo",
        "key_attr": "LEONARDO_API_KEY",
        "endpoint_attr": "LEONARDO_VIDEO_ENDPOINT",
        "default_endpoint": "",
        "model_attr": "LEONARDO_VIDEO_MODEL",
        "default_model": "motion-2.0-fast",
        "site_url": "https://leonardo.ai/",
        "extra_headers": {},
    },
    "Custom API": {
        "id": "custom",
        "key_attr": "AI_VIDEO_CUSTOM_API_KEY",
        "endpoint_attr": "AI_VIDEO_CUSTOM_ENDPOINT",
        "default_endpoint": "",
        "model_attr": "AI_VIDEO_CUSTOM_MODEL",
        "default_model": "video-model",
        "site_url": "",
        "extra_headers": {},
    },
}


def generate_ai_video_materials(
    provider_name,
    prompts,
    output_dir,
    clips_per_prompt=1,
    duration_seconds=5,
    aspect_ratio="9:16",
    resolution="720p",
    log_callback=None,
):
    """Generate AI videos when an API endpoint is configured, otherwise save a prompt pack."""
    def log(message):
        if log_callback:
            log_callback(message)
        else:
            print(message)

    provider = PROVIDERS.get(provider_name)
    if not provider:
        log(f"[!] AI video provider khong hop le: {provider_name}")
        return []

    os.makedirs(output_dir, exist_ok=True)
    cleaned_prompts = [p.strip() for p in prompts if p and p.strip()]
    if not cleaned_prompts:
        log("[!] Khong co prompt nao de tao video AI.")
        return []

    endpoint = getattr(config, provider["endpoint_attr"], "") or provider["default_endpoint"]
    api_key = getattr(config, provider["key_attr"], "")
    model = getattr(config, provider["model_attr"], "") or provider["default_model"]

    prompt_pack = _write_prompt_pack(
        provider_name,
        provider,
        cleaned_prompts,
        output_dir,
        clips_per_prompt,
        duration_seconds,
        aspect_ratio,
        resolution,
        model,
    )
    log(f"[*] Da luu prompt pack AI video: {prompt_pack}")

    if not api_key or not endpoint:
        log("[!] Provider nay chua co API key/endpoint de goi tu dong.")
        if provider["site_url"]:
            log(f"    Mo cong cu va dan prompt thu cong: {provider['site_url']}")
        log("    Khi co API chinh thuc, dien *_API_KEY va *_VIDEO_ENDPOINT trong .env de app tu tai mp4.")
        return []

    downloaded = []
    for prompt_index, prompt in enumerate(cleaned_prompts, start=1):
        for clip_index in range(1, clips_per_prompt + 1):
            log(f"[*] Tao AI video {provider_name} prompt {prompt_index}/{len(cleaned_prompts)}, clip {clip_index}/{clips_per_prompt}...")
            try:
                result = _submit_and_download_video(
                    provider,
                    endpoint,
                    api_key,
                    model,
                    prompt,
                    output_dir,
                    prompt_index,
                    clip_index,
                    duration_seconds,
                    aspect_ratio,
                    resolution,
                    log,
                )
                if result:
                    downloaded.append(result)
            except Exception as exc:
                log(f"[x] Loi tao video AI ({provider_name}): {exc}")

    return downloaded


def _write_prompt_pack(provider_name, provider, prompts, output_dir, clips_per_prompt, duration_seconds, aspect_ratio, resolution, model):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    provider_id = provider["id"]
    path = os.path.join(output_dir, f"ai_video_prompts_{provider_id}_{timestamp}.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"Provider: {provider_name}\n")
        f.write(f"Model: {model}\n")
        f.write(f"Duration: {duration_seconds}s\n")
        f.write(f"Aspect ratio: {aspect_ratio}\n")
        f.write(f"Resolution: {resolution}\n")
        if provider["site_url"]:
            f.write(f"Open: {provider['site_url']}\n")
        f.write("\n")
        for i, prompt in enumerate(prompts, start=1):
            f.write(f"--- PROMPT {i} ({clips_per_prompt} clip) ---\n")
            f.write(_build_video_prompt(prompt, duration_seconds, aspect_ratio, resolution))
            f.write("\n\n")
    return path


def _submit_and_download_video(provider, endpoint, api_key, model, prompt, output_dir, prompt_index, clip_index, duration_seconds, aspect_ratio, resolution, log):
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    headers.update(provider.get("extra_headers", {}))

    payload = {
        "model": model,
        "prompt": _build_video_prompt(prompt, duration_seconds, aspect_ratio, resolution),
        "duration": duration_seconds,
        "aspect_ratio": aspect_ratio,
        "ratio": aspect_ratio,
        "resolution": resolution,
    }

    response = requests.post(endpoint, headers=headers, json=payload, timeout=60)
    if response.status_code >= 400:
        raise RuntimeError(f"HTTP {response.status_code}: {response.text[:500]}")

    data = response.json()
    video_url = _find_video_url(data)
    if not video_url:
        task_id = _find_task_id(data)
        if task_id:
            data = _poll_video_task(provider, endpoint, headers, task_id, log)
            video_url = _find_video_url(data)

    if not video_url:
        log(f"[!] Provider tra ve ket qua nhung chua thay video URL: {json.dumps(data, ensure_ascii=False)[:500]}")
        return None

    filename_prompt = clean_filename(prompt[:50]) or "ai_video"
    filename = f"ai_{provider['id']}_{prompt_index:02d}_{clip_index:02d}_{filename_prompt}.mp4"
    output_path = os.path.abspath(os.path.join(output_dir, filename))
    if download_direct(video_url, output_path, log):
        return output_path
    return None


def _poll_video_task(provider, endpoint, headers, task_id, log):
    poll_seconds = int(getattr(config, "AI_VIDEO_POLL_SECONDS", "5") or 5)
    max_wait_seconds = int(getattr(config, "AI_VIDEO_MAX_WAIT_SECONDS", "600") or 600)
    task_url = f"{endpoint.rstrip('/')}/{task_id}"
    started_at = time.time()

    while time.time() - started_at <= max_wait_seconds:
        time.sleep(poll_seconds)
        response = requests.get(task_url, headers=headers, timeout=30)
        if response.status_code >= 400:
            raise RuntimeError(f"Poll HTTP {response.status_code}: {response.text[:500]}")

        data = response.json()
        status = str(data.get("status") or data.get("state") or "").lower()
        log(f"    - Trang thai task {provider['id']}: {status or 'unknown'}")

        if _find_video_url(data):
            return data
        if status in {"failed", "error", "cancelled", "canceled"}:
            raise RuntimeError(json.dumps(data, ensure_ascii=False)[:500])

    raise TimeoutError(f"Het thoi gian cho AI video task: {task_id}")


def _build_video_prompt(prompt, duration_seconds, aspect_ratio, resolution):
    return (
        f"{prompt.strip()}\n"
        f"Create a short vertical TikTok product review style video, {aspect_ratio} aspect ratio, "
        f"{duration_seconds} seconds, {resolution}, realistic product detail, clear motion, "
        "no watermark, no logo, no text artifacts, no distorted hands."
    )


def _find_video_url(data):
    if isinstance(data, str):
        if data.startswith("http") and any(ext in data.lower() for ext in [".mp4", ".mov", ".webm"]):
            return data
        return None
    if isinstance(data, list):
        for item in data:
            found = _find_video_url(item)
            if found:
                return found
        return None
    if not isinstance(data, dict):
        return None

    for key in ["video_url", "videoUrl", "url", "download_url", "downloadUrl", "asset_url", "assetUrl"]:
        found = _find_video_url(data.get(key))
        if found:
            return found

    for key in ["output", "outputs", "result", "results", "data", "assets", "artifacts"]:
        found = _find_video_url(data.get(key))
        if found:
            return found

    return None


def _find_task_id(data):
    if not isinstance(data, dict):
        return None
    for key in ["id", "task_id", "taskId", "generation_id", "generationId"]:
        value = data.get(key)
        if value:
            return str(value)
    return None
