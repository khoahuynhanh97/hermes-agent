from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import log1p


def _normalize_category(category: str) -> str:
    return category.strip().lower().replace(" ", "_").replace("-", "_")


@dataclass(frozen=True)
class ProductCandidate:
    owner_user_id: str
    platform: str
    external_product_id: str
    name: str
    category: str
    price_vnd: int
    sold_count: int | None
    rating: float | None
    review_count: int | None
    commission_rate: float | None
    shop_name: str
    product_url: str
    image_urls: tuple[str, ...]
    visual_signals: tuple[str, ...]
    source_type: str
    source_url: str
    authorization_scope: str
    rights_status: str
    content_hash: str


@dataclass(frozen=True)
class AffiliateProduct:
    id: str
    owner_user_id: str
    platform: str
    external_product_id: str
    name: str
    category: str
    price_vnd: int
    sold_count: int | None
    rating: float | None
    review_count: int | None
    commission_rate: float | None
    shop_name: str
    product_url: str
    image_urls: tuple[str, ...]
    visual_signals: tuple[str, ...]
    source_type: str
    source_url: str
    authorization_scope: str
    rights_status: str
    content_hash: str
    created_at: str
    updated_at: str
    score: float | None = None
    score_reason: str = ""
    score_confidence: str = "low"


@dataclass(frozen=True)
class ProductSnapshot:
    product_id: str
    snapshot_date: str
    price_vnd: int
    sold_count: int | None
    rating: float | None
    review_count: int | None
    commission_rate: float | None
    collected_at: str


@dataclass(frozen=True)
class ScoreBreakdown:
    total: float
    components: dict[str, float]
    reason: str
    confidence: str
    growth_rate: float | None


@dataclass(frozen=True)
class EligibilityDecision:
    eligible: bool
    reason: str


@dataclass(frozen=True)
class ReferenceMetadata:
    id: str
    owner_user_id: str
    product_id: str
    platform: str
    source_url: str
    title: str
    author_name: str
    author_url: str
    thumbnail_url: str
    caption: str
    embed_html: str
    authorization_scope: str
    rights_status: str
    media_local_path: str
    collected_at: str
    source_type: str = "tiktok_oembed"
    content_hash: str = ""


@dataclass(frozen=True)
class ContentIdea:
    id: str
    owner_user_id: str
    product_id: str
    run_id: str
    audience: str
    angle: str
    rationale: str
    created_at: str
    score: float = 0.0
    rank: int = 0
    selected: bool = False


@dataclass(frozen=True)
class ResearchBrief:
    id: str
    owner_user_id: str
    product_id: str
    run_id: str
    revision: int
    verified_specs: tuple[dict[str, object], ...]
    strengths: tuple[str, ...]
    limitations: tuple[str, ...]
    unverified_claims: tuple[str, ...]
    reference_patterns: tuple[str, ...]
    created_at: str


class PackageStatus(str, Enum):
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REVISION_REQUESTED = "revision_requested"
    REJECTED = "rejected"


@dataclass(frozen=True)
class ContentPackage:
    id: str
    owner_user_id: str
    product_id: str
    run_id: str
    revision: int
    status: PackageStatus
    audience: str
    angle: str
    angle_reason: str
    hook: str
    script: str
    duration_seconds: int
    storyboard: tuple[dict[str, object], ...]
    ai_prompts: tuple[str, ...]
    voiceover_plan: str
    text_overlays: tuple[str, ...]
    claims: tuple[dict[str, object], ...]
    warnings: tuple[str, ...]
    asset_rights: dict[str, str]
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class ProjectionResult:
    ok: bool
    retryable: bool
    detail: str


class ProductPolicy:
    _ALLOWED_CATEGORIES = frozenset(
        {
            "keyboard",
            "keyboards",
            "mouse",
            "mice",
            "headphone",
            "headphones",
            "earphone",
            "earphones",
            "mini_fan",
            "fan",
            "desk_light",
            "smart_light",
            "light",
            "lamp",
            "hub",
            "stand",
            "cable",
            "desk_accessory",
            "gaming_accessory",
            "workspace_accessory",
        }
    )
    _GENERAL_MIN_PRICE = 200_000
    _GENERAL_MAX_PRICE = 500_000
    _KEYBOARD_MAX_PRICE = 1_500_000

    def evaluate(self, product: AffiliateProduct) -> EligibilityDecision:
        category = _normalize_category(product.category)
        if category not in self._ALLOWED_CATEGORIES:
            return EligibilityDecision(False, "category is outside the supported technology niche")

        maximum_price = (
            self._KEYBOARD_MAX_PRICE if category in {"keyboard", "keyboards"} else self._GENERAL_MAX_PRICE
        )
        if not self._GENERAL_MIN_PRICE <= product.price_vnd <= maximum_price:
            return EligibilityDecision(
                False,
                f"price must be between {self._GENERAL_MIN_PRICE} and {maximum_price} VND",
            )
        return EligibilityDecision(True, "eligible technology product within the price policy")


