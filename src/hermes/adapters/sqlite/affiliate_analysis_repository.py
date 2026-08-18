"""SQLite adapter for ``AffiliateAnalysisRepository``."""

from __future__ import annotations

import json

from hermes.db import Database
from hermes.domain.affiliate_analysis import (
    AffiliateAnalysis,
    TikTokScript,
    VisualPrompts,
)
from hermes.ports.affiliate_analysis_repository import AffiliateAnalysisRepository


def _row_to_analysis(row) -> AffiliateAnalysis:
    return AffiliateAnalysis(
        analysis_id=row["id"],
        owner_user_id=row["owner_user_id"],
        product_id=row["product_id"],
        run_id=row["run_id"],
        usp_list=tuple(json.loads(row["usp_list_json"])),
        pain_points=tuple(json.loads(row["pain_points_json"])),
        target_audience=row["target_audience"],
        tiktok_script=TikTokScript(
            hook=row["hook"],
            body=row["body"],
            cta=row["cta"],
        ),
        visual_prompts=VisualPrompts(
            image_prompt=row["image_prompt"],
            video_prompt=row["video_prompt"],
        ),
        fallback_used=bool(row["fallback_used"]),
        created_at=row["created_at"],
    )


class SQLiteAffiliateAnalysisRepository(AffiliateAnalysisRepository):
    def __init__(self, database: Database):
        self._database = database
        self._database.initialize()

    def save(self, analysis: AffiliateAnalysis) -> AffiliateAnalysis:
        with self._database.transaction(immediate=True) as conn:
            existing = conn.execute(
                """
                SELECT id FROM affiliate_analyses
                WHERE owner_user_id = ? AND product_id = ? AND run_id = ? AND content_hash = ?
                """,
                (
                    analysis.owner_user_id,
                    analysis.product_id,
                    analysis.run_id,
                    _content_hash(analysis),
                ),
            ).fetchone()

            if existing:
                row = conn.execute(
                    "SELECT * FROM affiliate_analyses WHERE id = ?",
                    (existing["id"],),
                ).fetchone()
                return _row_to_analysis(row)

            analysis_id = analysis.analysis_id
            conn.execute(
                """
                INSERT INTO affiliate_analyses (
                    id, owner_user_id, product_id, run_id,
                    usp_list_json, pain_points_json, target_audience,
                    hook, body, cta, image_prompt, video_prompt,
                    fallback_used, content_hash, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    analysis_id,
                    analysis.owner_user_id,
                    analysis.product_id,
                    analysis.run_id,
                    json.dumps(list(analysis.usp_list), ensure_ascii=False),
                    json.dumps(list(analysis.pain_points), ensure_ascii=False),
                    analysis.target_audience,
                    analysis.tiktok_script.hook,
                    analysis.tiktok_script.body,
                    analysis.tiktok_script.cta,
                    analysis.visual_prompts.image_prompt,
                    analysis.visual_prompts.video_prompt,
                    1 if analysis.fallback_used else 0,
                    _content_hash(analysis),
                    analysis.created_at,
                ),
            )
        return analysis

    def find_for_product(
        self, owner_user_id: str, product_id: str
    ) -> list[AffiliateAnalysis]:
        with self._database.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM affiliate_analyses
                WHERE owner_user_id = ? AND product_id = ?
                ORDER BY created_at ASC
                """,
                (owner_user_id, product_id),
            ).fetchall()
        return [_row_to_analysis(row) for row in rows]


def _content_hash(analysis: AffiliateAnalysis) -> str:
    import hashlib

    payload = "\x1f".join(
        [
            "|".join(analysis.usp_list),
            "|".join(analysis.pain_points),
            analysis.target_audience,
            analysis.tiktok_script.hook,
            analysis.tiktok_script.body,
            analysis.tiktok_script.cta,
            analysis.visual_prompts.image_prompt,
            analysis.visual_prompts.video_prompt,
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
