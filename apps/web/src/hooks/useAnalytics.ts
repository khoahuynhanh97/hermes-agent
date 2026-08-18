import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../lib/api'

export interface VideoAnalytics {
  id: number
  project_id: string
  asset_id: string
  platform: string
  platform_post_id: string
  platform_url: string
  views: number
  likes: number
  comments: number
  shares: number
  saves: number
  watch_time_seconds: number
  average_watch_percentage: number
  engagement_rate: number
  published_at: string
  last_synced_at: string
  created_at: string
  updated_at: string
}

export interface AnalyticsOverview {
  total_views: number
  total_engagement: { likes: number; comments: number; shares: number; saves: number }
  average_engagement_rate: number
  video_count: number
  top_videos: VideoAnalytics[]
}

export interface AnalyticsSnapshot {
  id: number
  project_id: string
  asset_id: string
  platform: string
  snapshot_time: string
  views: number
  likes: number
  comments: number
  shares: number
  engagement_rate: number
}

export interface PlatformBreakdown {
  [platform: string]: {
    views: number
    likes: number
    comments: number
    shares: number
    video_count: number
  }
}

export function useAnalyticsOverview(projectId?: string) {
  return useQuery<AnalyticsOverview>({
    queryKey: ['analytics-overview', projectId],
    queryFn: async () => {
      if (projectId) {
        return api.get<AnalyticsOverview>(`/api/analytics/overview/${encodeURIComponent(projectId)}`)
      }
      return api.get<AnalyticsOverview>('/api/analytics/overview')
    },
    staleTime: 10000,
  })
}

export function useVideoAnalytics(assetId?: string) {
  return useQuery<VideoAnalytics>({
    queryKey: ['analytics-video', assetId],
    queryFn: async () => {
      if (!assetId) throw new Error('Asset ID required')
      return api.get<VideoAnalytics>(`/api/analytics/videos/${encodeURIComponent(assetId)}`)
    },
    enabled: Boolean(assetId),
    staleTime: 5000,
  })
}

export function useAnalyticsList(projectId?: string) {
  return useQuery<VideoAnalytics[]>({
    queryKey: ['analytics-list', projectId],
    queryFn: async () => {
      const params = projectId ? `?project_id=${encodeURIComponent(projectId)}` : ''
      return api.get<VideoAnalytics[]>(`/api/analytics/videos${params}`)
    },
    staleTime: 10000,
  })
}

export function useAnalyticsTrends(projectId: string) {
  return useQuery<AnalyticsSnapshot[]>({
    queryKey: ['analytics-trends', projectId],
    queryFn: async () => {
      return api.get<AnalyticsSnapshot[]>(`/api/analytics/trends/${encodeURIComponent(projectId)}`)
    },
    enabled: Boolean(projectId),
    staleTime: 10000,
  })
}

export function usePlatformBreakdown(projectId: string) {
  return useQuery<PlatformBreakdown>({
    queryKey: ['analytics-platforms', projectId],
    queryFn: async () => {
      return api.get<PlatformBreakdown>(`/api/analytics/platforms/${encodeURIComponent(projectId)}`)
    },
    enabled: Boolean(projectId),
    staleTime: 10000,
  })
}

export function useSyncMetrics() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({
      assetId,
      projectId,
      platform,
      platformPostId,
      metrics,
    }: {
      assetId: string
      projectId: string
      platform: string
      platformPostId: string
      metrics: Partial<VideoAnalytics>
    }) => {
      const params = new URLSearchParams({
        project_id: projectId,
        platform,
        platform_post_id: platformPostId,
      })
      return api.post<VideoAnalytics>(
        `/api/analytics/videos/${encodeURIComponent(assetId)}/sync?${params.toString()}`,
        metrics
      )
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['analytics-overview'] })
      queryClient.invalidateQueries({ queryKey: ['analytics-list'] })
      queryClient.invalidateQueries({ queryKey: ['analytics-trends'] })
      queryClient.invalidateQueries({ queryKey: ['analytics-platforms'] })
    },
  })
}
