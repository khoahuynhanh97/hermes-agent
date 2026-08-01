import pytest

from hermes.adapters.tiktok.public_reference import TikTokPublicReferenceAdapter


def test_only_tiktok_public_video_urls_are_accepted():
    adapter = TikTokPublicReferenceAdapter(get_json=lambda *_args, **_kwargs: {})

    with pytest.raises(ValueError, match="TikTok"):
        adapter.fetch("https://example.com/video/1", "42", "shopee:101")


def test_oembed_metadata_is_reference_only():
    calls = []

    def get_json(url, **kwargs):
        calls.append((url, kwargs))
        return {
            "title": "Desk setup idea",
            "author_name": "creator",
            "author_url": "https://www.tiktok.com/@creator",
            "thumbnail_url": "https://example.com/thumb.jpg",
        }

    reference = TikTokPublicReferenceAdapter(get_json=get_json).fetch(
        "https://www.tiktok.com/@creator/video/123", "42", "shopee:101"
    )

    assert calls[0][0] == "https://www.tiktok.com/oembed"
    assert reference.rights_status == "reference_only"
    assert reference.media_local_path == ""


@pytest.mark.parametrize(
    "url",
    [
        "http://www.tiktok.com/@creator/video/123",
        "https://evil.tiktok.com/@creator/video/123",
        "https://www.tiktok.com/@creator/photo/123",
    ],
)
def test_rejects_non_public_tiktok_urls(url):
    adapter = TikTokPublicReferenceAdapter(get_json=lambda *_args, **_kwargs: {})

    with pytest.raises(ValueError, match="TikTok"):
        adapter.fetch(url, "42", "shopee:101")


def test_rejects_oversized_metadata_text():
    adapter = TikTokPublicReferenceAdapter(
        get_json=lambda *_args, **_kwargs: {"title": "x" * 1001}
    )

    with pytest.raises(ValueError, match="length"):
        adapter.fetch("https://www.tiktok.com/@creator/video/123", "42", "shopee:101")
