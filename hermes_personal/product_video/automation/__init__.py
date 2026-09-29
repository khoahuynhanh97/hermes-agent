"""Hermes Personal Product Video Automation package.

Provides exchange boundary contracts, atomic import repository, manifest importer,
and the unified ProductVideoCoordinator.
"""

from __future__ import annotations

from .contracts import (
    BatchStartResult,
    CandidateItem,
    ExchangeImage,
    ExchangeManifest,
    ExchangeProduct,
    compute_canonical_product_key,
    compute_product_key,
)
from .coordinator import ProductVideoCoordinator
from .importer import (
    DEFAULT_EXCHANGE_INBOX,
    ExchangeImporter,
    publish_daily_run_to_exchange,
)
from .repository import ClaimResult, DailyImportRepository

__all__ = [
    "BatchStartResult",
    "CandidateItem",
    "ClaimResult",
    "DailyImportRepository",
    "ExchangeImage",
    "ExchangeImporter",
    "ExchangeManifest",
    "ExchangeProduct",
    "ProductVideoCoordinator",
    "compute_canonical_product_key",
    "compute_product_key",
    "publish_daily_run_to_exchange",
    "DEFAULT_EXCHANGE_INBOX",
]
