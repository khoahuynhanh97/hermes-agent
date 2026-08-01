import pytest
from hermes.application.web_url_policy import PublicWebUrlPolicy
from hermes.domain.web_document import UnsafeWebUrl


def fake_public_resolver(host: str) -> list[str]:
    mapping = {
        "example.com": ["93.184.216.34"],
        "public.example": ["93.184.216.34"],
        "internal.example": ["10.0.0.8"],
        "localhost": ["127.0.0.1"],
    }
    if host in mapping:
        return mapping[host]
    # Default mock IP for any other valid host
    return ["93.184.216.34"]


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "http://127.0.0.1/admin",
        "http://169.254.169.254/latest/meta-data",
        "http://user:pass@example.com/",
        "https://example.com:8443/",
        "https://www.shopee.vn/product/1",
        "https://www.tiktok.com/@x/video/1",
        "ftp://example.com/file",
        "http://internal.example/api",
    ],
)
def test_policy_rejects_unsafe_or_disallowed_urls(url):
    policy = PublicWebUrlPolicy(resolver=fake_public_resolver)
    with pytest.raises(UnsafeWebUrl):
        policy.validate(url)


def test_policy_revalidates_redirect_destination():
    policy = PublicWebUrlPolicy(
        resolver=lambda host: {
            "public.example": ["93.184.216.34"],
            "internal.example": ["10.0.0.8"],
        }[host]
    )
    first = policy.validate("https://public.example/article")
    assert first == "https://public.example/article"
    with pytest.raises(UnsafeWebUrl):
        policy.validate_redirect(first, "http://internal.example/admin")


def test_policy_drops_fragment_and_normalizes():
    policy = PublicWebUrlPolicy(resolver=fake_public_resolver)
    normalized = policy.validate("https://example.com/review#section2")
    assert normalized == "https://example.com/review"
