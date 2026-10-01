"""Exchange boundary importer and publisher for the independent inbox contract."""

from __future__ import annotations

import json
import os
import re
import shutil
import unicodedata
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image

from .contracts import (
    ExchangeImage,
    ExchangeManifest,
    ExchangeProduct,
    compute_canonical_product_key,
    compute_product_key,
)

DEFAULT_EXCHANGE_INBOX = Path(r"D:\work\Personal\hermes-product-video-exchange\inbox")
_AMBIGUOUS_VARIANT = re.compile(r"\b\d+\s*[a-zA-Z]*\s*/\s*\d+", re.IGNORECASE)
_URL_LIKE_NAME = re.compile(r"^[^\s/]+\.[a-z]{2,}(?:\.[a-z]{2,})?/", re.IGNORECASE)
_PRICE_LIKE_MODEL = re.compile(r"^\d+(?:[.,]\d+)?\s*(?:k|tr|đ|vnd)$", re.IGNORECASE)
_PROMOTIONAL_NOISE_MODEL = re.compile(
    r"^(?:sale|top|giam|giảm|hot|deal|combo|freeship|chinh\s*hang|chính\s*hãng)\b|\b\d+\s*%"
    r"|^[^\w\s]+|\b\d+\s*(?:k|tr|đ|vnd|usd)\b",
    re.IGNORECASE,
)
_RANKING_LIST_PATTERN = re.compile(r"^top\s*\d+\b", re.IGNORECASE)


