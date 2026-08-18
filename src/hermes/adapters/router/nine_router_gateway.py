from __future__ import annotations

import os
from typing import Any

import httpx

from hermes.domain.model_request import ModelRequest, ModelResponse
from hermes.domain.results import Result
from hermes.ports.model_gateway import ModelGateway


class NineRouterGateway(ModelGateway):
    def __init__(self, base_url: str | None = None, api_key: str | None = None):
        self.base_url = base_url or os.environ.get("LLM_BASE_URL", "http://localhost:9000")
        self.api_key = api_key or os.environ.get("LLM_ROUTER_API_KEY")
        if not self.api_key:
            raise ValueError("LLM_ROUTER_API_KEY environment variable not set.")

        self.client = httpx.Client(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(5.0, connect=10.0),
        )

    def complete(self, request: ModelRequest) -> Result[ModelResponse]:
        try:
            payload: dict[str, Any] = {
                "model": request.tier,  # 9Router uses 'model' for tier alias
                "messages": [{"role": m.role.value, "content": m.content} for m in request.messages],
                "temperature": 0.7, # Default temperature
            }
            if request.json_schema:
                payload["response_format"] = {"type": "json_object", "schema": request.json_schema}
            
            response = self.client.post("/v1/chat/completions", json=payload, timeout=request.timeout_seconds)
            response.raise_for_status()
            
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            model_name = data["model"]
            usage = data.get("usage", {})

            return Result.success(ModelResponse(content=content, model=model_name, usage=usage))
        except httpx.HTTPStatusError as e:
            return Result.failure("unavailable", f"HTTP error: {e.response.status_code} - {e.response.text}")
        except httpx.RequestError as e:
            return Result.failure("unavailable", f"Request error: {e}")
        except KeyError as e:
            return Result.failure("invalid_response", f"Missing key in response: {e}")
        except IndexError as e:
            return Result.failure("invalid_response", f"Missing message in response: {e}")
        except Exception as e:
            return Result.failure("unknown_error", f"An unexpected error occurred: {e}")

