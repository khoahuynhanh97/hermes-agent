"""Google Flow Playwright Keyframe Generation Provider."""

from __future__ import annotations

import hashlib
import logging
import os
import re
from pathlib import Path
from typing import Any

from PIL import Image
from playwright.sync_api import sync_playwright

from hermes_personal.integrations.video_factory.ports import (
    KeyframeGenerationPort,
    KeyframeGenerationRequest,
    KeyframeGenerationResult,
)

logger = logging.getLogger(__name__)

KEYFRAME_NEGATIVE_PROMPT = "watermark, text, seller logo, marketplace badge, price tag, blurry, low quality"


class GoogleFlowKeyframeProvider(KeyframeGenerationPort):
    provider_kind = "google_flow"

    def __init__(
        self,
        profile_path: Path | str | None = None,
        chrome_profile_directory: str = "Default",
        output_dir: Path | str | None = None,
        model: str = "ImageFx / Imagen 3",
        timeout_seconds: float = 180.0,
        headless: bool = False,
    ) -> None:
        self.profile_path = Path(profile_path).expanduser().resolve() if profile_path else None
        self.chrome_profile_directory = chrome_profile_directory
        self.output_dir = Path(output_dir).expanduser().resolve() if output_dir else (Path.cwd() / "keyframes")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.headless = headless

    @classmethod
    def from_config(cls, output_dir: Path | str | None = None) -> GoogleFlowKeyframeProvider:
        """Construct GoogleFlowKeyframeProvider from user profile / config."""
        from hermes_cli.config import load_config

        cfg = load_config()
        video_cfg = cfg.get("video_factory", {}) if isinstance(cfg, dict) else {}
        flow_cfg = (
            video_cfg.get("google_flow_keyframe")
            or video_cfg.get("google_flow")
            or {}
        )
        if not isinstance(flow_cfg, dict):
            flow_cfg = {}
        profile_path = flow_cfg.get("profile_path")
        chrome_profile_directory = str(flow_cfg.get("chrome_profile_directory", "Default"))
        model = str(flow_cfg.get("model", "ImageFx / Imagen 3"))
        timeout = float(flow_cfg.get("timeout_seconds", 180.0))
        headless = bool(flow_cfg.get("headless", False))
        return cls(
            profile_path=profile_path,
            chrome_profile_directory=chrome_profile_directory,
            output_dir=output_dir,
            model=model,
            timeout_seconds=timeout,
            headless=headless,
        )

    def is_available(self) -> bool:
        if not self.profile_path:
            return False
        return self.profile_path.is_dir()

    def _output_path(self, operation_id: str) -> Path:
        safe = re.sub(r"[^A-Za-z0-9_.-]", "_", operation_id).strip("._") or "keyframe"
        output = (self.output_dir / f"{safe[:120]}.png").resolve()
        return output

    def submit(self, request: KeyframeGenerationRequest) -> KeyframeGenerationResult:
        if not request.prompt.strip() or not request.product_description.strip():
            return KeyframeGenerationResult(
                operation_id=request.operation_id,
                status="failed",
                error_code="INVALID_INPUT",
                error_message="prompt and product_description are required",
            )
        reference_paths = [Path(value).resolve() for value in request.reference_image_paths]
        if not reference_paths or any(
            not path.is_file() or path.stat().st_size == 0 for path in reference_paths
        ):
            return KeyframeGenerationResult(
                operation_id=request.operation_id,
                status="failed",
                error_code="REFERENCE_IMAGE_NOT_FOUND",
                error_message="at least one readable product reference is required",
            )

        if not self.is_available():
            return KeyframeGenerationResult(
                operation_id=request.operation_id,
                status="failed",
                error_code="GOOGLE_FLOW_UNAVAILABLE",
                error_message="Google Flow browser profile directory not found or not configured",
            )

        output_file = self._output_path(request.operation_id)
        if output_file.is_file() and output_file.stat().st_size > 0:
            return KeyframeGenerationResult(
                operation_id=request.operation_id,
                status="completed",
                provider_operation_id=f"flow-kf-{request.operation_id}",
                image_path=str(output_file),
                metadata={"provider_kind": self.provider_kind, "model": self.model},
            )

        try:
            with sync_playwright() as p:
                context_args = []
                user_data_dir = str(self.profile_path)
                if self.chrome_profile_directory and self.chrome_profile_directory != "Default":
                    context_args.append(f"--profile-directory={self.chrome_profile_directory}")
                
                browser = p.chromium.launch_persistent_context(
                    user_data_dir=user_data_dir,
                    headless=self.headless,
                    channel="chrome",
                    args=context_args,
                    accept_downloads=True,
                )
                try:
                    page = browser.pages[0] if browser.pages else browser.new_page()
                    page.goto("https://flow.google.com/", timeout=self.timeout_seconds * 1000)

                    # Check auth
                    is_auth = (
                        page.query_selector(".profile-button") is not None
                        or page.query_selector("button.settings-trigger-button") is not None
                        or page.query_selector(".account-button") is not None
                    )
                    if not is_auth:
                        is_auth = page.query_selector(".auth-required") is None

                    if not is_auth:
                        raise RuntimeError("GOOGLE_FLOW_AUTH_REQUIRED")

                    # Prompt input
                    prompt_input = page.wait_for_selector(
                        "textarea[name='prompt'], textarea[placeholder*='prompt'], flow-prompt-input textarea",
                        timeout=10000,
                    )
                    prompt_input.click()
                    neg = request.negative_prompt or KEYFRAME_NEGATIVE_PROMPT
                    prompt_input.fill(f"{request.prompt}. Negative prompt: {neg}")

                    # Trigger Generation
                    gen_btn = page.wait_for_selector(
                        "button.generate-button, button[aria-label*='generate' i], button[aria-label*='tạo' i]",
                        timeout=10000,
                    )
                    gen_btn.click()

                    # Wait for Result
                    page.wait_for_selector(".generated-image, flow-image-tile, img.result-image", timeout=self.timeout_seconds * 1000)

                    # Download asset
                    download_btn = page.query_selector(".download-button, button[aria-label*='download' i], button[aria-label*='tải' i]")
                    if download_btn:
                        with page.expect_download(timeout=self.timeout_seconds * 1000) as download_info:
                            download_btn.click()
                        download = download_info.value
                        download.save_as(str(output_file))
                    else:
                        # Fallback: screenshot element or extract src
                        img_elem = page.query_selector(".generated-image img, flow-image-tile img, img.result-image")
                        if img_elem:
                            img_elem.screenshot(path=str(output_file))
                        else:
                            raise RuntimeError("GOOGLE_FLOW_IMAGE_EXTRACT_FAILED")
                finally:
                    browser.close()

            # Verify image output
            with Image.open(output_file) as im:
                im.verify()
                width, height = im.size
                if width < 512 or height < 512:
                    raise ValueError(f"Low resolution keyframe: {width}x{height}")

            return KeyframeGenerationResult(
                operation_id=request.operation_id,
                status="completed",
                provider_operation_id=f"flow-kf-{request.operation_id}",
                image_path=str(output_file),
                metadata={"provider_kind": self.provider_kind, "model": self.model},
            )
        except Exception as exc:
            logger.error("GoogleFlowKeyframeProvider error: %s", exc)
            return KeyframeGenerationResult(
                operation_id=request.operation_id,
                status="failed",
                error_code="GOOGLE_FLOW_KEYFRAME_FAILED",
                error_message=str(exc),
                metadata={"provider_kind": self.provider_kind},
            )

    def get_status(self, operation_id: str) -> KeyframeGenerationResult:
        output_file = self._output_path(operation_id)
        if output_file.is_file() and output_file.stat().st_size > 0:
            return KeyframeGenerationResult(
                operation_id=operation_id,
                status="completed",
                provider_operation_id=operation_id,
                image_path=str(output_file),
                metadata={"provider_kind": self.provider_kind},
            )
        return KeyframeGenerationResult(
            operation_id=operation_id,
            status="failed",
            provider_operation_id=operation_id,
            error_code="KEYFRAME_NOT_FOUND",
            error_message=f"Keyframe {operation_id} not found on disk",
            metadata={"provider_kind": self.provider_kind},
        )

    def generate_keyframe(self, request: Any) -> KeyframeGenerationResult:
        """Legacy compatibility method."""
        if hasattr(request, "operation_id") and hasattr(request, "prompt"):
            req = KeyframeGenerationRequest(
                operation_id=request.operation_id,
                workflow_id=getattr(request, "workflow_id", "pv-legacy"),
                project_id=getattr(request, "project_id", "project-legacy"),
                frame_id=getattr(request, "frame_id", "scene-1-start"),
                prompt=request.prompt,
                product_description=getattr(request, "product_description", request.prompt),
                reference_image_paths=tuple(getattr(request, "reference_image_paths", ())),
            )
            return self.submit(req)
        raise ValueError("Invalid request object for generate_keyframe")