class ProductScorer:
    _VISUAL_SIGNAL_WEIGHTS = {
        "light": 8.0,
        "rgb": 8.0,
        "movement": 8.0,
        "transformation": 8.0,
        "before_after": 7.0,
        "audible_interaction": 5.0,
        "tactile_interaction": 5.0,
        "visible_problem_solution": 5.0,
        "multiple_scenes": 3.0,
        "compositing_ready": 2.0,
    }

    def score(
        self,
        product: AffiliateProduct,
        *,
        category_sales: tuple[int, int],
        previous_sold_count: int | None,
        seen_before: bool,
    ) -> ScoreBreakdown:
        growth_rate = self._growth_rate(product.sold_count, previous_sold_count)
        components = {
            "sales": self._sales_score(product.sold_count, category_sales, growth_rate),
            "visual": self._visual_score(product.visual_signals),
            "price": self._price_score(product),
            "trust": self._trust_score(product),
            "commission": self._commission_score(product.commission_rate),
            "novelty": 0.0 if seen_before else 2.0,
        }
        components = {name: round(score, 2) for name, score in components.items()}
        total = round(sum(components.values()), 2)
        confidence = self._confidence(product, previous_sold_count)
        reason = "; ".join(f"{name}={score:g}" for name, score in components.items())
        return ScoreBreakdown(total, components, reason, confidence, growth_rate)

    @staticmethod
    def _growth_rate(current: int | None, previous: int | None) -> float | None:
        if current is None or previous is None or previous <= 0:
            return None
        return round((current - previous) / previous, 4)

    @staticmethod
    def _sales_score(
        sold_count: int | None,
        category_sales: tuple[int, int],
        growth_rate: float | None,
    ) -> float:
        if sold_count is None:
            return 0.0
        lower, upper = sorted(max(0, value) for value in category_sales)
        if upper <= lower:
            volume = 36.0 if sold_count >= upper and upper > 0 else 0.0
        else:
            normalized = (log1p(max(0, sold_count)) - log1p(lower)) / (log1p(upper) - log1p(lower))
            volume = 36.0 * min(1.0, max(0.0, normalized))
        growth = 0.0 if growth_rate is None else 9.0 * min(1.0, max(0.0, growth_rate / 0.2))
        return min(45.0, volume + growth)

    def _visual_score(self, signals: tuple[str, ...]) -> float:
        return min(30.0, sum(self._VISUAL_SIGNAL_WEIGHTS.get(signal.lower(), 0.0) for signal in set(signals)))

    @staticmethod
    def _price_score(product: AffiliateProduct) -> float:
        category = _normalize_category(product.category)
        maximum = 1_500_000 if category in {"keyboard", "keyboards"} else 500_000
        if not 200_000 <= product.price_vnd <= maximum:
            return 0.0
        midpoint = (200_000 + maximum) / 2
        half_range = (maximum - 200_000) / 2
        return 5.0 + 5.0 * (1.0 - abs(product.price_vnd - midpoint) / half_range)

    @staticmethod
    def _trust_score(product: AffiliateProduct) -> float:
        rating = 0.0 if product.rating is None else 5.0 * min(1.0, max(0.0, product.rating / 5))
        reviews = 0.0 if product.review_count is None else 2.0 * min(1.0, log1p(max(0, product.review_count)) / log1p(1_000))
        shop = 1.0 if product.shop_name.strip() else 0.0
        return min(8.0, rating + reviews + shop)

    @staticmethod
    def _commission_score(commission_rate: float | None) -> float:
        if commission_rate is None:
            return 0.0
        return 5.0 * min(1.0, max(0.0, commission_rate / 0.15))

    @staticmethod
    def _confidence(product: AffiliateProduct, previous_sold_count: int | None) -> str:
        has_core_evidence = all(
            (
                product.sold_count is not None,
                product.rating is not None,
                product.review_count is not None,
                product.commission_rate is not None,
                bool(product.image_urls),
                bool(product.visual_signals),
            )
        )
        if not has_core_evidence:
            return "low"
        return "high" if previous_sold_count is not None else "medium"
