import os
import pytest
from hermes.web_research_config import (
    WebResearchSettings,
    load_web_research_settings_from_env,
    validate_web_reference_batch,
    WebBatchRejected,
)


def test_default_web_research_settings():
    settings = WebResearchSettings()
    assert settings.crawl4ai_enabled is False
    assert settings.max_urls_per_run == 20
    assert settings.max_urls_per_host == 5
    assert settings.timeout_seconds == 30
    assert settings.max_html_bytes == 2097152
    assert settings.max_markdown_chars == 200000


def test_load_settings_from_env(monkeypatch):
    monkeypatch.setenv("CRAWL4AI_ENABLED", "1")
    monkeypatch.setenv("WEB_RESEARCH_MAX_URLS_PER_RUN", "10")
    monkeypatch.setenv("WEB_RESEARCH_MAX_URLS_PER_HOST", "3")
    monkeypatch.setenv("WEB_RESEARCH_TIMEOUT_SECONDS", "15")

    settings = load_web_research_settings_from_env()
    assert settings.crawl4ai_enabled is True
    assert settings.max_urls_per_run == 10
    assert settings.max_urls_per_host == 3
    assert settings.timeout_seconds == 15


def test_env_settings_cannot_exceed_hard_maximums(monkeypatch):
    monkeypatch.setenv("WEB_RESEARCH_MAX_URLS_PER_RUN", "100")
    monkeypatch.setenv("WEB_RESEARCH_MAX_URLS_PER_HOST", "50")

    settings = load_web_research_settings_from_env()
    assert settings.max_urls_per_run == 20
    assert settings.max_urls_per_host == 5


def test_batch_validation_passes_valid_urls():
    urls = ["https://example1.com/page", "https://example2.com/page"]
    validate_web_reference_batch(urls)
