from typing import Optional
from sqlmodel import Field, SQLModel


class VideoAnalytics(SQLModel, table=True):
    """Tracks video publishing performance metrics."""
    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: str = Field(index=True)
    asset_id: str = Field(index=True)
    platform: str  # tiktok, youtube_shorts, instagram_reels
    platform_post_id: str  # ID on the platform
    platform_url: str = ""  # URL to the post
    # Metrics (updated periodically)
    views: int = 0
    likes: int = 0
    comments: int = 0
    shares: int = 0
    saves: int = 0
    watch_time_seconds: float = 0.0
    average_watch_percentage: float = 0.0
    # Engagement rate
    engagement_rate: float = 0.0  # (likes + comments + shares) / views
    # Timestamps
    published_at: str = ""
    last_synced_at: str = ""
    created_at: str = ""
    updated_at: str = ""


class AnalyticsSnapshot(SQLModel, table=True):
    """Point-in-time analytics snapshot for trend tracking."""
    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: str = Field(index=True)
    asset_id: str = Field(index=True)
    platform: str
    snapshot_time: str
    views: int = 0
    likes: int = 0
    comments: int = 0
    shares: int = 0
    engagement_rate: float = 0.0
