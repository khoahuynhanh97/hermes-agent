"""Mocked tests for the Hermes text LLM gateway."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch
import requests

sys.path.append(str(Path(__file__).resolve().parent.parent))

import core.llm_gateway as gateway


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.ok = status_code < 400
        self.text = str(payload)

    def json(self):
        return self._payload

    def raise_for_status(self):
        if not self.ok:
            raise RuntimeError(f"HTTP {self.status_code}")


def run_tests():
    names = [
        "LLM_PROVIDER",
        "LLM_ROUTER_BASE_URL",
        "LLM_MODEL_LEARNING",
        "LLM_RETRY_COUNT",
        "LLM_ENABLE_LEGACY_PROVIDER_FALLBACK",
    ]
    old_values = {name: os.environ.get(name) for name in names}
    os.environ["LLM_PROVIDER"] = "router"
    os.environ["LLM_ROUTER_BASE_URL"] = "http://127.0.0.1:20128/v1"
    os.environ["LLM_MODEL_LEARNING"] = "reason"
    os.environ["LLM_ENABLE_LEGACY_PROVIDER_FALLBACK"] = "0"
    os.environ["LLM_RETRY_COUNT"] = "0"
    try:
        try:
            gateway.complete("image", task_type="vision")
            raise AssertionError("vision must not use the text gateway")
        except gateway.LLMGatewayError as exc:
            assert "verified capable adapter" in str(exc)

        with patch(
            "core.llm_gateway.requests.post",
            return_value=FakeResponse({"model": "reason", "choices": [{"message": {"content": "ok"}}]}),
        ) as request:
            assert gateway.complete("hello", task_type="learning") == "ok"
            assert request.call_args.kwargs["json"]["model"] == "reason_combo"
            assert request.call_args.args[0].endswith("/chat/completions")

        with patch(
            "core.llm_gateway.requests.post",
            return_value=FakeResponse({"model": "reason", "choices": [{"message": {"content": "analysis-ok"}}]}),
        ) as request:
            assert gateway.complete("analyze", task_type="analysis") == "analysis-ok"
            assert request.call_args.kwargs["json"]["model"] == "reason_combo"

        with patch(
            "core.llm_gateway.requests.post",
            return_value=FakeResponse({"model": "reason", "choices": [{"message": {"content": "deep-ok"}}]}),
        ) as request:
            assert gateway.complete("deep analyze", task_type="deep_analysis") == "deep-ok"
            assert request.call_args.kwargs["json"]["model"] == "reason_combo"

        with patch(
            "core.llm_gateway.requests.post",
            return_value=FakeResponse({"model": "chat", "choices": [{"message": {"content": "script-ok"}}]}),
        ) as request:
            assert gateway.complete("write", task_type="script") == "script-ok"
            assert request.call_args.kwargs["json"]["model"] == "reason_combo"

        with patch("core.llm_gateway.requests.post", side_effect=ConnectionError("offline")):
            with patch("core.ai_router.chat", return_value="legacy-ok") as legacy:
                os.environ["LLM_ENABLE_LEGACY_PROVIDER_FALLBACK"] = "1"
                assert gateway.complete("hello", task_type="chat") == "legacy-ok"
                legacy.assert_called_once()

        os.environ["LLM_ENABLE_LEGACY_PROVIDER_FALLBACK"] = "0"
        os.environ["LLM_RETRY_COUNT"] = "1"
        with patch(
            "core.llm_gateway.requests.post",
            side_effect=[requests.ConnectionError("temporary"), FakeResponse({"model": "fast", "choices": [{"message": {"content": "retried"}}]})],
        ) as request:
            assert gateway.complete("retry", task_type="chat") == "retried"
            assert request.call_count == 2
    finally:
        for name, value in old_values.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

    print("llm gateway mocked tests: PASS")


if __name__ == "__main__":
    run_tests()
