from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import select

from hermes.analytics.db import get_session
from hermes.analytics.service import AnalyticsService
from hermes.analytics.models import VideoAnalytics, AnalyticsSnapshot

router = APIRouter()


def _get_service():
    with get_session() as session:
        yield AnalyticsService(session)


# ── Overview ─────────────────────────────────────────────────────────────

@router.get("/overview")
def get_overview(svc: AnalyticsService = Depends(_get_service)):
    all_videos = svc.session.exec(select(VideoAnalytics)).all()
    if not all_videos:
        return {
            "total_views": 0,
            "total_engagement": {"likes": 0, "comments": 0, "shares": 0, "saves": 0},
            "average_engagement_rate": 0.0,
            "video_count": 0,
            "top_videos": [],
        }
    total_views = sum(v.views for v in all_videos)
    engagement = {
        "likes": sum(v.likes for v in all_videos),
        "comments": sum(v.comments for v in all_videos),
        "shares": sum(v.shares for v in all_videos),
        "saves": sum(v.saves for v in all_videos),
    }
    avg_engagement = sum(v.engagement_rate for v in all_videos) / len(all_videos)
    sorted_videos = sorted(all_videos, key=lambda v: v.views, reverse=True)[:5]
    return {
        "total_views": total_views,
        "total_engagement": engagement,
        "average_engagement_rate": round(avg_engagement, 4),
        "video_count": len(all_videos),
        "top_videos": [v.model_dump() for v in sorted_videos],
    }


@router.get("/overview/{project_id}")
def get_project_overview(
    project_id: str,
    svc: AnalyticsService = Depends(_get_service),
):
    return svc.get_project_analytics_summary(project_id)


# ── Video Analytics ──────────────────────────────────────────────────────

@router.get("/videos")
def list_videos(
    project_id: Optional[str] = Query(None),
    platform: Optional[str] = Query(None),
    svc: AnalyticsService = Depends(_get_service),
):
    statement = select(VideoAnalytics)
    if project_id:
        statement = statement.where(VideoAnalytics.project_id == project_id)
    if platform:
        statement = statement.where(VideoAnalytics.platform == platform)
    videos = svc.session.exec(statement).all()
    return [v.model_dump() for v in videos]


@router.get("/videos/{asset_id}")
def get_video(
    asset_id: str,
    svc: AnalyticsService = Depends(_get_service),
):
    statement = select(VideoAnalytics).where(VideoAnalytics.asset_id == asset_id)
    video = svc.session.exec(statement).first()
    if video is None:
        raise HTTPException(status_code=404, detail="Video analytics not found")
    return video.model_dump()


class SyncRequest(BaseModel):
    views: int = 0
    likes: int = 0
    comments: int = 0
    shares: int = 0
    saves: int = 0
    watch_time_seconds: float = 0.0
    average_watch_percentage: float = 0.0
    platform_url: str = ""


@router.post("/videos/{asset_id}/sync")
def sync_video(
    asset_id: str,
    body: SyncRequest,
    project_id: str = Query(...),
    platform: str = Query(...),
    platform_post_id: str = Query(...),
    svc: AnalyticsService = Depends(_get_service),
):
    now = datetime.now(timezone.utc).isoformat()
    metrics = body.model_dump()
    views = metrics.get("views", 0)
    if views > 0:
        metrics["engagement_rate"] = round(
            (metrics.get("likes", 0) + metrics.get("comments", 0) + metrics.get("shares", 0)) / views,
            4,
        )
    metrics["last_synced_at"] = now
    metrics["updated_at"] = now
    analytics = svc.upsert_analytics(
        project_id=project_id,
        asset_id=asset_id,
        platform=platform,
        platform_post_id=platform_post_id,
        metrics=metrics,
    )
    svc.record_snapshot(
        project_id=project_id,
        asset_id=asset_id,
        platform=platform,
        metrics={
            "snapshot_time": now,
            "views": views,
            "likes": metrics.get("likes", 0),
            "comments": metrics.get("comments", 0),
            "shares": metrics.get("shares", 0),
            "engagement_rate": metrics.get("engagement_rate", 0.0),
        },
    )
    return analytics.model_dump()


# ── Trends ───────────────────────────────────────────────────────────────

@router.get("/trends/{project_id}")
def get_trends(
    project_id: str,
    asset_id: Optional[str] = Query(None),
    limit: int = Query(30),
    svc: AnalyticsService = Depends(_get_service),
):
    if asset_id:
        snapshots = svc.get_snapshots(project_id, asset_id, limit=limit)
    else:
        statement = (
            select(AnalyticsSnapshot)
            .where(AnalyticsSnapshot.project_id == project_id)
            .order_by(AnalyticsSnapshot.snapshot_time.desc())
            .limit(limit)
        )
        snapshots = svc.session.exec(statement).all()
    return [s.model_dump() for s in snapshots]


# ── Platform Breakdown ──────────────────────────────────────────────────

@router.get("/platforms/{project_id}")
def get_platforms(
    project_id: str,
    svc: AnalyticsService = Depends(_get_service),
):
    return svc.get_platform_breakdown(project_id)


# ── Publishing Summary ──────────────────────────────────────────────────

@router.get("/publishing")
def get_publishing(
    project_id: Optional[str] = Query(None),
    limit: int = Query(20),
    svc: AnalyticsService = Depends(_get_service),
):
    statement = select(VideoAnalytics)
    if project_id:
        statement = statement.where(VideoAnalytics.project_id == project_id)
    statement = statement.order_by(VideoAnalytics.created_at.desc()).limit(limit)
    videos = svc.session.exec(statement).all()
    return [v.model_dump() for v in videos]
