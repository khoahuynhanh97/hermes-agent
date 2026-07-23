import httpx
import pytest
from hermes.adapters.router.nine_router_gateway import NineRouterGateway
from hermes.domain.model_request import ModelRequest, Message, ModelTier


@pytest.fixture
def gateway(monkeypatch):
    monkeypatch.setenv("LLM_ROUTER_API_KEY", "test-api-key")
    return NineRouterGateway(base_url="http://test-9router")


def test_gateway_sends_the_reason_alias_and_normalizes_content(httpx_mock, gateway):
    httpx_mock.add_response(
        url="http://test-9router/v1/chat/completions",
        method="POST",
        json={
            "choices": [{"message": {"content": "answer"}}],
            "model": "selected_reason_model",
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        },
        status_code=200,
    )
    request = ModelRequest.reason([Message.user("analyze this")])
    result = gateway.complete(request)

    assert result.ok
    assert result.value.content == "answer"
    assert result.value.model == "selected_reason_model"
    assert result.value.usage == {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}

    sent_request = httpx_mock.get_requests()[0]
    assert sent_request.url == "http://test-9router/v1/chat/completions"
    assert sent_request.headers["Authorization"] == "Bearer test-api-key"
    import json
    # Use json.loads to compare dictionaries
    request_data = json.loads(sent_request.content.decode("utf-8"))
    assert request_data == {"model": "reason", "messages": [{"role": "user", "content": "analyze this"}], "temperature": 0.7}



def test_gateway_handles_http_errors(httpx_mock, gateway):
    httpx_mock.add_response(
        url="http://test-9router/v1/chat/completions",
        method="POST",
        status_code=500,
        content="Internal Server Error",
    )
    request = ModelRequest.fast([Message.user("hello")])
    result = gateway.complete(request)

    assert not result.ok
    assert result.error_code == "unavailable"
    assert "HTTP error: 500" in result.message


def test_gateway_handles_network_errors(monkeypatch, gateway):
    def mock_post(*args, **kwargs):
        raise httpx.RequestError("Network is down", request=httpx.Request("POST", "http://test-9router"))

    monkeypatch.setattr(gateway.client, "post", mock_post)

    request = ModelRequest.fast([Message.user("hello")])
    result = gateway.complete(request)

    assert not result.ok
    assert result.error_code == "unavailable"
    assert "Request error: Network is down" in result.message


def test_gateway_handles_missing_keys_in_response(httpx_mock, gateway):
    httpx_mock.add_response(
        url="http://test-9router/v1/chat/completions",
        method="POST",
        json={"choices": []},  # Missing 'message' key
        status_code=200,
    )
    request = ModelRequest.fast([Message.user("hello")])
    result = gateway.complete(request)

    assert not result.ok
    assert result.error_code == "invalid_response"
    assert "Missing" in result.message # Check for a message about missing key/message


def test_gateway_sends_json_schema_when_provided(httpx_mock, gateway):
    json_schema = {"type": "object", "properties": {"name": {"type": "string"}}}
    httpx_mock.add_response(
        url="http://test-9router/v1/chat/completions",
        method="POST",
        json={
            "choices": [{"message": {"content": '{"name": "test"}'}}],
            "model": "selected_reason_model",
        },
        status_code=200,
    )
    request = ModelRequest.reason([Message.user("generate json")], json_schema=json_schema)
    result = gateway.complete(request)

    assert result.ok
    sent_request = httpx_mock.get_requests()[0]
    import json
    # Use json.loads to compare dictionaries
    request_data = json.loads(sent_request.content.decode("utf-8"))
    assert request_data["response_format"] == {"type": "json_object", "schema": json_schema}