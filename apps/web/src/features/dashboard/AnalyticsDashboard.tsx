import React, { useState } from 'react'
import { Link } from 'react-router-dom'
import {
  Eye,
  ThumbsUp,
  MessageCircle,
  Share2,
  Bookmark,
  TrendingUp,
  Film,
  ArrowRight,
  RefreshCw,
  ExternalLink,
  ChevronDown,
  ChevronUp,
} from 'lucide-react'
import {
  useAnalyticsOverview,
  useAnalyticsList,
  usePlatformBreakdown,
  useAnalyticsTrends,
} from '../../hooks/useAnalytics'
import { VideoAnalytics, PlatformBreakdown as PlatformBreakdownType } from '../../hooks/useAnalytics'
import { Button } from '../../components/common/Button'
import { Badge, BadgeVariant } from '../../components/common/Badge'
import './AnalyticsDashboard.css'

const PLATFORM_COLORS: Record<string, string> = {
  tiktok: '#ff0050',
  youtube_shorts: '#ff0000',
  instagram_reels: '#c13584',
  youtube: '#ff0000',
  instagram: '#c13584',
}

const PLATFORM_LABELS: Record<string, string> = {
  tiktok: 'TikTok',
  youtube_shorts: 'YouTube Shorts',
  instagram_reels: 'Instagram Reels',
  youtube: 'YouTube',
  instagram: 'Instagram',
}

