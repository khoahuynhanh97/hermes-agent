from typing import List, Optional
from sqlmodel import Session, select

from .db import get_session
from .models import VideoAnalytics, AnalyticsSnapshot


class AnalyticsService:
    def __init__(self, session: Session):
        self.session = session

    # ── VideoAnalytics CRUD ──────────────────────────────────────────────

    def upsert_analytics(
        self,
        project_id: str,
        asset_id: str,
        platform: str,
        platform_post_id: str,
        metrics: dict,
    ) -> VideoAnalytics:
        statement = select(VideoAnalytics).where(
            VideoAnalytics.asset_id == asset_id,
            VideoAnalytics.platform == platform,
        )
        existing = self.session.exec(statement).first()

        if existing:
            for key, value in metrics.items():
                if hasattr(existing, key):
                    setattr(existing, key, value)
            existing.last_synced_at = metrics.get("last_synced_at", existing.last_synced_at)
            existing.updated_at = metrics.get("updated_at", existing.updated_at)
            self.session.add(existing)
            self.session.commit()
            self.session.refresh(existing)
            return existing

        analytics = VideoAnalytics(
            project_id=project_id,
            asset_id=asset_id,
            platform=platform,
            platform_post_id=platform_post_id,
            **{k: v for k, v in metrics.items() if hasattr(VideoAnalytics, k)},
        )
        self.session.add(analytics)
        self.session.commit()
        self.session.refresh(analytics)
        return analytics

    def get_analytics(self, project_id: str, asset_id: Optional[str] = None) -> List[VideoAnalytics]:
        statement = select(VideoAnalytics).where(VideoAnalytics.project_id == project_id)
        if asset_id:
            statement = statement.where(VideoAnalytics.asset_id == asset_id)
        return self.session.exec(statement).all()

    def get_project_analytics_summary(self, project_id: str) -> dict:
        videos = self.get_analytics(project_id)
        if not videos:
            return {
                "total_views": 0,
                "total_likes": 0,
                "total_comments": 0,
                "total_shares": 0,
                "total_saves": 0,
                "average_engagement_rate": 0.0,
                "video_count": 0,
            }
        total_views = sum(v.views for v in videos)
        total_likes = sum(v.likes for v in videos)
        total_comments = sum(v.comments for v in videos)
        total_shares = sum(v.shares for v in videos)
        total_saves = sum(v.saves for v in videos)
        avg_engagement = (
            sum(v.engagement_rate for v in videos) / len(videos) if videos else 0.0
        )
        return {
            "total_views": total_views,
            "total_likes": total_likes,
            "total_comments": total_comments,
            "total_shares": total_shares,
            "total_saves": total_saves,
            "average_engagement_rate": round(avg_engagement, 4),
            "video_count": len(videos),
        }

    # ── AnalyticsSnapshot CRUD ───────────────────────────────────────────

    def record_snapshot(
        self,
        project_id: str,
        asset_id: str,
        platform: str,
        metrics: dict,
    ) -> AnalyticsSnapshot:
        snapshot = AnalyticsSnapshot(
            project_id=project_id,
            asset_id=asset_id,
            platform=platform,
            snapshot_time=metrics.get("snapshot_time", ""),
            views=metrics.get("views", 0),
            likes=metrics.get("likes", 0),
            comments=metrics.get("comments", 0),
            shares=metrics.get("shares", 0),
            engagement_rate=metrics.get("engagement_rate", 0.0),
        )
        self.session.add(snapshot)
        self.session.commit()
        self.session.refresh(snapshot)
        return snapshot

    def get_snapshots(
        self, project_id: str, asset_id: str, limit: int = 30
    ) -> List[AnalyticsSnapshot]:
        statement = (
            select(AnalyticsSnapshot)
            .where(
                AnalyticsSnapshot.project_id == project_id,
                AnalyticsSnapshot.asset_id == asset_id,
            )
            .order_by(AnalyticsSnapshot.snapshot_time.desc())
            .limit(limit)
        )
        return self.session.exec(statement).all()

    # ── Aggregation ──────────────────────────────────────────────────────

    def get_total_views(self, project_id: str) -> int:
        videos = self.get_analytics(project_id)
        return sum(v.views for v in videos)

    def get_total_engagement(self, project_id: str) -> dict:
        videos = self.get_analytics(project_id)
        return {
            "likes": sum(v.likes for v in videos),
            "comments": sum(v.comments for v in videos),
            "shares": sum(v.shares for v in videos),
            "saves": sum(v.saves for v in videos),
        }

    def get_top_performing_videos(self, limit: int = 10) -> List[VideoAnalytics]:
        statement = (
            select(VideoAnalytics)
            .order_by(VideoAnalytics.views.desc())
            .limit(limit)
        )
        return self.session.exec(statement).all()

    def get_platform_breakdown(self, project_id: str) -> dict:
        videos = self.get_analytics(project_id)
        breakdown: dict[str, dict] = {}
        for v in videos:
            if v.platform not in breakdown:
                breakdown[v.platform] = {
                    "views": 0,
                    "likes": 0,
                    "comments": 0,
                    "shares": 0,
                    "video_count": 0,
                }
            breakdown[v.platform]["views"] += v.views
            breakdown[v.platform]["likes"] += v.likes
            breakdown[v.platform]["comments"] += v.comments
            breakdown[v.platform]["shares"] += v.shares
            breakdown[v.platform]["video_count"] += 1
        return breakdown


def get_analytics_service() -> AnalyticsService:
    with get_session() as session:
        yield AnalyticsService(session)
