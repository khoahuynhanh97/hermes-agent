"""TikTok metadata adapters."""

from .public_reference import (
    InvalidTikTokReferenceError,
    TikTokPublicReferenceAdapter,
    TikTokReferenceTransportError,
)

__all__ = [
    "InvalidTikTokReferenceError",
    "TikTokPublicReferenceAdapter",
    "TikTokReferenceTransportError",
]
