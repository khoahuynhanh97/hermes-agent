"""Google Flow Playwright Keyframe Generation Provider."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any

from PIL import Image
from playwright.sync_api import sync_playwright

from hermes_personal.integrations.video_factory.ports import KeyframeGenerationPort, KeyframeGenerationResult

logger = logging.getLogger(__name__)

KEYFRAME_NEGATIVE_PROMPT = "watermark, text, seller logo, marketplace badge, price tag, blurry, low quality"

class GoogleFlowKeyframeProvider(KeyframeGenerationPort):
    def __init__(
        self,
        profile_path: Path,
        chrome_profile_directory: str = "Default",
        output_dir: Path | None = None,
        model: str = "ImageFx / Imagen 3",
        timeout_seconds: float = 180.0,
        headless: bool = False,
    ) -> None:
        self.profile_path = profile_path
        self.chrome_profile_directory = chrome_profile_directory
        self.output_dir = output_dir or Path.cwd() / "keyframes"
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.headless = headless
        self.provider_kind = "google_flow"

    def generate_keyframe(self, request: Any) -> KeyframeGenerationResult:
        marker = f"hermes-kf-{hashlib.sha256(request.operation_id.encode()).hexdigest()[:16]}"
        output_file = self.output_dir / f"{request.operation_id}.png"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        with sync_playwright() as p:
            browser = p.chromium.launch_persistent_context(
                user_data_dir=str(self.profile_path / self.chrome_profile_directory),
                headless=self.headless,
                channel="chrome",
            )
            
            page = browser.pages[0]
            page.goto("https://flow.google.com/", timeout=self.timeout_seconds * 1000)

            # Verification: Check authentication
            # Note: Checking for profile avatar to ensure authenticated session is loaded
            is_auth = page.query_selector(".profile-button") is not None
            if not is_auth:
                # Fallback check for auth-required banner
                is_auth = page.query_selector(".auth-required") is None

            if not is_auth:
                browser.close()
                raise RuntimeError("GOOGLE_FLOW_AUTH_REQUIRED")

            # Injection: Input prompt (using keyboard to ensure triggering JS events)
            prompt_input = page.wait_for_selector("textarea[name='prompt']", timeout=10000)
            prompt_input.click()
            prompt_input.fill(f"{request.prompt}. Negative prompt: {KEYFRAME_NEGATIVE_PROMPT}")

            # Trigger Generation
            page.click("button.generate-button")

            # Wait for Result (Image container)
            page.wait_for_selector(".generated-image", timeout=self.timeout_seconds * 1000)
            
            # Download asset
            download_btn = page.query_selector(".download-button")
            with page.expect_download() as download_info:
                download_btn.click()
            download = download_info.value
            download.save_as(str(output_file))
            browser.close()


        # Verification: PIL
        with Image.open(output_file) as im:
            im.verify()
            width, height = im.size
            if width < 720 or height < 720:
                raise ValueError("Low resolution keyframe")

        return KeyframeGenerationResult(
            artifact_id=request.operation_id,
            relative_path=str(output_file.relative_to(self.output_dir)),
            digest=hashlib.sha256(output_file.read_bytes()).hexdigest(),
        )
