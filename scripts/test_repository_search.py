"""Focused tests for bounded GitHub repository search."""

from pathlib import Path
import sys
from unittest.mock import patch

sys.path.append(str(Path(__file__).resolve().parent.parent))

from core.repository_search import (
    extract_repository_query,
    format_repository_context,
    is_repository_search_request,
    search_repositories,
)


class FakeResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {
            "items": [{
                "full_name": "example/context-compressor",
                "html_url": "https://github.com/example/context-compressor",
                "description": "Reduce repeated agent context",
                "language": "Python",
                "stargazers_count": 123,
                "updated_at": "2026-01-01T00:00:00Z",
            }]
        }


def run_tests():
    assert is_repository_search_request("tìm repo giúp agent tiết kiệm token")
    assert extract_repository_query("/tim_repo tiết kiệm token cho agent") == "tiết kiệm token cho agent"
    with patch("core.repository_search.requests.get", return_value=FakeResponse()) as mocked:
        result = search_repositories("agent token")
    assert result["ok"] is True
    assert result["results"][0]["name"] == "example/context-compressor"
    assert mocked.call_args.kwargs["timeout"] == 12
    context = format_repository_context(result)
    assert "UNTRUSTED REFERENCE DATA" in context
    assert "https://github.com/example/context-compressor" in context
    print("repository search tests: PASS")


if __name__ == "__main__":
    run_tests()
