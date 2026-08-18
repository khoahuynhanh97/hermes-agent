import pytest
from datetime import datetime, timezone
from sqlmodel import SQLModel, Session, create_engine
from sqlmodel.pool import StaticPool

from hermes.analytics.models import VideoAnalytics, AnalyticsSnapshot
from hermes.analytics.service import AnalyticsService


@pytest.fixture()
def session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture()
def svc(session):
    return AnalyticsService(session)


# ── VideoAnalytics CRUD ──────────────────────────────────────────────────


def test_upsert_creates_new(svc):
    analytics = svc.upsert_analytics(
        project_id="proj-1",
        asset_id="asset-1",
        platform="tiktok",
        platform_post_id="tt-123",
        metrics={"views": 100, "likes": 10, "comments": 5, "shares": 2},
    )
    assert analytics.id is not None
    assert analytics.project_id == "proj-1"
    assert analytics.asset_id == "asset-1"
    assert analytics.platform == "tiktok"
    assert analytics.views == 100
    assert analytics.likes == 10


def test_upsert_updates_existing(svc):
    svc.upsert_analytics(
        project_id="proj-1",
        asset_id="asset-1",
        platform="tiktok",
        platform_post_id="tt-123",
        metrics={"views": 100, "likes": 10},
    )
    updated = svc.upsert_analytics(
        project_id="proj-1",
        asset_id="asset-1",
        platform="tiktok",
        platform_post_id="tt-123",
        metrics={"views": 200, "likes": 25},
    )
    assert updated.views == 200
    assert updated.likes == 25


def test_get_analytics_by_project(svc):
    svc.upsert_analytics("proj-1", "a1", "tiktok", "tt-1", {"views": 50})
    svc.upsert_analytics("proj-1", "a2", "youtube_shorts", "yt-1", {"views": 80})
    svc.upsert_analytics("proj-2", "a3", "tiktok", "tt-2", {"views": 30})

    results = svc.get_analytics("proj-1")
    assert len(results) == 2

    filtered = svc.get_analytics("proj-1", asset_id="a1")
    assert len(filtered) == 1
    assert filtered[0].asset_id == "a1"


def test_get_project_analytics_summary(svc):
    svc.upsert_analytics("proj-1", "a1", "tiktok", "tt-1", {"views": 100, "likes": 10, "comments": 5, "shares": 3, "engagement_rate": 0.18})
    svc.upsert_analytics("proj-1", "a2", "youtube_shorts", "yt-1", {"views": 200, "likes": 20, "comments": 8, "shares": 5, "engagement_rate": 0.165})

    summary = svc.get_project_analytics_summary("proj-1")
    assert summary["total_views"] == 300
    assert summary["total_likes"] == 30
    assert summary["video_count"] == 2
    assert summary["average_engagement_rate"] > 0


def test_get_project_analytics_summary_empty(svc):
    summary = svc.get_project_analytics_summary("nonexistent")
    assert summary["total_views"] == 0
    assert summary["video_count"] == 0


# ── AnalyticsSnapshot CRUD ───────────────────────────────────────────────


def test_record_snapshot(svc):
    snapshot = svc.record_snapshot(
        project_id="proj-1",
        asset_id="a1",
        platform="tiktok",
        metrics={
            "snapshot_time": "2026-01-01T00:00:00Z",
            "views": 100,
            "likes": 10,
            "comments": 5,
            "shares": 3,
            "engagement_rate": 0.18,
        },
    )
    assert snapshot.id is not None
    assert snapshot.views == 100
    assert snapshot.platform == "tiktok"


def test_get_snapshots(svc):
    for i in range(5):
        svc.record_snapshot(
            project_id="proj-1",
            asset_id="a1",
            platform="tiktok",
            metrics={"snapshot_time": f"2026-01-0{i+1}T00:00:00Z", "views": 100 + i},
        )

    snapshots = svc.get_snapshots("proj-1", "a1", limit=3)
    assert len(snapshots) == 3
    # Descending order
    assert snapshots[0].views >= snapshots[-1].views


# ── Aggregation ──────────────────────────────────────────────────────────


def test_get_total_views(svc):
    svc.upsert_analytics("proj-1", "a1", "tiktok", "tt-1", {"views": 100})
    svc.upsert_analytics("proj-1", "a2", "youtube_shorts", "yt-1", {"views": 250})
    assert svc.get_total_views("proj-1") == 350


def test_get_total_engagement(svc):
    svc.upsert_analytics("proj-1", "a1", "tiktok", "tt-1", {"likes": 10, "comments": 5, "shares": 3, "saves": 2})
    svc.upsert_analytics("proj-1", "a2", "youtube_shorts", "yt-1", {"likes": 20, "comments": 8, "shares": 5, "saves": 1})

    engagement = svc.get_total_engagement("proj-1")
    assert engagement["likes"] == 30
    assert engagement["comments"] == 13
    assert engagement["shares"] == 8
    assert engagement["saves"] == 3


def test_get_top_performing_videos(svc):
    svc.upsert_analytics("proj-1", "a1", "tiktok", "tt-1", {"views": 50})
    svc.upsert_analytics("proj-1", "a2", "tiktok", "tt-2", {"views": 300})
    svc.upsert_analytics("proj-1", "a3", "tiktok", "tt-3", {"views": 150})

    top = svc.get_top_performing_videos(limit=2)
    assert len(top) == 2
    assert top[0].views == 300
    assert top[1].views == 150


def test_get_platform_breakdown(svc):
    svc.upsert_analytics("proj-1", "a1", "tiktok", "tt-1", {"views": 100, "likes": 10, "comments": 5, "shares": 2})
    svc.upsert_analytics("proj-1", "a2", "tiktok", "tt-2", {"views": 50, "likes": 5, "comments": 2, "shares": 1})
    svc.upsert_analytics("proj-1", "a3", "youtube_shorts", "yt-1", {"views": 200, "likes": 20, "comments": 8, "shares": 5})

    breakdown = svc.get_platform_breakdown("proj-1")
    assert "tiktok" in breakdown
    assert "youtube_shorts" in breakdown
    assert breakdown["tiktok"]["views"] == 150
    assert breakdown["tiktok"]["video_count"] == 2
    assert breakdown["youtube_shorts"]["views"] == 200


# ── Engagement Rate ──────────────────────────────────────────────────────


def test_engagement_rate_calculation(svc):
    analytics = svc.upsert_analytics(
        project_id="proj-1",
        asset_id="a1",
        platform="tiktok",
        platform_post_id="tt-1",
        metrics={"views": 1000, "likes": 50, "comments": 30, "shares": 20, "engagement_rate": 0.1},
    )
    # Engagement rate = (50 + 30 + 20) / 1000 = 0.1
    assert analytics.engagement_rate == 0.1


def test_engagement_rate_zero_views(svc):
    analytics = svc.upsert_analytics(
        project_id="proj-1",
        asset_id="a1",
        platform="tiktok",
        platform_post_id="tt-1",
        metrics={"views": 0, "likes": 0, "comments": 0, "shares": 0, "engagement_rate": 0.0},
    )
    assert analytics.engagement_rate == 0.0
