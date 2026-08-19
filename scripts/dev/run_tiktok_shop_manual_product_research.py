from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from hermes.adapters.affiliate.manual_source import ManualProductSource
from hermes.adapters.google.sheets_projection import DisabledSheetsProjection
from hermes.adapters.local.sheet_projection import LocalSheetProjection
from hermes.adapters.sqlite.affiliate_research_repository import (
    SQLiteAffiliateResearchRepository,
)
from hermes.application.affiliate_catalog_service import AffiliateCatalogService
from hermes.application.affiliate_content_service import AffiliateContentService
from hermes.application.product_research_intent import ProductResearchIntent
from hermes.application.product_research_script_workflow import (
    ProductResearchScriptWorkflow,
)
from hermes.application.product_source_selector import ProductSourceSelection
from hermes.db import Database
from hermes.domain.affiliate_research import ProductCandidate


OWNER_USER_ID = "user"
REQUEST = "tim 3 san pham hot trend nganh cong nghe tren TikTok Shop gia 200k-500k VND"


PRODUCTS = (
    {
        "external_product_id": "tiktok-mic-gochek",
        "name": "Micro thu am khong day Type-C GoChek/K9 cho TikTok livestream",
        "category": "workspace_accessory",
        "price_vnd": 329_000,
        "sold_count": 28_800,
        "rating": 4.9,
        "review_count": 2_300,
        "product_url": "https://shop-vn.tiktok.com/pdp/1730291191517514501",
        "visual_signals": ("audio_demo", "before_after", "creator_tool"),
    },
    {
        "external_product_id": "tiktok-monitor-rgb",
        "name": "Den monitor bar / den ban kep desktop RGB chong choi",
        "category": "desk_light",
        "price_vnd": 399_000,
        "sold_count": 4_800,
        "rating": 4.7,
        "review_count": 740,
        "product_url": "https://shop-vn.tiktok.com/pdp/1729655993620662620",
        "visual_signals": ("light", "rgb", "desk_setup"),
    },
    {
        "external_product_id": "tiktok-usbc-hub",
        "name": "Hub USB-C TP-Link / HDMI 4K da cong cho laptop va iPad",
        "category": "hub",
        "price_vnd": 459_000,
        "sold_count": 2_100,
        "rating": 4.8,
        "review_count": 510,
        "product_url": "https://shop-vn.tiktok.com/pdp/1731011745685736264",
        "visual_signals": ("connectivity", "workspace_upgrade", "port_expansion"),
    },
)


def _candidate(product: dict[str, object]) -> ProductCandidate:
    fingerprint = (
        f"{product['external_product_id']}:{product['name']}:"
        f"{product['price_vnd']}:{product['sold_count']}"
    )
    return ProductCandidate(
        owner_user_id=OWNER_USER_ID,
        platform="tiktok_shop",
        external_product_id=str(product["external_product_id"]),
        name=str(product["name"]),
        category=str(product["category"]),
        price_vnd=int(product["price_vnd"]),
        sold_count=int(product["sold_count"]),
        rating=float(product["rating"]),
        review_count=int(product["review_count"]),
        commission_rate=None,
        shop_name="TikTok Shop VN",
        product_url=str(product["product_url"]),
        image_urls=(),
        visual_signals=tuple(product["visual_signals"]),
        source_type="manual_tiktok_shop_feed",
        source_url=str(product["product_url"]),
        authorization_scope="public_product_page",
        rights_status="reference_only",
        content_hash=hashlib.sha256(fingerprint.encode("utf-8")).hexdigest(),
    )


class ManualTikTokSourceSelector:
    def __init__(self, candidates: tuple[ProductCandidate, ...]):
        self._source = ManualProductSource(candidates)

    def select(self, intent: ProductResearchIntent) -> ProductSourceSelection:
        return ProductSourceSelection(
            status="manual_feed",
            source=self._source,
            warnings=(
                "TikTok Shop crawler disabled; using verified manual feed for 3 products.",
            ),
        )


