from __future__ import annotations

import os
import unittest
from unittest.mock import patch

import requests


class LLMGatewayTests(unittest.TestCase):
    def test_all_generic_tasks_use_reason_combo(self) -> None:
        import core.llm_gateway as gateway

        with patch.dict(os.environ, {"LLM_MODEL_CHAT": "fast-model", "LLM_MODEL_LEARNING": "reason-model"}):
            for task_type in ("chat", "learning", "structured_extraction", "code", "analysis"):
                self.assertEqual(gateway._model_for_task(task_type), "reason_combo")

    def test_base_url_supports_shared_gateway_name(self) -> None:
        import core.llm_gateway as gateway

        with patch.dict(os.environ, {"LLM_BASE_URL": "http://127.0.0.1:20128/v1"}, clear=True):
            self.assertEqual(gateway._router_url("/models"), "http://127.0.0.1:20128/v1/models")

    def test_timeout_is_normalized_without_implicit_provider_fallback(self) -> None:
        import core.llm_gateway as gateway

        env = {
            "LLM_PROVIDER": "router",
            "LLM_RETRY_COUNT": "0",
            "LLM_ENABLE_LEGACY_PROVIDER_FALLBACK": "0",
        }
        with patch.dict(os.environ, env, clear=False), patch(
            "core.llm_gateway.requests.post", side_effect=requests.Timeout("slow")
        ) as request, patch("core.llm_gateway.logger"):
            with self.assertRaisesRegex(gateway.LLMGatewayError, "9Router request failed"):
                gateway.complete("hello")
            self.assertEqual(request.call_count, 1)

    def test_structured_output_is_validated(self) -> None:
        from hermes.llm import HermesLLMGateway, StructuredOutputError

        gateway = HermesLLMGateway(complete_fn=lambda **_kwargs: '{"title":"Lesson","items":["one"]}')
        result = gateway.structured(
            "extract",
            schema={"title": str, "items": list},
            task_type="structured_extraction",
        )
        self.assertEqual(result["title"], "Lesson")

        invalid = HermesLLMGateway(complete_fn=lambda **_kwargs: '{"title":12}')
        with self.assertRaises(StructuredOutputError):
            invalid.structured("extract", schema={"title": str, "items": list})

    def test_vision_capability_mismatch_is_rejected(self) -> None:
        from hermes.llm import CapabilityMismatchError, HermesLLMGateway

        with self.assertRaises(CapabilityMismatchError):
            HermesLLMGateway().complete("inspect image", task_type="vision")


if __name__ == "__main__":
    unittest.main()
