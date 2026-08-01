import pytest
from hermes.domain.web_document import WebFetchRequest, WebFetchFailure
from hermes.application.web_url_policy import PublicWebUrlPolicy
from hermes.adapters.web.static_fetcher import StaticWebDocumentFetcher


class FakeResponse:
    def __init__(self, status_code=200, headers=None, content=b"", url="https://example.com/lamp"):
        self.status_code = status_code
        self.headers = headers or {"Content-Type": "text/html; charset=utf-8"}
        self._content = content
        self.url = url

    def iter_content(self, chunk_size=8192):
        yield self._content


class FakeSession:
    def __init__(self, html: str, status_code: int = 200, headers: dict = None):
        self.html = html
        self.status_code = status_code
        self.headers = headers or {"Content-Type": "text/html; charset=utf-8"}

    def get(self, url, allow_redirects=False, stream=True, timeout=30, headers=None):
        return FakeResponse(
            status_code=self.status_code,
            headers=self.headers,
            content=self.html.encode("utf-8"),
            url=url,
        )


class FakeRedirectSession:
    def __init__(self, start_url: str, location: str):
        self.start_url = start_url
        self.location = location

    def get(self, url, allow_redirects=False, stream=True, timeout=30, headers=None):
        if url == self.start_url:
            return FakeResponse(
                status_code=302,
                headers={"Location": self.location},
                url=url,
            )
        return FakeResponse(status_code=200, content=b"<html><body>Redirected</body></html>", url=url)


def public_policy():
    return PublicWebUrlPolicy(
        resolver=lambda host: {
            "example.com": ["93.184.216.34"],
            "public.example": ["93.184.216.34"],
            "internal.example": ["10.0.0.8"],
        }.get(host, ["93.184.216.34"])
    )


def public_request(url="https://example.com/lamp"):
    return WebFetchRequest(
        owner_user_id="42",
        run_id="run-1",
        product_id="prod-1",
        url=url,
    )


def test_static_fetcher_returns_clean_bounded_markdown():
    session = FakeSession(
        html="<html><head><title>Desk lamp review</title></head>"
             "<body><nav>Menu</nav><main><h1>Desk lamp</h1><p>Three modes.</p></main>"
             "<script>alert(1)</script></body></html>"
    )
    document = StaticWebDocumentFetcher(
        session=session,
        policy=public_policy(),
    ).fetch(public_request("https://example.com/lamp"))
    assert document.acquisition_method == "static_http"
    assert document.title == "Desk lamp review"
    assert "Three modes." in document.markdown
    assert "Menu" not in document.markdown
    assert "alert(1)" not in document.markdown


def test_static_fetcher_revalidates_every_redirect():
    session = FakeRedirectSession(
        "https://public.example/start",
        location="http://127.0.0.1/admin",
    )
    with pytest.raises(WebFetchFailure) as exc_info:
        StaticWebDocumentFetcher(session=session, policy=public_policy()).fetch(
            public_request("https://public.example/start")
        )
    assert exc_info.value.code == "unsafe_url"


def test_static_fetcher_rejects_unsupported_content_type():
    session = FakeSession(
        html="binary data",
        headers={"Content-Type": "application/pdf"},
    )
    with pytest.raises(WebFetchFailure) as exc_info:
        StaticWebDocumentFetcher(session=session, policy=public_policy()).fetch(
            public_request("https://example.com/doc.pdf")
        )
    assert exc_info.value.code == "unsupported_content"