def _identity_words(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii").lower()
    return " ".join(re.findall(r"[a-z0-9]+", normalized))


class ExchangeImporter:
    """Reads and validates versioned immutable exchange batches from inbox."""

    def __init__(self, inbox_root: Path | None = None) -> None:
        if inbox_root is not None:
            self.inbox_root = Path(inbox_root)
        else:
            env_inbox = os.environ.get("HERMES_EXCHANGE_INBOX")
            self.inbox_root = Path(env_inbox) if env_inbox else DEFAULT_EXCHANGE_INBOX

    def find_latest_ready_batch(self, target_date: date | None = None) -> Path:
        """Locate the latest batch directory containing a valid READY signal file."""
        if not self.inbox_root.is_dir():
            raise FileNotFoundError(f"Exchange inbox directory not found: {self.inbox_root}")

        if target_date is not None:
            day_dir = self.inbox_root / target_date.isoformat()
            if not day_dir.is_dir():
                raise FileNotFoundError(f"No exchange batches found for date: {target_date.isoformat()}")
            candidates = sorted(day_dir.glob("run_*"), reverse=True)
        else:
            candidates = sorted(self.inbox_root.glob("????-??-??/run_*"), reverse=True)

        for candidate in candidates:
            if (candidate / "READY").is_file() and (candidate / "manifest.json").is_file():
                return candidate

        raise FileNotFoundError(f"No ready exchange batch (manifest.json + READY) found beneath {self.inbox_root}")

    def load_manifest(self, batch_dir: Path) -> ExchangeManifest:
        """Parse manifest.json from a confirmed READY batch directory."""
        manifest_file = batch_dir / "manifest.json"
        if not manifest_file.is_file():
            raise FileNotFoundError(f"manifest.json missing in batch: {batch_dir}")

        raw = json.loads(manifest_file.read_text(encoding="utf-8"))
        schema_version = str(raw.get("schema_version") or "1.0.0")
        batch_id = str(raw.get("batch_id") or batch_dir.name)
        production_date = str(raw.get("production_date") or batch_dir.parent.name)
        created_at = str(raw.get("created_at") or "")

        products: list[ExchangeProduct] = []
        for p in raw.get("products") or []:
            brand = str(p.get("brand") or "").strip()
            model = str(p.get("model") or "").strip()
            variant = p.get("variant")
            canonical_key = str(p.get("canonical_product_key") or "")
            if not canonical_key and brand and model:
                canonical_key = compute_canonical_product_key(brand, model, variant)
            pkey = str(p.get("product_key") or "")
            if not pkey and canonical_key:
                pkey = compute_product_key(canonical_key)

            images: list[ExchangeImage] = []
            for img in p.get("images") or []:
                images.append(
                    ExchangeImage(
                        asset_id=str(img.get("asset_id") or ""),
                        relative_path=str(img.get("relative_path") or img.get("local_path") or ""),
                        original_url=img.get("original_url"),
                        match_score=float(img.get("match_score", 1.0)),
                        width=img.get("width"),
                        height=img.get("height"),
                        format=img.get("format"),
                    )
                )

            products.append(
                ExchangeProduct(
                    priority=int(p.get("priority", len(products) + 1)),
                    canonical_product_key=canonical_key,
                    product_key=pkey,
                    name=str(p.get("name") or f"{brand} {model}"),
                    brand=brand,
                    model=model,
                    variant=variant,
                    category=str(p.get("category") or ""),
                    price_display=str(p.get("price_display") or ""),
                    price_min=p.get("price_min"),
                    price_max=p.get("price_max"),
                    currency=str(p.get("currency") or "VND"),
                    hot_reason=str(p.get("hot_reason") or ""),
                    key_features=str(p.get("key_features") or ""),
                    keywords=list(p.get("keywords") or []),
                    images=images,
                    source_product_id=str(p.get("source_product_id") or p.get("id") or ""),
                    source_url=p.get("source_url") or p.get("pdp_url"),
                    selection_reason=p.get("selection_reason"),
                )
            )

        return ExchangeManifest(
            schema_version=schema_version,
            batch_id=batch_id,
            production_date=production_date,
            created_at=created_at,
            products=products,
        )

    def validate_admission(
        self, product: ExchangeProduct, batch_dir: Path
    ) -> tuple[bool, str | None, list[dict[str, Any]]]:
        """Verify admission rules: unambiguous variant and at least 2 valid readable images."""
        if not product.name or not product.name.strip():
            return False, "missing product name", []
        if _URL_LIKE_NAME.match(product.name.strip()):
            return False, "product name is a URL or marketplace slug", []
        
        # Check for ranking list pattern in product name
        if _RANKING_LIST_PATTERN.match(product.name.strip()):
            return False, "product name is a ranking article/listicle, not a single product", []
        
        normalized_name = f" {_identity_words(product.name)} "
        brand = _identity_words(product.brand)
        if not brand or f" {brand} " not in normalized_name:
            return False, "product name does not identify brand", []
        if not _identity_words(product.model) or _PRICE_LIKE_MODEL.match(product.model.strip()):
            return False, "product model is missing or looks like a price", []
        
        # Check for promotional noise in model
        if _PROMOTIONAL_NOISE_MODEL.search(product.model.strip()):
            return False, "product model contains promotional or ranking noise (e.g. Sale/Top/Deal/%)", []

        if _AMBIGUOUS_VARIANT.search(product.name):
            return False, "ambiguous product variant", []

        valid_imgs: list[dict[str, Any]] = []
        for img in product.images:
            if img.match_score < 0.5:
                continue
            img_path = (batch_dir / img.relative_path).resolve()
            try:
                img_path.relative_to(batch_dir.resolve())
            except ValueError:
                continue
            if not img_path.is_file() or img_path.is_symlink():
                continue
            try:
                with Image.open(img_path) as im:
                    im.verify()
                valid_imgs.append(
                    {
                        "asset_id": img.asset_id,
                        "relative_path": img.relative_path,
                        "absolute_path": str(img_path),
                        "original_url": img.original_url,
                        "match_score": img.match_score,
                        "width": img.width,
                        "height": img.height,
                    }
                )
            except Exception:  # noqa: BLE001
                continue

        if len(valid_imgs) < 2:
            return False, "fewer than two technically readable candidate images", []

        return True, None, valid_imgs


def publish_daily_run_to_exchange(
    source_run_dir: Path,
    inbox_root: Path = DEFAULT_EXCHANGE_INBOX,
    batch_id: str | None = None,
    master_catalog_conn: Any | None = None,
    cooldown_days: int = 30,
    max_products: int = 10,
) -> Path:
    """Atomically publish a Product-Intelligence run to the independent exchange inbox with gatekeeper checks.

    1. Validates each product against admission rules and master catalog cooldown.
    2. Copies products and reference images into an isolated exchange directory.
    3. Generates canonical product keys and versioned manifest.json.
    4. Writes the READY sentinel file ONLY after all files are completely written.
    
    Args:
        source_run_dir: Product-Intelligence daily run directory with products.json
        inbox_root: Exchange inbox root directory
        batch_id: Optional batch ID override
        master_catalog_conn: SQLite connection for deduplication tracking
        cooldown_days: Days to block recently produced products (default: 30)
        max_products: Maximum products to include in batch (default: 10)
    
    Returns:
        Path to published batch directory with READY marker
    """
    source_run_dir = Path(source_run_dir)
    products_file = source_run_dir / "products.json"
    if not products_file.is_file():
        raise FileNotFoundError(f"Source products.json not found in {source_run_dir}")

    raw = json.loads(products_file.read_text(encoding="utf-8"))
    production_date = str(raw.get("date") or source_run_dir.name)
    now = datetime.now(timezone.utc)
    effective_batch_id = batch_id or f"run_{now.strftime('%Y%m%d_%H%M%S')}"

    inbox_root = Path(inbox_root)
    batch_dir = inbox_root / production_date / effective_batch_id
    temp_dir = inbox_root / production_date / f".tmp_{effective_batch_id}"
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    temp_dir.mkdir(parents=True, exist_ok=True)

    # Initialize master catalog repository if connection provided
    master_repo = None
    if master_catalog_conn is not None:
        from .repository import DailyImportRepository
        master_repo = DailyImportRepository(master_catalog_conn)

    products_out: list[dict[str, Any]] = []
    raw_products = raw.get("products") or []
    admitted_count = 0

    for idx, p in enumerate(raw_products, start=1):
        if admitted_count >= max_products:
            break  # Enforce daily limit
        brand = str(p.get("brand") or "").strip()
        model = str(p.get("model") or "").strip()
        variant = p.get("variant")
        name = str(p.get("name") or f"{brand} {model}").strip()

        # Handle canonical key
        try:
            canonical_key = compute_canonical_product_key(brand, model, variant)
            pkey = compute_product_key(canonical_key)
        except Exception:  # noqa: BLE001
            canonical_key = f"unknown:{idx}"
            pkey = f"invalid_{idx}"

        # Gatekeeper checks if master catalog enabled
        if master_repo is not None:
            # Record as scouted
            master_repo.upsert_scouted_product(
                canonical_product_key=canonical_key,
                product_key=pkey,
                brand=brand,
                model=model,
                variant=variant or "",
                source_url=p.get("pdp_url"),
                raw_metadata=p,
            )

            # Check cooldown
            is_available, rejection_reason = master_repo.check_cooldown(canonical_key, cooldown_days)
            if not is_available:
                master_repo.mark_rejected(canonical_key, rejection_reason or "COOLDOWN")
                continue  # Skip this product

            # Basic admission validation
            if not name or not brand or not model:
                master_repo.mark_rejected(canonical_key, "MISSING_REQUIRED_FIELDS")
                continue

            if _AMBIGUOUS_VARIANT.search(name):
                master_repo.mark_rejected(canonical_key, "AMBIGUOUS_VARIANT")
                continue

            if _URL_LIKE_NAME.match(name):
                master_repo.mark_rejected(canonical_key, "URL_LIKE_NAME")
                continue

            if _PRICE_LIKE_MODEL.match(model):
                master_repo.mark_rejected(canonical_key, "PRICE_LIKE_MODEL")
                continue

            # Check for promotional noise in model
            if _PROMOTIONAL_NOISE_MODEL.search(model):
                master_repo.mark_rejected(canonical_key, "PROMOTIONAL_NOISE_MODEL")
                continue

            # Check for ranking list pattern in name
            if _RANKING_LIST_PATTERN.match(name):
                master_repo.mark_rejected(canonical_key, "RANKING_LIST_TITLE")
                continue

            # Verify at least 2 images exist
            valid_img_count = 0
            for img in p.get("images") or []:
                src_path = Path(str(img.get("absolute_path") or source_run_dir / img.get("local_path", "")))
                if src_path.is_file():
                    valid_img_count += 1
                    if valid_img_count >= 2:
                        break

            if valid_img_count < 2:
                master_repo.mark_rejected(canonical_key, "INSUFFICIENT_IMAGES")
                continue

            # Mark as admitted
            master_repo.mark_admitted(canonical_key)

        # Copy images into products/<canonical_key>/images/
        clean_key_folder = canonical_key.replace(":", "_")
        target_img_dir = temp_dir / "products" / clean_key_folder / "images"
        target_img_dir.mkdir(parents=True, exist_ok=True)

        images_out: list[dict[str, Any]] = []
        for img_idx, img in enumerate(p.get("images") or [], start=1):
            src_img_path = Path(str(img.get("absolute_path") or source_run_dir / img.get("local_path", "")))
            rel_dest = Path("products") / clean_key_folder / "images" / f"image_{img_idx}{src_img_path.suffix or '.jpg'}"
            dest_img_path = temp_dir / rel_dest

            if src_img_path.is_file():
                shutil.copy2(src_img_path, dest_img_path)

            images_out.append(
                {
                    "asset_id": img.get("asset_id") or f"asset_{pkey[:8]}_{img_idx}",
                    "relative_path": str(rel_dest).replace("\\", "/"),
                    "original_url": img.get("original_url"),
                    "match_score": float(img.get("match_score", 1.0)),
                    "width": img.get("width"),
                    "height": img.get("height"),
                    "format": img.get("format") or src_img_path.suffix.lstrip("."),
                }
            )

        products_out.append(
            {
                "priority": admitted_count + 1,  # Use admitted count for priority
                "canonical_product_key": canonical_key,
                "product_key": pkey,
                "name": name,
                "brand": brand,
                "model": model,
                "variant": variant,
                "category": p.get("category", ""),
                "price_display": p.get("price_display", ""),
                "price_min": p.get("price_min"),
                "price_max": p.get("price_max"),
                "currency": p.get("currency", "VND"),
                "hot_reason": p.get("hot_reason", ""),
                "key_features": p.get("key_features", ""),
                "keywords": p.get("keywords") or [],
                "images": images_out,
                "source_product_id": str(p.get("id") or f"prod_{idx:02d}"),
                "source_url": p.get("pdp_url"),
                "selection_reason": p.get("hot_reason"),
            }
        )
        admitted_count += 1

    manifest_payload = {
        "schema_version": "1.0.0",
        "batch_id": effective_batch_id,
        "production_date": production_date,
        "created_at": now.isoformat(),
        "products": products_out,
    }

    (temp_dir / "manifest.json").write_text(json.dumps(manifest_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    # Atomic rename to final batch directory
    if batch_dir.exists():
        shutil.rmtree(batch_dir)
    temp_dir.rename(batch_dir)

    # Write READY file LAST
    (batch_dir / "READY").write_text(f"READY at {now.isoformat()}\n", encoding="utf-8")
    return batch_dir
