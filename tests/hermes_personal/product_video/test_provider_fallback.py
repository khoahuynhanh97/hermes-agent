"""Tests for multi-model provider fallback chain."""
from __future__ import annotations

import pytest

from hermes_personal.product_video.job_contracts import TerminalJobError
from hermes_personal.product_video.provider_fallback import (
    DEFAULT_PROVIDER_CHAIN,
    ProviderFallbackChain,
    create_fallback_chain,
)


def test_fallback_chain_default_providers():
    """Verify default provider chain is correctly configured."""
    chain = ProviderFallbackChain()
    assert chain.providers == DEFAULT_PROVIDER_CHAIN
    assert len(chain.providers) >= 4


def test_fallback_chain_custom_providers():
    """Verify custom provider list is used."""
    custom = ["provider_a", "provider_b"]
    chain = ProviderFallbackChain(providers=custom)
    assert chain.providers == custom


def test_first_provider_succeeds():
    """Test successful operation on first provider without fallback."""
    chain = ProviderFallbackChain(providers=["google_flow", "kling"])
    
    call_count = 0
    
    def operation(provider_kind: str) -> dict[str, str]:
        nonlocal call_count
        call_count += 1
        return {"status": "success", "provider": provider_kind}
    
    result, provider = chain.execute_with_fallback(
        operation, workflow_id="wf_test_001", operation_name="test_render"
    )
    
    assert call_count == 1
    assert result["status"] == "success"
    assert provider == "google_flow"


def test_fallback_to_second_provider():
    """Test fallback when first provider fails with TerminalJobError."""
    chain = ProviderFallbackChain(providers=["google_flow", "kling", "wan"])
    
    attempts = []
    
    def operation(provider_kind: str) -> dict[str, str]:
        attempts.append(provider_kind)
        if provider_kind == "google_flow":
            raise TerminalJobError("Provider timeout", code="PROVIDER_TIMEOUT")
        return {"status": "success", "provider": provider_kind}
    
    result, provider = chain.execute_with_fallback(
        operation, workflow_id="wf_test_002", operation_name="test_render"
    )
    
    assert len(attempts) == 2
    assert attempts == ["google_flow", "kling"]
    assert result["status"] == "success"
    assert provider == "kling"


def test_fallback_to_third_provider():
    """Test fallback across multiple failures."""
    chain = ProviderFallbackChain(providers=["google_flow", "kling", "wan", "vertex_ai"])
    
    attempts = []
    
    def operation(provider_kind: str) -> dict[str, str]:
        attempts.append(provider_kind)
        if provider_kind in ["google_flow", "kling"]:
            raise TerminalJobError(f"{provider_kind} unavailable", code="PROVIDER_UNAVAILABLE")
        return {"status": "success", "provider": provider_kind}
    
    result, provider = chain.execute_with_fallback(
        operation, workflow_id="wf_test_003", operation_name="test_render"
    )
    
    assert len(attempts) == 3
    assert attempts == ["google_flow", "kling", "wan"]
    assert result["status"] == "success"
    assert provider == "wan"


def test_all_providers_exhausted():
    """Test that TerminalJobError is raised when all providers fail."""
    chain = ProviderFallbackChain(providers=["google_flow", "kling"])
    
    def operation(provider_kind: str) -> dict[str, str]:
        raise TerminalJobError(f"{provider_kind} failed", code="PROVIDER_FAILED")
    
    with pytest.raises(TerminalJobError) as exc_info:
        chain.execute_with_fallback(
            operation, workflow_id="wf_test_004", operation_name="test_render"
        )
    
    assert exc_info.value.code == "ALL_PROVIDERS_EXHAUSTED"
    assert "google_flow:PROVIDER_FAILED" in str(exc_info.value)
    assert "kling:PROVIDER_FAILED" in str(exc_info.value)


def test_fallback_on_runtime_error():
    """Test fallback when provider raises RuntimeError."""
    chain = ProviderFallbackChain(providers=["google_flow", "kling"])
    
    attempts = []
    
    def operation(provider_kind: str) -> dict[str, str]:
        attempts.append(provider_kind)
        if provider_kind == "google_flow":
            raise RuntimeError("Unexpected error")
        return {"status": "success", "provider": provider_kind}
    
    result, provider = chain.execute_with_fallback(
        operation, workflow_id="wf_test_005", operation_name="test_render"
    )
    
    assert len(attempts) == 2
    assert attempts == ["google_flow", "kling"]
    assert provider == "kling"


def test_attempt_recorder_called():
    """Test that attempt recorder is invoked for each failure."""
    recorded_attempts = []
    
    def recorder(workflow_id: str, provider_kind: str, code: str, context: dict) -> None:
        recorded_attempts.append({
            "workflow_id": workflow_id,
            "provider": provider_kind,
            "code": code,
            "attempt": context.get("attempt"),
        })
    
    chain = ProviderFallbackChain(
        providers=["google_flow", "kling", "wan"],
        attempt_recorder=recorder,
    )
    
    def operation(provider_kind: str) -> dict[str, str]:
        if provider_kind in ["google_flow", "kling"]:
            raise TerminalJobError(f"{provider_kind} failed", code="TEST_FAILURE")
        return {"status": "success", "provider": provider_kind}
    
    result, provider = chain.execute_with_fallback(
        operation, workflow_id="wf_test_006", operation_name="test_render"
    )
    
    assert len(recorded_attempts) == 2
    assert recorded_attempts[0]["provider"] == "google_flow"
    assert recorded_attempts[0]["code"] == "TEST_FAILURE"
    assert recorded_attempts[0]["attempt"] == 1
    assert recorded_attempts[1]["provider"] == "kling"
    assert recorded_attempts[1]["attempt"] == 2


def test_create_fallback_chain_factory():
    """Test factory function creates chain correctly."""
    chain = create_fallback_chain(providers=["provider_a", "provider_b"])
    assert chain.providers == ["provider_a", "provider_b"]
    assert chain.attempt_recorder is None


def test_empty_provider_chain():
    """Test that empty provider chain raises error immediately."""
    chain = ProviderFallbackChain(providers=[])
    
    def operation(provider_kind: str) -> dict[str, str]:
        return {"status": "success"}
    
    with pytest.raises(TerminalJobError) as exc_info:
        chain.execute_with_fallback(
            operation, workflow_id="wf_test_007", operation_name="test_render"
        )
    
    assert exc_info.value.code == "EMPTY_PROVIDER_CHAIN"
