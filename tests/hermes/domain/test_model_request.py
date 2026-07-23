import pytest
from hermes.domain.model_request import ModelRequest, Message

def test_model_request_rejects_a_provider_name_as_a_tier():
    with pytest.raises(ValueError, match="Invalid model tier"):
        ModelRequest(tier="gemini", messages=[Message.user("hello")]) # type: ignore

def test_model_request_creation_with_valid_tiers():
    messages = [Message.user("hello")]
    request = ModelRequest.fast(messages)
    assert request.tier == "fast"
    assert request.messages == messages