class DeterministicContentGateway:
    def generate(self, product, references, **kwargs):  # noqa: ANN001, ANN003
        script_by_category = {
            "workspace_accessory": (
                f"Mo dau bang canh quay clip bi re, nhieu tap am. Dat {product.name} "
                "vao khung hinh, gan dau thu Type-C, roi quay canh so sanh am thanh "
                "truoc va sau. Nhan man nguoi xem nen nghe bang tai nghe de thay "
                "khac biet, sau do hien checklist: phu hop livestream, quay review, "
                "hoc online; can kiem tra cong ket noi va gia live truoc khi mua."
            ),
            "desk_light": (
                f"Bat dau voi goc ban lam viec bi toi va bi bong man hinh. Kep {product.name} "
                "len setup, chuyen lan luot cac che do sang am, sang lanh va RGB. Quay "
                "canh truoc/sau tren cung mot goc may de thay mat ban ro hon, roi ket "
                "bang khuyen nghi cho nguoi lam viec dem, quay setup, gaming desk."
            ),
            "hub": (
                f"Mo canh laptop chi co mot cong USB-C va ban lam viec day day cap. Cam {product.name} "
                "vao, ket noi chuot, USB, man hinh HDMI va sac PD theo tung beat cat. "
                "Chot bang thong diep: ai dung laptop mong/iPad nen xem hub da cong, "
                "nhung phai kiem tra dung variant HDMI/PD/LAN truoc khi dat hang."
            ),
        }
        prompt_by_category = {
            "workspace_accessory": (
                "vertical TikTok audio comparison scene, compact wireless lavalier "
                "microphone Type-C receiver, creator desk, waveform overlay, before "
                "and after sound demo, practical product review"
            ),
            "desk_light": (
                "vertical TikTok desk setup transformation, monitor light bar with RGB "
                "back glow, anti-glare workspace lighting, split before after lighting, "
                "clean gaming and work desk"
            ),
            "hub": (
                "vertical TikTok laptop workstation upgrade, USB-C hub connected to "
                "HDMI monitor and accessories, cable organization, close-up port "
                "expansion demo, clean productivity desk"
            ),
        }
        script = script_by_category.get(product.category, f"Demo {product.name} in 30 seconds.")
        hook_by_category = {
            "workspace_accessory": "Thu am clip bi re? Thu test micro cai ao Type-C truoc khi doi dien thoai.",
            "desk_light": "Goc ban toi va bi loi anh sang? Mot thanh den co the doi ca khung hinh.",
            "hub": "Laptop chi mot cong USB-C? Day la cach bien no thanh mini workstation.",
        }
        prompt = prompt_by_category.get(
            product.category,
            f"9:16 TikTok product demo, close-up of {product.name}, practical review",
        )
        return {
            "audience": (
                "Nguoi lam noi dung TikTok va dan van phong thich do cong nghe gia tot"
            ),
            "angle": f"{product.name}: demo loi ich nhin thay ngay trong 30 giay",
            "angle_reason": (
                "San pham co tin hieu de quay demo, gia nam trong nguong "
                "200-500k va phu hop affiliate short video."
            ),
            "hook": hook_by_category.get(product.category, f"Demo nhanh {product.name}"),
            "script": script,
            "duration_seconds": 35,
            "storyboard": [
                {"visual": "Can canh van de truoc khi dung san pham", "start": 0, "end": 5},
                {"visual": f"Unbox va can canh {product.name}", "start": 5, "end": 12},
                {
                    "visual": "Demo tinh nang chinh theo goc quay before/after",
                    "start": 12,
                    "end": 25,
                },
                {
                    "visual": "Hien thi gia, doi tuong phu hop, CTA kiem tra deal",
                    "start": 25,
                    "end": 35,
                },
            ],
            "ai_prompts": [
                prompt,
                (
                    f"macro shot of {product.name}, hands demonstrating practical use, "
                    "bright practical lighting, no exaggerated claims"
                ),
            ],
            "voiceover_plan": (
                "Giong nhanh, ro, chia 4 nhip: van de, demo, loi ich, luu y gia live."
            ),
            "text_overlays": [
                "Duoi 500k",
                "Demo that trong 30s",
                "Kiem tra gia live truoc khi mua",
            ],
            "claims": [
                {
                    "text": (
                        "Gia tham chieu nam trong khoang 200-500k VND: "
                        f"{product.price_vnd} VND"
                    ),
                    "evidence_url": product.product_url,
                },
                {
                    "text": (
                        "Nguon san pham tu trang TikTok Shop cong khai: "
                        f"{product.name}"
                    ),
                    "evidence_url": product.product_url,
                },
            ],
            "warnings": [
                "Khong khang dinh da tu su dung san pham neu chua co test that.",
                "Gia va so ban TikTok Shop co the thay doi theo flash sale/variant.",
            ],
        }


def main() -> int:
    candidates = tuple(_candidate(product) for product in PRODUCTS)
    repository = SQLiteAffiliateResearchRepository(Database())
    output_dir = Path(
        os.environ.get(
            "PRODUCT_RESEARCH_OUTPUT_DIR",
            str(Path(__file__).resolve().parents[2] / ".pytest-tmp" / "tiktok-product-run" / "product_research_exports"),
        )
    )
    workflow = ProductResearchScriptWorkflow(
        repository=repository,
        catalog_service=AffiliateCatalogService(repository),
        content_service=AffiliateContentService(repository, DeterministicContentGateway()),
        source_selector=ManualTikTokSourceSelector(candidates),
        local_projection=LocalSheetProjection(repository, output_dir),
        google_projection=DisabledSheetsProjection(),
        shortlist_limit=25,
    )
    intent = ProductResearchIntent.from_message(OWNER_USER_ID, REQUEST)
    result = workflow.run(intent)
    print(result.to_report())
    print("PAYLOAD_JSON=" + json.dumps(result.to_payload(), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
