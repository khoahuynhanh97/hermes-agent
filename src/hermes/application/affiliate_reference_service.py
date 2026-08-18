from __future__ import annotations

import hashlib
from typing import Any, Sequence

from hermes.adapters.tiktok.public_reference import (
    InvalidTikTokReferenceError,
    TikTokPublicReferenceAdapter,
    TikTokReferenceTransportError,
)


class PermanentReferenceError(ValueError):
    pass


class RetryableReferenceError(RuntimeError):
    pass


class TikTokReferenceCollector:
    """Associate explicit TikTok URLs with run products and persist metadata."""

    def __init__(self, repository: Any, adapter: Any | None = None):
        self._repository = repository
        self._adapter = adapter or TikTokPublicReferenceAdapter()

    def collect(
        self,
        owner_user_id: str,
        products: Sequence[Any],
        urls: Sequence[str],
    ) -> tuple[Any, ...]:
        if not urls:
            return ()
        owned = sorted(
            (product for product in products if product.owner_user_id == owner_user_id),
            key=lambda product: product.id,
        )
        if len(owned) != len(products) or not owned:
            raise PermanentReferenceError(
                "TikTok references require owner-scoped products"
            )
        collected = []
        for url in urls:
            digest = hashlib.sha256(url.strip().encode("utf-8")).digest()
            product = owned[int.from_bytes(digest[:8], "big") % len(owned)]
            try:
                reference = self._adapter.fetch(url, owner_user_id, product.id)
                collected.append(self._repository.save_reference(reference))
            except TikTokReferenceTransportError as error:
                raise RetryableReferenceError(str(error)) from error
            except (InvalidTikTokReferenceError, ValueError, LookupError) as error:
                raise PermanentReferenceError(str(error)) from error
        return tuple(collected)
