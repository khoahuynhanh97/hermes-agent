from hermes.domain.results import Result
import pytest


def test_failure_result_keeps_a_stable_error_code():
    result = Result.failure("not_found", "Project p-1 was not found")
    assert result.ok is False
    assert result.error_code == "not_found"
    assert result.value is None


def test_success_result_is_ok_and_contains_value():
    result = Result.success("test_value")
    assert result.ok is True
    assert result.value == "test_value"
    assert result.error_code is None
    assert result.message is None


def test_failure_result_must_have_error_code():
    with pytest.raises(ValueError, match="error_code cannot be empty for a failure result"):
        Result.failure("", "message")
