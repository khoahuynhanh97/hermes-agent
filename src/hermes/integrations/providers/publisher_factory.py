"""Publisher factory: resolves platform string to PublisherPort instance."""

from __future__ import annotations

from hermes.ports.publisher import PublisherPort


def get_publisher(platform: str) -> PublisherPort:
    """Return the appropriate PublisherPort for the given platform."""
    if platform == "tiktok":
        from .tiktok_publisher import TikTokPublisher
        return TikTokPublisher()
    if platform == "youtube_shorts":
        from .youtube_publisher import YouTubePublisher
        return YouTubePublisher()
    if platform == "instagram_reels":
        from .instagram_publisher import InstagramPublisher
        return InstagramPublisher()
    raise ValueError(f"Unsupported platform: {platform}")
