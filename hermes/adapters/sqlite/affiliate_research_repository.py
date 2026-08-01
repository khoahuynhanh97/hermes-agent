from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from typing import Mapping, Sequence

from hermes.db import Database, utc_now
from hermes.domain.affiliate_research import (
    AffiliateProduct,
    ContentIdea,
    ContentPackage,
    PackageStatus,
    ProductSnapshot,
    ProjectionResult,
    ReferenceMetadata,
    ResearchBrief,
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
                        image_urls_json = ?, visual_signals_json = ?, source_type = ?, source_url = ?,
                        authorization_scope = ?, rights_status = ?, content_hash = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    self._product_current_values(product) + (product.updated_at, product_id),
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
                    (
                        product.id,
                        product.owner_user_id,
                        product.platform,
                        product.external_product_id,
                        *self._product_current_values(product),
                        product.created_at,
                        product.updated_at,
                    ),
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

    def record_run_product(
        self,
        run_id: str,
        product_id: str,
        *,
        warnings: Sequence[str] = (),
    ) -> None:
        with self._database.transaction(immediate=True) as connection:
            run = connection.execute(
                "SELECT owner_user_id FROM affiliate_research_runs WHERE id = ?",
                (run_id,),
            ).fetchone()
            if run is None:
                raise LookupError(f"affiliate run not found: {run_id}")
            self._require_owned_product(connection, product_id, run["owner_user_id"])
            connection.execute(
                """
                INSERT INTO affiliate_run_products(
                    run_id, product_id, observation_status, warnings_json, observed_at
                ) VALUES (?, ?, 'imported', ?, ?)
                ON CONFLICT(run_id, product_id) DO UPDATE SET
                    warnings_json = excluded.warnings_json,
                    observed_at = excluded.observed_at
                """,
                (run_id, product_id, json.dumps(tuple(warnings)), utc_now()),
            )

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
                    SELECT
                        product.*,
                        observation.score AS run_score,
                        observation.score_reason AS run_score_reason,
                        observation.score_confidence AS run_score_confidence
                    FROM affiliate_products AS product
                    JOIN affiliate_run_products AS observation
                      ON observation.product_id = product.id
                    WHERE product.owner_user_id = ? AND observation.run_id = ?
                    ORDER BY observation.score DESC, product.updated_at DESC, product.id
                    """,
                    (owner_user_id, run_id),
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

    def save_run_score(
        self,
        run_id: str,
        product_id: str,
        score: ScoreBreakdown,
        eligibility_status: str,
        *,
        rank: int | None = None,
        shortlisted: bool = False,
    ) -> None:
        now = utc_now()
        with self._database.transaction(immediate=True) as connection:
            run = connection.execute(
                "SELECT owner_user_id FROM affiliate_research_runs WHERE id = ?",
                (run_id,),
            ).fetchone()
            if run is None:
                raise LookupError(f"affiliate run not found: {run_id}")
            self._require_owned_product(connection, product_id, run["owner_user_id"])
            self._validate_score_evidence(
                score, run["owner_user_id"], product_id
            )
            score_json = json.dumps(
                {
                    "components": score.components,
                    "growth_rate": score.growth_rate,
                    "evidence_ids": score.evidence_ids,
                    "snapshot_timestamps": score.snapshot_timestamps,
                },
                sort_keys=True,
            )
            cursor = connection.execute(
                """
                UPDATE affiliate_run_products SET
                    eligibility_status = ?, score = ?, score_json = ?,
                    score_reason = ?, score_confidence = ?, rank = ?,
                    shortlisted = ?, evidence_ids_json = ?,
                    snapshot_timestamps_json = ?, observed_at = ?
                WHERE run_id = ? AND product_id = ?
                """,
                (
                    eligibility_status,
                    score.total,
                    score_json,
                    score.reason,
                    score.confidence,
                    rank,
                    int(shortlisted),
                    json.dumps(score.evidence_ids),
                    json.dumps(score.snapshot_timestamps),
                    now,
                    run_id,
                    product_id,
                ),
            )
            if cursor.rowcount != 1:
                raise LookupError(
                    f"affiliate run product not found: {run_id}/{product_id}"
                )

    def save_reference(self, reference: ReferenceMetadata) -> ReferenceMetadata:
        with self._database.transaction() as connection:
            self._require_owned_product(
                connection, reference.product_id, reference.owner_user_id
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO affiliate_references(
                    id, owner_user_id, product_id, platform, source_url, title, author_name,
                    author_url, thumbnail_url, caption, embed_html, authorization_scope,
                    rights_status, media_local_path, collected_at, source_type, content_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                tuple(asdict(reference).values()),
            )
            row = connection.execute(
                "SELECT * FROM affiliate_references WHERE id = ? AND owner_user_id = ?",
                (reference.id, reference.owner_user_id),
            ).fetchone()
            if row is None:
                row = connection.execute(
                    """
                    SELECT * FROM affiliate_references
                    WHERE owner_user_id = ? AND source_url = ?
                    """,
                    (reference.owner_user_id, reference.source_url),
                ).fetchone()
            if row is None:
                raise ValueError(f"affiliate reference id belongs to another owner: {reference.id}")
        return self._reference_from_row(row)

    def save_brief(self, brief: ResearchBrief) -> ResearchBrief:
        with self._database.transaction(immediate=True) as connection:
            self._require_owned_product(connection, brief.product_id, brief.owner_user_id)
            self._require_owned_run(connection, brief.run_id, brief.owner_user_id)
            connection.execute(
                """
                INSERT OR IGNORE INTO affiliate_research_briefs(
                    id, owner_user_id, product_id, run_id, revision,
                    verified_specs_json, strengths_json, limitations_json,
                    unverified_claims_json, reference_patterns_json,
                    reference_pattern_provenance_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    brief.id,
                    brief.owner_user_id,
                    brief.product_id,
                    brief.run_id,
                    brief.revision,
                    json.dumps(brief.verified_specs),
                    json.dumps(brief.strengths),
                    json.dumps(brief.limitations),
                    json.dumps(brief.unverified_claims),
                    json.dumps(brief.reference_patterns),
                    json.dumps(brief.reference_pattern_provenance),
                    brief.created_at,
                ),
            )
            row = connection.execute(
                "SELECT * FROM affiliate_research_briefs WHERE id = ?",
                (brief.id,),
            ).fetchone()
        return self._brief_from_row(row)

    def save_ideas(
        self, product_id: str, run_id: str, ideas: Sequence[ContentIdea]
    ) -> list[ContentIdea]:
        if any(idea.product_id != product_id or idea.run_id != run_id for idea in ideas):
            raise ValueError("content ideas must match the supplied product and run")
        with self._database.transaction(immediate=True) as connection:
            for idea in ideas:
                self._require_owned_product(connection, idea.product_id, idea.owner_user_id)
                self._require_owned_run(connection, idea.run_id, idea.owner_user_id)
                connection.execute(
                    """
                    INSERT OR IGNORE INTO affiliate_run_products(
                        run_id, product_id, observation_status, warnings_json,
                        eligibility_status, score, score_json, score_reason,
                        score_confidence, shortlisted, observed_at
                    )
                    SELECT
                        ?, id, 'imported', '[]', eligibility_status, score,
                        score_json, score_reason, score_confidence,
                        CASE WHEN eligibility_status = 'shortlisted' THEN 1 ELSE 0 END,
                        ?
                    FROM affiliate_products WHERE id = ?
                    """,
                    (idea.run_id, utc_now(), idea.product_id),
                )
                connection.execute(
                    """
                    INSERT OR IGNORE INTO affiliate_content_ideas(
                        id, owner_user_id, product_id, run_id, audience, angle, rationale,
                        created_at, score, rank, selected
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        idea.id,
                        idea.owner_user_id,
                        idea.product_id,
                        idea.run_id,
                        idea.audience,
                        idea.angle,
                        idea.rationale,
                        idea.created_at,
                        idea.score,
                        idea.rank,
                        int(idea.selected),
                    ),
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
            self._require_owned_product(connection, package.product_id, package.owner_user_id)
            self._require_owned_run(connection, package.run_id, package.owner_user_id)
            connection.execute(
                """
                INSERT OR IGNORE INTO affiliate_run_products(
                    run_id, product_id, observation_status, warnings_json,
                    eligibility_status, score, score_json, score_reason,
                    score_confidence, shortlisted, observed_at
                )
                SELECT
                    ?, id, 'imported', '[]', eligibility_status, score,
                    score_json, score_reason, score_confidence,
                    CASE WHEN eligibility_status = 'shortlisted' THEN 1 ELSE 0 END,
                    ?
                FROM affiliate_products WHERE id = ?
                """,
                (package.run_id, utc_now(), package.product_id),
            )
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
                "SELECT * FROM affiliate_content_packages WHERE id = ?", (package.id,)
            ).fetchone()
            saved = self._package_from_row(row)
            if saved != package:
                raise ValueError(f"conflicting package payload for id: {package.id}")
        return saved

    def save_revision(
        self,
        parent_id: str,
        owner_user_id: str,
        revision: ContentPackage,
        feedback: str,
    ) -> ContentPackage:
        with self._database.transaction(immediate=True) as connection:
            parent_row = connection.execute(
                "SELECT * FROM affiliate_content_packages WHERE id = ? AND owner_user_id = ?",
                (parent_id, owner_user_id),
            ).fetchone()
            if parent_row is None:
                raise LookupError(f"affiliate package not found: {parent_id}")
            existing_row = connection.execute(
                "SELECT * FROM affiliate_content_packages WHERE id = ? AND owner_user_id = ?",
                (revision.id, owner_user_id),
            ).fetchone()
            if existing_row is not None:
                return self._package_from_row(existing_row)
            parent = self._package_from_row(parent_row)
            if parent.status not in {
                PackageStatus.PENDING_REVIEW,
                PackageStatus.REVISION_REQUESTED,
            }:
                raise ValueError(
                    f"cannot revise package in {parent.status.value} status"
                )
            self._require_owned_product(
                connection, revision.product_id, revision.owner_user_id
            )
            self._require_owned_run(connection, revision.run_id, revision.owner_user_id)
            connection.execute(
                """
                INSERT INTO affiliate_content_packages(
                    id, owner_user_id, product_id, run_id, revision, status, audience, angle,
                    angle_reason, hook, script, duration_seconds, storyboard_json, ai_prompts_json,
                    voiceover_plan, text_overlays_json, claims_json, warnings_json, asset_rights_json,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                self._package_values(revision),
            )
            now = utc_now()
            if parent.status is PackageStatus.PENDING_REVIEW:
                connection.execute(
                    """
                    UPDATE affiliate_content_packages
                    SET status = 'revision_requested', updated_at = ?
                    WHERE id = ?
                    """,
                    (now, parent_id),
                )
                connection.execute(
                    """
                    INSERT INTO affiliate_approval_events(
                        package_id, owner_user_id, action, reason, created_at
                    ) VALUES (?, ?, 'revise', ?, ?)
                    """,
                    (parent_id, owner_user_id, feedback, now),
                )
            saved_row = connection.execute(
                "SELECT * FROM affiliate_content_packages WHERE id = ?",
                (revision.id,),
            ).fetchone()
        return self._package_from_row(saved_row)

    def get_package(self, package_id: str, owner_user_id: str) -> ContentPackage | None:
        with self._database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM affiliate_content_packages WHERE id = ? AND owner_user_id = ?",
                (package_id, owner_user_id),
            ).fetchone()
        return self._package_from_row(row) if row else None

    def list_packages(
        self, owner_user_id: str, run_id: str | None = None
    ) -> list[ContentPackage]:
        with self._database.connect() as connection:
            if run_id is None:
                rows = connection.execute(
                    """
                    SELECT * FROM affiliate_content_packages
                    WHERE owner_user_id = ?
                    ORDER BY created_at DESC, revision DESC, id DESC
                    """,
                    (owner_user_id,),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT * FROM affiliate_content_packages
                    WHERE owner_user_id = ? AND run_id = ?
                    ORDER BY created_at DESC, revision DESC, id DESC
                    """,
                    (owner_user_id, run_id),
                ).fetchall()
        return [self._package_from_row(row) for row in rows]

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

    def finish_run(self, run_id: str, counters: dict[str, object]) -> dict:
        return self.complete_run(run_id, counters, ())

    def complete_run(
        self,
        run_id: str,
        counters: dict[str, object],
        projections: Sequence[str],
        *,
        projection_items: Mapping[str, Sequence[str]] | None = None,
    ) -> dict:
        now = utc_now()
        item_map = projection_items or {}
        unknown = set(item_map) - set(projections)
        if unknown:
            raise ValueError(
                f"projection items require an outbox projection: {sorted(unknown)}"
            )
        with self._database.transaction(immediate=True) as connection:
            run = connection.execute(
                "SELECT owner_user_id FROM affiliate_research_runs WHERE id = ?",
                (run_id,),
            ).fetchone()
            if run is None:
                raise LookupError(f"affiliate run not found: {run_id}")
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
            for projection in projections:
                if not projection.strip():
                    raise ValueError("projection name is required")
                connection.execute(
                    """
                    INSERT OR IGNORE INTO affiliate_projection_outbox(
                        run_id, projection, owner_user_id, status, attempts,
                        detail, created_at, updated_at
                    ) VALUES (?, ?, ?, 'pending', 0, '', ?, ?)
                    """,
                    (run_id, projection, run["owner_user_id"], now, now),
                )
                for item_id in item_map.get(projection, ()):
                    if not item_id.strip():
                        raise ValueError("projection item id is required")
                    connection.execute(
                        """
                        INSERT OR IGNORE INTO affiliate_projection_items(
                            run_id, projection, item_id, status, attempts,
                            external_message_id, created_at, updated_at
                        ) VALUES (?, ?, ?, 'pending', 0, '', ?, ?)
                        """,
                        (run_id, projection, item_id, now, now),
                    )
            row = connection.execute(
                "SELECT * FROM affiliate_research_runs WHERE id = ?", (run_id,)
            ).fetchone()
        return self._run_from_row(row)

    def pending_projections(self, run_id: str) -> list[dict]:
        with self._database.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM affiliate_projection_outbox
                WHERE run_id = ? AND status = 'pending'
                ORDER BY projection
                """,
                (run_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def pending_projection_items(
        self,
        run_id: str,
        projection: str,
        item_ids: Sequence[str],
    ) -> list[str]:
        if not item_ids:
            return []
        placeholders = ", ".join("?" for _ in item_ids)
        with self._database.connect() as connection:
            delivered = {
                row["item_id"]
                for row in connection.execute(
                    f"""
                    SELECT item_id FROM affiliate_projection_items
                    WHERE run_id = ? AND projection = ?
                      AND item_id IN ({placeholders}) AND status = 'delivered'
                    """,
                    (run_id, projection, *item_ids),
                )
            }
        return [item_id for item_id in item_ids if item_id not in delivered]

    def ensure_projection_item(
        self,
        run_id: str,
        projection: str,
        item_id: str,
    ) -> None:
        now = utc_now()
        with self._database.transaction(immediate=True) as connection:
            outbox = connection.execute(
                """
                SELECT 1 FROM affiliate_projection_outbox
                WHERE run_id = ? AND projection = ?
                """,
                (run_id, projection),
            ).fetchone()
            if outbox is None:
                raise LookupError(
                    f"affiliate projection outbox entry not found: "
                    f"{run_id}/{projection}"
                )
            if projection == "telegram":
                package = connection.execute(
                    """
                    SELECT 1 FROM affiliate_content_packages
                    WHERE id = ? AND run_id = ?
                    """,
                    (item_id, run_id),
                ).fetchone()
                if package is None:
                    raise LookupError(
                        f"affiliate package not found in run: "
                        f"{run_id}/{item_id}"
                    )
            connection.execute(
                """
                INSERT OR IGNORE INTO affiliate_projection_items(
                    run_id, projection, item_id, status, external_message_id,
                    attempts, created_at, updated_at
                ) VALUES (?, ?, ?, 'pending', '', 0, ?, ?)
                """,
                (run_id, projection, item_id, now, now),
            )

    def mark_projection_item_delivered(
        self,
        run_id: str,
        projection: str,
        item_id: str,
        external_message_id: str = "",
    ) -> None:
        now = utc_now()
        with self._database.transaction(immediate=True) as connection:
            cursor = connection.execute(
                """
                UPDATE affiliate_projection_items
                SET status = 'delivered', attempts = attempts + 1,
                    external_message_id = ?, updated_at = ?, delivered_at = ?
                WHERE run_id = ? AND projection = ? AND item_id = ?
                """,
                (
                    str(external_message_id),
                    now,
                    now,
                    run_id,
                    projection,
                    item_id,
                ),
            )
            if cursor.rowcount != 1:
                raise LookupError(
                    "affiliate projection item not found: "
                    f"{run_id}/{projection}/{item_id}"
                )

    def mark_projection_result(
        self,
        run_id: str,
        projection: str,
        result: ProjectionResult,
    ) -> None:
        now = utc_now()
        status = (
            "delivered"
            if result.ok
            else ("pending" if result.retryable else "permanent_failure")
        )
        with self._database.transaction(immediate=True) as connection:
            run = connection.execute(
                "SELECT counters_json FROM affiliate_research_runs WHERE id = ?",
                (run_id,),
            ).fetchone()
            if run is None:
                raise LookupError(f"affiliate run not found: {run_id}")
            cursor = connection.execute(
                """
                UPDATE affiliate_projection_outbox
                SET status = ?, attempts = attempts + 1, detail = ?,
                    updated_at = ?, delivered_at = ?
                WHERE run_id = ? AND projection = ?
                """,
                (
                    status,
                    str(result.detail)[:1000],
                    now,
                    now if result.ok else None,
                    run_id,
                    projection,
                ),
            )
            if cursor.rowcount != 1:
                raise LookupError(
                    f"affiliate projection outbox entry not found: {run_id}/{projection}"
                )
            counters = json.loads(run["counters_json"])
            failures = counters.get("projection_failures")
            if result.ok:
                if isinstance(failures, dict):
                    failures.pop(projection, None)
                    if not failures:
                        counters.pop("projection_failures", None)
            else:
                if not isinstance(failures, dict):
                    failures = {}
                    counters["projection_failures"] = failures
                failures[projection] = {
                    "detail": str(result.detail)[:1000],
                    "retryable": bool(result.retryable),
                }
            connection.execute(
                """
                UPDATE affiliate_research_runs
                SET counters_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (json.dumps(counters, sort_keys=True), now, run_id),
            )

    def record_projection_failure(
        self, run_id: str, projection: str, detail: str, *, retryable: bool
    ) -> dict:
        if not projection.strip():
            raise ValueError("projection name is required")
        with self._database.transaction(immediate=True) as connection:
            row = connection.execute(
                "SELECT * FROM affiliate_research_runs WHERE id = ?", (run_id,)
            ).fetchone()
            if row is None:
                raise LookupError(f"affiliate run not found: {run_id}")
            counters = json.loads(row["counters_json"])
            failures = counters.get("projection_failures")
            if not isinstance(failures, dict):
                failures = {}
                counters["projection_failures"] = failures
            failures[projection] = {"detail": str(detail)[:1000], "retryable": bool(retryable)}
            connection.execute(
                """
                UPDATE affiliate_projection_outbox
                SET status = ?, attempts = attempts + 1, detail = ?, updated_at = ?
                WHERE run_id = ? AND projection = ?
                """,
                (
                    "pending" if retryable else "permanent_failure",
                    str(detail)[:1000],
                    utc_now(),
                    run_id,
                    projection,
                ),
            )
            connection.execute(
                "UPDATE affiliate_research_runs SET counters_json = ?, updated_at = ? WHERE id = ?",
                (json.dumps(counters, sort_keys=True), utc_now(), run_id),
            )
            updated = connection.execute(
                "SELECT * FROM affiliate_research_runs WHERE id = ?", (run_id,)
            ).fetchone()
        return self._run_from_row(updated)

    def clear_projection_failure(self, run_id: str, projection: str) -> dict:
        with self._database.transaction(immediate=True) as connection:
            row = connection.execute(
                "SELECT * FROM affiliate_research_runs WHERE id = ?", (run_id,)
            ).fetchone()
            if row is None:
                raise LookupError(f"affiliate run not found: {run_id}")
            counters = json.loads(row["counters_json"])
            failures = counters.get("projection_failures")
            if isinstance(failures, dict):
                failures.pop(projection, None)
                if not failures:
                    counters.pop("projection_failures", None)
            connection.execute(
                """
                UPDATE affiliate_projection_outbox
                SET status = 'delivered', attempts = attempts + 1, detail = '',
                    updated_at = ?, delivered_at = ?
                WHERE run_id = ? AND projection = ?
                """,
                (utc_now(), utc_now(), run_id, projection),
            )
            connection.execute(
                "UPDATE affiliate_research_runs SET counters_json = ?, updated_at = ? WHERE id = ?",
                (json.dumps(counters, sort_keys=True), utc_now(), run_id),
            )
            updated = connection.execute(
                "SELECT * FROM affiliate_research_runs WHERE id = ?", (run_id,)
            ).fetchone()
        return self._run_from_row(updated)

    def projection_rows(self, owner_user_id: str, run_id: str) -> dict[str, list[dict]]:
        with self._database.connect() as connection:
            products = self._projection_query(
                connection,
                """
                SELECT
                    product.*,
                    observation.warnings_json AS stale_warnings_json,
                    observation.eligibility_status AS run_eligibility_status,
                    observation.score AS run_score,
                    observation.score_json AS run_score_payload_json,
                    observation.score_reason AS run_score_reason,
                    observation.score_confidence AS run_score_confidence,
                    observation.rank AS run_rank,
                    observation.shortlisted AS run_shortlisted,
                    observation.evidence_ids_json AS run_evidence_ids_json,
                    observation.snapshot_timestamps_json
                        AS run_snapshot_timestamps_json
                FROM affiliate_products AS product
                JOIN affiliate_run_products AS observation
                  ON observation.product_id = product.id
                WHERE product.owner_user_id = ? AND observation.run_id = ?
                ORDER BY observation.score DESC, product.id
                """,
                (owner_user_id, run_id),
            )
            for product in products:
                product["eligibility_status"] = product.pop(
                    "run_eligibility_status"
                )
                product["score"] = product.pop("run_score")
                product["score_json"] = product.pop("run_score_payload")
                product["score_reason"] = product.pop("run_score_reason")
                product["score_confidence"] = product.pop(
                    "run_score_confidence"
                )
                product["rank"] = product.pop("run_rank")
                product["shortlisted"] = product.pop("run_shortlisted")
                product["evidence_ids"] = product.pop("run_evidence_ids")
                product["snapshot_timestamps"] = product.pop(
                    "run_snapshot_timestamps"
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
                JOIN affiliate_run_products AS observation
                  ON observation.product_id = reference.product_id
                WHERE reference.owner_user_id = ? AND observation.run_id = ?
                ORDER BY reference.collected_at, reference.id
                """,
                (owner_user_id, run_id),
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
    def _product_current_values(product: AffiliateProduct) -> tuple:
        return (
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
            product.source_type,
            product.source_url,
            product.authorization_scope,
            product.rights_status,
            product.content_hash,
        )

    @staticmethod
    def _require_owned_product(
        connection: sqlite3.Connection, product_id: str, owner_user_id: str
    ) -> None:
        row = connection.execute(
            "SELECT owner_user_id FROM affiliate_products WHERE id = ?", (product_id,)
        ).fetchone()
        if row is None:
            raise LookupError(f"affiliate product not found: {product_id}")
        if row["owner_user_id"] != owner_user_id:
            raise LookupError(f"affiliate product does not belong to owner: {product_id}")

    @staticmethod
    def _require_owned_run(
        connection: sqlite3.Connection, run_id: str, owner_user_id: str
    ) -> None:
        row = connection.execute(
            "SELECT owner_user_id FROM affiliate_research_runs WHERE id = ?", (run_id,)
        ).fetchone()
        if row is None:
            raise LookupError(f"affiliate run not found: {run_id}")
        if row["owner_user_id"] != owner_user_id:
            raise LookupError(f"affiliate run does not belong to owner: {run_id}")

    @staticmethod
    def _validate_score_evidence(
        score: ScoreBreakdown, owner_user_id: str, product_id: str
    ) -> None:
        source_prefix = f"source:{owner_user_id}:{product_id}:"
        snapshot_prefix = f"snapshot:{owner_user_id}:{product_id}:"
        invalid = [
            evidence_id
            for evidence_id in score.evidence_ids
            if not evidence_id.startswith((source_prefix, snapshot_prefix))
        ]
        if invalid:
            raise ValueError(
                f"score evidence must be owner-scoped: {invalid[0]}"
            )
        if not any(
            evidence_id.startswith(source_prefix)
            for evidence_id in score.evidence_ids
        ):
            raise ValueError("score requires canonical source evidence")
        if not any(
            evidence_id.startswith(snapshot_prefix)
            for evidence_id in score.evidence_ids
        ):
            raise ValueError("score requires canonical snapshot evidence")
        if not score.snapshot_timestamps:
            raise ValueError("score requires snapshot timestamps")

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
        keys = set(row.keys())
        score = row["run_score"] if "run_score" in keys else row["score"]
        score_reason = (
            row["run_score_reason"]
            if "run_score_reason" in keys
            else row["score_reason"]
        )
        score_confidence = (
            row["run_score_confidence"]
            if "run_score_confidence" in keys
            else row["score_confidence"]
        )
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
            score=score, score_reason=score_reason,
            score_confidence=score_confidence,
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
        value = dict(row)
        value["selected"] = bool(value["selected"])
        return ContentIdea(**value)

    @staticmethod
    def _brief_from_row(row: sqlite3.Row) -> ResearchBrief:
        keys = set(row.keys())
        return ResearchBrief(
            id=row["id"],
            owner_user_id=row["owner_user_id"],
            product_id=row["product_id"],
            run_id=row["run_id"],
            revision=row["revision"],
            verified_specs=tuple(json.loads(row["verified_specs_json"])),
            strengths=tuple(json.loads(row["strengths_json"])),
            limitations=tuple(json.loads(row["limitations_json"])),
            unverified_claims=tuple(json.loads(row["unverified_claims_json"])),
            reference_patterns=tuple(json.loads(row["reference_patterns_json"])),
            created_at=row["created_at"],
            reference_pattern_provenance=tuple(
                json.loads(row["reference_pattern_provenance_json"])
                if "reference_pattern_provenance_json" in keys
                else ()
            ),
        )

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
