from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from typing import Sequence

from hermes.db import Database, utc_now
from hermes.domain.affiliate_research import (
    AffiliateProduct,
    ContentIdea,
    ContentPackage,
    PackageStatus,
    ProductSnapshot,
    ReferenceMetadata,
    ScoreBreakdown,
)


class SQLiteAffiliateResearchRepository:
    """Canonical SQLite persistence for affiliate research state."""

    _PACKAGE_ACTIONS = {
        "approve": PackageStatus.APPROVED,
        "revise": PackageStatus.REVISION_REQUESTED,
        "reject": PackageStatus.REJECTED,
    }

    def __init__(self, database: Database):
        self._database = database
        self._database.initialize()

    def upsert_product(self, product: AffiliateProduct) -> AffiliateProduct:
        with self._database.transaction(immediate=True) as connection:
            existing = connection.execute(
                """
                SELECT id FROM affiliate_products
                WHERE owner_user_id = ? AND platform = ? AND external_product_id = ?
                """,
                (product.owner_user_id, product.platform, product.external_product_id),
            ).fetchone()
            product_id = existing["id"] if existing else product.id
            if existing:
                connection.execute(
                    """
                    UPDATE affiliate_products SET
                        name = ?, category = ?, price_vnd = ?, sold_count = ?, rating = ?,
                        review_count = ?, commission_rate = ?, shop_name = ?, product_url = ?,
                        image_urls_json = ?, visual_signals_json = ?, content_hash = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    self._product_values(product, include_identity=False) + (product_id,),
                )
            else:
                connection.execute(
                    """
                    INSERT INTO affiliate_products(
                        id, owner_user_id, platform, external_product_id, name, category, price_vnd,
                        sold_count, rating, review_count, commission_rate, shop_name, product_url,
                        image_urls_json, visual_signals_json, source_type, source_url,
                        authorization_scope, rights_status, content_hash, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    self._product_values(product, include_identity=True),
                )
            row = connection.execute(
                "SELECT * FROM affiliate_products WHERE id = ?", (product_id,)
            ).fetchone()
        return self._product_from_row(row)

    def record_snapshot(
        self, product_id: str, snapshot_date: str, product: AffiliateProduct
    ) -> ProductSnapshot:
        with self._database.transaction() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO affiliate_product_snapshots(
                    product_id, snapshot_date, price_vnd, sold_count, rating, review_count,
                    commission_rate, collected_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    product_id,
                    snapshot_date,
                    product.price_vnd,
                    product.sold_count,
                    product.rating,
                    product.review_count,
                    product.commission_rate,
                    utc_now(),
                ),
            )
            row = connection.execute(
                """
                SELECT * FROM affiliate_product_snapshots
                WHERE product_id = ? AND snapshot_date = ?
                """,
                (product_id, snapshot_date),
            ).fetchone()
        return self._snapshot_from_row(row)

    def list_products(self, owner_user_id: str, run_id: str | None = None) -> list[AffiliateProduct]:
        with self._database.connect() as connection:
            if run_id is None:
                rows = connection.execute(
                    """
                    SELECT * FROM affiliate_products WHERE owner_user_id = ?
                    ORDER BY score DESC, updated_at DESC, id
                    """,
                    (owner_user_id,),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT * FROM affiliate_products AS product
                    WHERE owner_user_id = ? AND (
                        EXISTS (
                            SELECT 1 FROM affiliate_content_ideas AS idea
                            WHERE idea.product_id = product.id AND idea.run_id = ?
                        ) OR EXISTS (
                            SELECT 1 FROM affiliate_content_packages AS package
                            WHERE package.product_id = product.id AND package.run_id = ?
                        )
                    )
                    ORDER BY score DESC, updated_at DESC, id
                    """,
                    (owner_user_id, run_id, run_id),
                ).fetchall()
        return [self._product_from_row(row) for row in rows]

    def list_snapshots(self, product_id: str) -> list[ProductSnapshot]:
        with self._database.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM affiliate_product_snapshots
                WHERE product_id = ? ORDER BY snapshot_date, collected_at
                """,
                (product_id,),
            ).fetchall()
        return [self._snapshot_from_row(row) for row in rows]

    def save_score(self, product_id: str, score: ScoreBreakdown, eligibility_status: str) -> None:
        score_json = json.dumps(
            {"components": score.components, "growth_rate": score.growth_rate}, sort_keys=True
        )
        with self._database.transaction() as connection:
            cursor = connection.execute(
                """
                UPDATE affiliate_products SET
                    score = ?, score_json = ?, score_reason = ?, score_confidence = ?,
                    eligibility_status = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    score.total,
                    score_json,
                    score.reason,
                    score.confidence,
                    eligibility_status,
                    utc_now(),
                    product_id,
                ),
            )
            if cursor.rowcount != 1:
                raise LookupError(f"affiliate product not found: {product_id}")

    def save_reference(self, reference: ReferenceMetadata) -> ReferenceMetadata:
        with self._database.transaction() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO affiliate_references(
                    id, owner_user_id, product_id, platform, source_url, title, author_name,
                    author_url, thumbnail_url, caption, embed_html, authorization_scope,
                    rights_status, media_local_path, collected_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                tuple(asdict(reference).values()),
            )
            row = connection.execute(
                "SELECT * FROM affiliate_references WHERE id = ? AND owner_user_id = ?",
                (reference.id, reference.owner_user_id),
            ).fetchone()
            if row is None:
                raise ValueError(f"affiliate reference id belongs to another owner: {reference.id}")
        return self._reference_from_row(row)

    def save_ideas(
        self, product_id: str, run_id: str, ideas: Sequence[ContentIdea]
    ) -> list[ContentIdea]:
        if any(idea.product_id != product_id or idea.run_id != run_id for idea in ideas):
            raise ValueError("content ideas must match the supplied product and run")
        with self._database.transaction() as connection:
            for idea in ideas:
                connection.execute(
                    """
                    INSERT OR IGNORE INTO affiliate_content_ideas(
                        id, owner_user_id, product_id, run_id, audience, angle, rationale, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    tuple(asdict(idea).values()),
                )
            rows = connection.execute(
                """
                SELECT * FROM affiliate_content_ideas
                WHERE product_id = ? AND run_id = ? AND id IN ({})
                ORDER BY created_at, id
                """.format(", ".join("?" for _ in ideas)),
                (product_id, run_id, *(idea.id for idea in ideas)),
            ).fetchall() if ideas else []
        return [self._idea_from_row(row) for row in rows]

    def save_package(self, package: ContentPackage) -> ContentPackage:
        with self._database.transaction(immediate=True) as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO affiliate_content_packages(
                    id, owner_user_id, product_id, run_id, revision, status, audience, angle,
                    angle_reason, hook, script, duration_seconds, storyboard_json, ai_prompts_json,
                    voiceover_plan, text_overlays_json, claims_json, warnings_json, asset_rights_json,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                self._package_values(package),
            )
            row = connection.execute(
                "SELECT * FROM affiliate_content_packages WHERE id = ? AND owner_user_id = ?",
                (package.id, package.owner_user_id),
            ).fetchone()
            if row is None:
                raise ValueError(f"affiliate package id belongs to another owner: {package.id}")
        return self._package_from_row(row)

    def get_package(self, package_id: str, owner_user_id: str) -> ContentPackage | None:
        with self._database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM affiliate_content_packages WHERE id = ? AND owner_user_id = ?",
                (package_id, owner_user_id),
            ).fetchone()
        return self._package_from_row(row) if row else None

    def transition_package(
        self, package_id: str, owner_user_id: str, action: str, reason: str
    ) -> ContentPackage:
        target_status = self._PACKAGE_ACTIONS.get(action)
        if target_status is None:
            raise ValueError(f"unsupported package action: {action}")
        with self._database.transaction(immediate=True) as connection:
            row = connection.execute(
                "SELECT * FROM affiliate_content_packages WHERE id = ? AND owner_user_id = ?",
                (package_id, owner_user_id),
            ).fetchone()
            if row is None:
                raise LookupError(f"affiliate package not found: {package_id}")
            package = self._package_from_row(row)
            if package.status is target_status:
                return package
            if package.status is not PackageStatus.PENDING_REVIEW:
                raise ValueError(
                    f"cannot {action} package in {package.status.value} status"
                )
            updated_at = utc_now()
            connection.execute(
                "UPDATE affiliate_content_packages SET status = ?, updated_at = ? WHERE id = ?",
                (target_status.value, updated_at, package_id),
            )
            connection.execute(
                """
                INSERT INTO affiliate_approval_events(package_id, owner_user_id, action, reason, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (package_id, owner_user_id, action, reason, updated_at),
            )
            row = connection.execute(
                "SELECT * FROM affiliate_content_packages WHERE id = ?", (package_id,)
            ).fetchone()
        return self._package_from_row(row)

    def create_run(self, run_id: str, owner_user_id: str, idempotency_key: str) -> dict:
        now = utc_now()
        with self._database.transaction(immediate=True) as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO affiliate_research_runs(
                    id, owner_user_id, idempotency_key, status, counters_json, created_at, updated_at
                ) VALUES (?, ?, ?, 'running', '{}', ?, ?)
                """,
                (run_id, owner_user_id, idempotency_key, now, now),
            )
            row = connection.execute(
                """
                SELECT * FROM affiliate_research_runs
                WHERE owner_user_id = ? AND idempotency_key = ?
                """,
                (owner_user_id, idempotency_key),
            ).fetchone()
            if row is None:
                raise ValueError(f"affiliate run id belongs to another owner: {run_id}")
        return self._run_from_row(row)

    def finish_run(self, run_id: str, counters: dict[str, int]) -> dict:
        now = utc_now()
        with self._database.transaction() as connection:
            cursor = connection.execute(
                """
                UPDATE affiliate_research_runs
                SET status = 'completed', counters_json = ?, updated_at = ?, finished_at = ?
                WHERE id = ?
                """,
                (json.dumps(counters, sort_keys=True), now, now, run_id),
            )
            if cursor.rowcount != 1:
                raise LookupError(f"affiliate run not found: {run_id}")
            row = connection.execute(
                "SELECT * FROM affiliate_research_runs WHERE id = ?", (run_id,)
            ).fetchone()
        return self._run_from_row(row)

    def projection_rows(self, owner_user_id: str, run_id: str) -> dict[str, list[dict]]:
        with self._database.connect() as connection:
            products = self._projection_query(
                connection,
                """
                SELECT DISTINCT product.* FROM affiliate_products AS product
                LEFT JOIN affiliate_content_ideas AS idea ON idea.product_id = product.id
                LEFT JOIN affiliate_content_packages AS package ON package.product_id = product.id
                WHERE product.owner_user_id = ? AND (idea.run_id = ? OR package.run_id = ?)
                ORDER BY product.score DESC, product.id
                """,
                (owner_user_id, run_id, run_id),
            )
            ideas = self._projection_query(
                connection,
                "SELECT * FROM affiliate_content_ideas WHERE owner_user_id = ? AND run_id = ? ORDER BY created_at, id",
                (owner_user_id, run_id),
            )
            packages = self._projection_query(
                connection,
                "SELECT * FROM affiliate_content_packages WHERE owner_user_id = ? AND run_id = ? ORDER BY revision, id",
                (owner_user_id, run_id),
            )
            references = self._projection_query(
                connection,
                """
                SELECT DISTINCT reference.* FROM affiliate_references AS reference
                WHERE reference.owner_user_id = ? AND (
                    EXISTS (
                        SELECT 1 FROM affiliate_content_ideas AS idea
                        WHERE idea.product_id = reference.product_id AND idea.run_id = ?
                    ) OR EXISTS (
                        SELECT 1 FROM affiliate_content_packages AS package
                        WHERE package.product_id = reference.product_id AND package.run_id = ?
                    )
                )
                ORDER BY reference.collected_at, reference.id
                """,
                (owner_user_id, run_id, run_id),
            )
            events = self._projection_query(
                connection,
                """
                SELECT event.* FROM affiliate_approval_events AS event
                JOIN affiliate_content_packages AS package ON package.id = event.package_id
                WHERE event.owner_user_id = ? AND package.run_id = ?
                ORDER BY event.created_at, event.id
                """,
                (owner_user_id, run_id),
            )
            runs = self._projection_query(
                connection,
                "SELECT * FROM affiliate_research_runs WHERE id = ? AND owner_user_id = ?",
                (run_id, owner_user_id),
            )
        return {
            "products": products,
            "references": references,
            "ideas": ideas,
            "packages": packages,
            "approval_events": events,
            "runs": runs,
        }

    @staticmethod
    def _product_values(product: AffiliateProduct, *, include_identity: bool) -> tuple:
        mutable = (
            product.name,
            product.category,
            product.price_vnd,
            product.sold_count,
            product.rating,
            product.review_count,
            product.commission_rate,
            product.shop_name,
            product.product_url,
            json.dumps(product.image_urls),
            json.dumps(product.visual_signals),
            product.content_hash,
            product.updated_at,
        )
        if not include_identity:
            return mutable
        return (
            product.id,
            product.owner_user_id,
            product.platform,
            product.external_product_id,
            *mutable[:11],
            product.source_type,
            product.source_url,
            product.authorization_scope,
            product.rights_status,
            mutable[11],
            product.created_at,
            mutable[12],
        )

    @staticmethod
    def _package_values(package: ContentPackage) -> tuple:
        return (
            package.id,
            package.owner_user_id,
            package.product_id,
            package.run_id,
            package.revision,
            package.status.value,
            package.audience,
            package.angle,
            package.angle_reason,
            package.hook,
            package.script,
            package.duration_seconds,
            json.dumps(package.storyboard),
            json.dumps(package.ai_prompts),
            package.voiceover_plan,
            json.dumps(package.text_overlays),
            json.dumps(package.claims),
            json.dumps(package.warnings),
            json.dumps(package.asset_rights, sort_keys=True),
            package.created_at,
            package.updated_at,
        )

    @staticmethod
    def _product_from_row(row: sqlite3.Row) -> AffiliateProduct:
        return AffiliateProduct(
            id=row["id"], owner_user_id=row["owner_user_id"], platform=row["platform"],
            external_product_id=row["external_product_id"], name=row["name"],
            category=row["category"], price_vnd=row["price_vnd"], sold_count=row["sold_count"],
            rating=row["rating"], review_count=row["review_count"],
            commission_rate=row["commission_rate"], shop_name=row["shop_name"],
            product_url=row["product_url"], image_urls=tuple(json.loads(row["image_urls_json"])),
            visual_signals=tuple(json.loads(row["visual_signals_json"])),
            source_type=row["source_type"], source_url=row["source_url"],
            authorization_scope=row["authorization_scope"], rights_status=row["rights_status"],
            content_hash=row["content_hash"], created_at=row["created_at"], updated_at=row["updated_at"],
        )

    @staticmethod
    def _snapshot_from_row(row: sqlite3.Row) -> ProductSnapshot:
        return ProductSnapshot(
            product_id=row["product_id"], snapshot_date=row["snapshot_date"],
            price_vnd=row["price_vnd"], sold_count=row["sold_count"], rating=row["rating"],
            review_count=row["review_count"], commission_rate=row["commission_rate"],
            collected_at=row["collected_at"],
        )

    @staticmethod
    def _reference_from_row(row: sqlite3.Row) -> ReferenceMetadata:
        return ReferenceMetadata(**dict(row))

    @staticmethod
    def _idea_from_row(row: sqlite3.Row) -> ContentIdea:
        return ContentIdea(**dict(row))

    @staticmethod
    def _package_from_row(row: sqlite3.Row) -> ContentPackage:
        return ContentPackage(
            id=row["id"], owner_user_id=row["owner_user_id"], product_id=row["product_id"],
            run_id=row["run_id"], revision=row["revision"], status=PackageStatus(row["status"]),
            audience=row["audience"], angle=row["angle"], angle_reason=row["angle_reason"],
            hook=row["hook"], script=row["script"], duration_seconds=row["duration_seconds"],
            storyboard=tuple(json.loads(row["storyboard_json"])),
            ai_prompts=tuple(json.loads(row["ai_prompts_json"])),
            voiceover_plan=row["voiceover_plan"],
            text_overlays=tuple(json.loads(row["text_overlays_json"])),
            claims=tuple(json.loads(row["claims_json"])), warnings=tuple(json.loads(row["warnings_json"])),
            asset_rights=json.loads(row["asset_rights_json"]), created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _run_from_row(row: sqlite3.Row) -> dict:
        value = dict(row)
        value["counters"] = json.loads(value.pop("counters_json"))
        return value

    @staticmethod
    def _projection_query(
        connection: sqlite3.Connection, query: str, parameters: tuple
    ) -> list[dict]:
        rows = []
        for row in connection.execute(query, parameters):
            value = dict(row)
            for key in tuple(value):
                if key.endswith("_json"):
                    decoded_key = "counters" if key == "counters_json" else key.removesuffix("_json")
                    value[decoded_key] = json.loads(value.pop(key))
            rows.append(value)
        return rows