function formatNumber(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`
  return n.toString()
}

function formatRate(rate: number): string {
  return `${(rate * 100).toFixed(1)}%`
}

interface OverviewCardsProps {
  totalViews: number
  totalEngagement: { likes: number; comments: number; shares: number; saves: number }
  avgEngagementRate: number
  videoCount: number
  loading: boolean
}

function OverviewCards({ totalViews, totalEngagement, avgEngagementRate, videoCount, loading }: OverviewCardsProps) {
  const cards = [
    { label: 'TOTAL VIEWS', value: formatNumber(totalViews), icon: <Eye size={16} />, color: 'var(--accent-primary)' },
    {
      label: 'TOTAL ENGAGEMENT',
      value: formatNumber(totalEngagement.likes + totalEngagement.comments + totalEngagement.shares),
      icon: <ThumbsUp size={16} />,
      color: 'var(--status-success)',
    },
    { label: 'AVG ENGAGEMENT RATE', value: formatRate(avgEngagementRate), icon: <TrendingUp size={16} />, color: 'var(--accent-timeline)' },
    { label: 'VIDEOS PUBLISHED', value: videoCount.toString(), icon: <Film size={16} />, color: '#c13584' },
  ]

  return (
    <div className="analytics-metrics-grid">
      {cards.map((card) => (
        <div key={card.label} className="metric-box">
          <div className="metric-header">
            <span className="metric-label">{card.label}</span>
            <span style={{ color: card.color }}>{card.icon}</span>
          </div>
          <div className="metric-number">{loading ? '--' : card.value}</div>
        </div>
      ))}
    </div>
  )
}

interface PlatformCardProps {
  platform: string
  data: { views: number; likes: number; comments: number; shares: number; video_count: number }
}

function PlatformCard({ platform, data }: PlatformCardProps) {
  const color = PLATFORM_COLORS[platform] || 'var(--text-secondary)'
  const label = PLATFORM_LABELS[platform] || platform
  const engagement = data.likes + data.comments + data.shares

  return (
    <div className="platform-card">
      <div className="platform-card-header">
        <div className="platform-dot" style={{ backgroundColor: color }} />
        <span className="platform-name">{label}</span>
        <Badge variant="neutral" size="sm">{data.video_count} videos</Badge>
      </div>
      <div className="platform-stats">
        <div className="platform-stat">
          <Eye size={13} />
          <span>{formatNumber(data.views)} views</span>
        </div>
        <div className="platform-stat">
          <ThumbsUp size={13} />
          <span>{formatNumber(engagement)} engagement</span>
        </div>
      </div>
    </div>
  )
}

interface TrendBarProps {
  date: string
  views: number
  maxViews: number
}

function TrendBar({ date, views, maxViews }: TrendBarProps) {
  const heightPct = maxViews > 0 ? (views / maxViews) * 100 : 0
  const shortDate = date.length > 10 ? date.slice(5, 10) : date

  return (
    <div className="trend-bar-col">
      <div className="trend-bar-value">{formatNumber(views)}</div>
      <div className="trend-bar-track">
        <div className="trend-bar-fill" style={{ height: `${Math.max(heightPct, 2)}%` }} />
      </div>
      <div className="trend-bar-date">{shortDate}</div>
    </div>
  )
}

interface VideoRowProps {
  video: VideoAnalytics
  rank: number
  expanded: boolean
  onToggle: () => void
}

function VideoRow({ video, rank, expanded, onToggle }: VideoRowProps) {
  const platformColor = PLATFORM_COLORS[video.platform] || 'var(--text-secondary)'
  const platformLabel = PLATFORM_LABELS[video.platform] || video.platform

  return (
    <>
      <tr className="analytics-table-row" onClick={onToggle}>
        <td>
          <span className="rank-badge">#{rank}</span>
        </td>
        <td>
          <strong style={{ color: 'var(--text-primary)' }}>{video.asset_id}</strong>
        </td>
        <td>
          <Badge variant={getPlatformVariant(video.platform)} size="sm">{platformLabel}</Badge>
        </td>
        <td>{formatNumber(video.views)}</td>
        <td>{formatRate(video.engagement_rate)}</td>
        <td style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
          {video.published_at ? new Date(video.published_at).toLocaleDateString() : '--'}
        </td>
        <td>
          {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        </td>
      </tr>
      {expanded && (
        <tr className="analytics-detail-row">
          <td colSpan={7}>
            <div className="video-detail-grid">
              <div className="detail-stat"><ThumbsUp size={13} /> {formatNumber(video.likes)} likes</div>
              <div className="detail-stat"><MessageCircle size={13} /> {formatNumber(video.comments)} comments</div>
              <div className="detail-stat"><Share2 size={13} /> {formatNumber(video.shares)} shares</div>
              <div className="detail-stat"><Bookmark size={13} /> {formatNumber(video.saves)} saves</div>
              {video.platform_url && (
                <a href={video.platform_url} target="_blank" rel="noopener noreferrer" className="detail-link">
                  <ExternalLink size={13} /> View on Platform
                </a>
              )}
            </div>
          </td>
        </tr>
      )}
    </>
  )
}

function getPlatformVariant(platform: string): BadgeVariant {
  switch (platform) {
    case 'tiktok': return 'active'
    case 'youtube_shorts': return 'error'
    case 'instagram_reels': return 'running'
    default: return 'neutral'
  }
}

export const AnalyticsDashboard: React.FC = () => {
  const [expandedVideo, setExpandedVideo] = useState<string | null>(null)
  const [trendView, setTrendView] = useState<'daily' | 'weekly'>('daily')

  const { data: overview, isLoading: loadingOverview } = useAnalyticsOverview()
  const { data: videos, isLoading: loadingVideos } = useAnalyticsList()
  const { data: platforms } = usePlatformBreakdown('')
  const { data: trends } = useAnalyticsTrends('')

  const overviewData = overview || { total_views: 0, total_engagement: { likes: 0, comments: 0, shares: 0, saves: 0 }, average_engagement_rate: 0, video_count: 0, top_videos: [] }
  const videoList = videos || []
  const platformData: PlatformBreakdownType = platforms || {}
  const trendData = trends || []

  const maxTrendViews = trendData.length > 0 ? Math.max(...trendData.map((t) => t.views)) : 0

  return (
    <div className="analytics-container">
      <div className="analytics-topbar">
        <div>
          <h1 style={{ fontSize: '20px', fontWeight: 600, color: 'var(--text-primary)' }}>
            Video Analytics
          </h1>
          <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginTop: '2px' }}>
            Publishing Performance Dashboard
          </p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <Link
            to="/dashboard"
            style={{ fontSize: '12px', color: 'var(--accent-primary)', display: 'flex', alignItems: 'center', gap: '4px' }}
          >
            <span>Back to Dashboard</span>
            <ArrowRight size={13} />
          </Link>
        </div>
      </div>

      <OverviewCards
        totalViews={overviewData.total_views}
        totalEngagement={overviewData.total_engagement}
        avgEngagementRate={overviewData.average_engagement_rate}
        videoCount={overviewData.video_count}
        loading={loadingOverview}
      />

      {/* Platform Breakdown */}
      <div className="analytics-card">
        <div className="analytics-card-header">
          <h3 style={{ fontSize: '14px', fontWeight: 600, color: 'var(--text-primary)' }}>Platform Breakdown</h3>
        </div>
        <div className="platform-grid">
          {Object.keys(platformData).length === 0 ? (
            <div className="empty-state-text">No platform data yet. Sync video metrics to see breakdown.</div>
          ) : (
            Object.entries(platformData).map(([platform, data]) => (
              <PlatformCard key={platform} platform={platform} data={data} />
            ))
          )}
        </div>
      </div>

      {/* Top Performing Videos */}
      <div className="analytics-card">
        <div className="analytics-card-header">
          <h3 style={{ fontSize: '14px', fontWeight: 600, color: 'var(--text-primary)' }}>Top Performing Videos</h3>
          <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
            {videoList.length} total
          </span>
        </div>
        <div className="table-container">
          <table className="analytics-data-table">
            <thead>
              <tr>
                <th style={{ width: '50px' }}>Rank</th>
                <th>Asset</th>
                <th>Platform</th>
                <th>Views</th>
                <th>Engagement</th>
                <th>Published</th>
                <th style={{ width: '40px' }}></th>
              </tr>
            </thead>
            <tbody>
              {videoList.length === 0 ? (
                <tr>
                  <td colSpan={7} style={{ textAlign: 'center', padding: '32px', color: 'var(--text-muted)' }}>
                    No video analytics data yet. Publish videos and sync metrics.
                  </td>
                </tr>
              ) : (
                videoList
                  .sort((a, b) => b.views - a.views)
                  .slice(0, 10)
                  .map((video, idx) => (
                    <VideoRow
                      key={video.asset_id}
                      video={video}
                      rank={idx + 1}
                      expanded={expandedVideo === video.asset_id}
                      onToggle={() => setExpandedVideo(expandedVideo === video.asset_id ? null : video.asset_id)}
                    />
                  ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Engagement Trend */}
      <div className="analytics-card">
        <div className="analytics-card-header">
          <h3 style={{ fontSize: '14px', fontWeight: 600, color: 'var(--text-primary)' }}>Engagement Trend</h3>
          <div className="trend-toggle">
            <button
              className={`trend-toggle-btn ${trendView === 'daily' ? 'active' : ''}`}
              onClick={() => setTrendView('daily')}
            >
              Daily
            </button>
            <button
              className={`trend-toggle-btn ${trendView === 'weekly' ? 'active' : ''}`}
              onClick={() => setTrendView('weekly')}
            >
              Weekly
            </button>
          </div>
        </div>
        <div className="trend-chart">
          {trendData.length === 0 ? (
            <div className="empty-state-text">No trend data yet. Metrics snapshots will appear here.</div>
          ) : (
            <div className="trend-bars-container">
              {trendData.slice(0, trendView === 'daily' ? 30 : 12).map((t) => (
                <TrendBar key={t.id} date={t.snapshot_time} views={t.views} maxViews={maxTrendViews} />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
