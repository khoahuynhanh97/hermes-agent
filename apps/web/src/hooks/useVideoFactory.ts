import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../lib/api'
import { VideoFactoryProject, ProjectSummary, ABVariantSet, Publication, TikTokConnectionStatus } from '../types/videoFactory'

export function useProjectsList() {
  return useQuery<{ status: string; data: ProjectSummary[] }>({
    queryKey: ['vf-projects'],
    queryFn: async () => {
      const res = await api.get<{ status: string; data: any[] }>('/api/vf/projects')
      return {
        status: res.status,
        data: (res.data || []).map((item) => ({
          id: item.id,
          status: item.status || 'draft',
        })),
      }
    },
    staleTime: 5000,
  })
}

export function useProjectDetail(projectId?: string) {
  return useQuery<{ status: string; data: VideoFactoryProject }>({
    queryKey: ['vf-project', projectId],
    queryFn: async () => {
      if (!projectId) throw new Error('Project ID required')
      return api.get<{ status: string; data: VideoFactoryProject }>(
        `/api/vf/projects/${encodeURIComponent(projectId)}`
      )
    },
    enabled: Boolean(projectId),
    staleTime: 2000,
  })
}

export function useCreateProject() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (projectId: string) => {
      return api.post<{ status: string; data: VideoFactoryProject }>(
        '/api/vf/projects',
        { project_id: projectId }
      )
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['vf-projects'] })
    },
  })
}

export function useBindResources() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ projectId, productQuery }: { projectId: string; productQuery: string }) => {
      return api.post<{ status: string; data: VideoFactoryProject }>(
        `/api/vf/projects/${encodeURIComponent(projectId)}/resources/bind`,
        { product_query: productQuery }
      )
    },
    onSuccess: (_, vars) => {
      queryClient.invalidateQueries({ queryKey: ['vf-project', vars.projectId] })
      queryClient.invalidateQueries({ queryKey: ['vf-projects'] })
    },
  })
}

export function useSaveBrief() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({
      projectId,
      objective,
      targetAudience,
      coreMessage,
      contentBlocks,
    }: {
      projectId: string
      objective: string
      targetAudience: string
      coreMessage: string
      contentBlocks?: string[]
    }) => {
      return api.post<{ status: string; data: VideoFactoryProject }>(
        `/api/vf/projects/${encodeURIComponent(projectId)}/brief`,
        {
          objective,
          target_audience: targetAudience,
          core_message: coreMessage,
          content_blocks: contentBlocks || ['Hook', 'Use case', 'Highlights', 'Call to action'],
        }
      )
    },
    onSuccess: (_, vars) => {
      queryClient.invalidateQueries({ queryKey: ['vf-project', vars.projectId] })
    },
  })
}

export function useApproveBrief() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (projectId: string) => {
      return api.post<{ status: string; data: VideoFactoryProject }>(
        `/api/vf/projects/${encodeURIComponent(projectId)}/brief/approve`
      )
    },
    onSuccess: (_, projectId) => {
      queryClient.invalidateQueries({ queryKey: ['vf-project', projectId] })
      queryClient.invalidateQueries({ queryKey: ['vf-projects'] })
    },
  })
}

export function useApproveScenes() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (projectId: string) => {
      return api.post<{ status: string; data: VideoFactoryProject }>(
        `/api/vf/projects/${encodeURIComponent(projectId)}/scenes/approve`
      )
    },
    onSuccess: (_, projectId) => {
      queryClient.invalidateQueries({ queryKey: ['vf-project', projectId] })
      queryClient.invalidateQueries({ queryKey: ['vf-projects'] })
    },
  })
}

export function useGenerateStoryboard() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (projectId: string) => {
      return api.post<{ status: string; jobs: { job_id: string }[]; data: VideoFactoryProject }>(
        `/api/vf/projects/${encodeURIComponent(projectId)}/storyboard/generate`
      )
    },
    onSuccess: (_, projectId) => {
      queryClient.invalidateQueries({ queryKey: ['vf-project', projectId] })
      queryClient.invalidateQueries({ queryKey: ['vf-projects'] })
    },
  })
}

export function useGenerateVoiceover() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({
      projectId,
      text,
      voice = 'Zephyr',
      stylePrompt = 'Clear product review',
    }: {
      projectId: string
      text: string
      voice?: string
      stylePrompt?: string
    }) => {
      return api.post<{ status: string; job_id?: string; asset_id?: string; data: VideoFactoryProject }>(
        `/api/vf/projects/${encodeURIComponent(projectId)}/tts`,
        { text, voice, style_prompt: stylePrompt }
      )
    },
    onSuccess: (_, vars) => {
      queryClient.invalidateQueries({ queryKey: ['vf-project', vars.projectId] })
    },
  })
}

export function useMixAudio() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ projectId, voiceoverAssetId }: { projectId: string; voiceoverAssetId?: string }) => {
      return api.post<{ status: string; mixed_audio_asset_id?: string; data: VideoFactoryProject }>(
        `/api/vf/projects/${encodeURIComponent(projectId)}/tts/mix`,
        { voiceover_asset_id: voiceoverAssetId }
      )
    },
    onSuccess: (_, vars) => {
      queryClient.invalidateQueries({ queryKey: ['vf-project', vars.projectId] })
    },
  })
}

export function useRenderTimeline() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (projectId: string) => {
      return api.post<{ status: string; job_id?: string; data: VideoFactoryProject }>(
        `/api/vf/projects/${encodeURIComponent(projectId)}/timeline/render`
      )
    },
    onSuccess: (_, projectId) => {
      queryClient.invalidateQueries({ queryKey: ['vf-project', projectId] })
      queryClient.invalidateQueries({ queryKey: ['vf-projects'] })
    },
  })
}

export function useExportFinalVideo() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (projectId: string) => {
      return api.post<{ status: string; job_id?: string; data: VideoFactoryProject }>(
        `/api/vf/projects/${encodeURIComponent(projectId)}/final/export`
      )
    },
    onSuccess: (_, projectId) => {
      queryClient.invalidateQueries({ queryKey: ['vf-project', projectId] })
      queryClient.invalidateQueries({ queryKey: ['vf-projects'] })
    },
  })
}

export function useProjectProgress(projectId?: string) {
  return useQuery({
    queryKey: ['vf-project-progress', projectId],
    queryFn: async () => {
      if (!projectId) return null;
      // In a real app, you would fetch from your API
      // For now, simulating the response structure
      console.log(`Fetching progress for ${projectId}`);
      const stages = [
        "Resource Pack", "Brief", "Scene Plan", "Storyboard",
        "TTS", "Render Scenes", "Timeline", "MP4 Export"
      ];
      const current_stage_index = Math.floor(Math.random() * (stages.length + 1));
      const progress = stages.map((name, i) => ({
        stage: name,
        status: i < current_stage_index ? 'completed' : (i === current_stage_index ? 'in_progress' : 'pending'),
      }));
      
      return Promise.resolve({ project_id: projectId, progress });
    },
    enabled: !!projectId,
    refetchInterval: 5000, // Refetch every 5 seconds
  });
}

export function useGenerateABVariants() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({
      projectId,
      prompt,
      productQuery,
      durationSeconds = 30,
      platform = 'TikTok',
      language = 'Vietnamese',
    }: {
      projectId: string
      prompt?: string
      productQuery?: string
      durationSeconds?: number
      platform?: string
      language?: string
    }) => {
      return api.post<{ status: string; variants: any[]; project_id: string }>(
        `/api/vf/projects/${encodeURIComponent(projectId)}/ab-variants/generate`,
        {
          prompt: prompt || 'Tạo video TikTok review sản phẩm dài 30 giây',
          product_query: productQuery,
          duration_seconds: durationSeconds,
          platform,
          language,
        }
      )
    },
    onSuccess: (_, vars) => {
      queryClient.invalidateQueries({ queryKey: ['vf-project', vars.projectId] })
      queryClient.invalidateQueries({ queryKey: ['vf-ab-variants', vars.projectId] })
    },
  })
}

export function useABVariants(projectId?: string) {
  return useQuery<{ status: string; data: ABVariantSet }>({
    queryKey: ['vf-ab-variants', projectId],
    queryFn: async () => {
      if (!projectId) throw new Error('Project ID required')
      return api.get<{ status: string; data: ABVariantSet }>(
        `/api/vf/projects/${encodeURIComponent(projectId)}/ab-variants`
      )
    },
    enabled: Boolean(projectId),
    staleTime: 3000,
  })
}

export function useSelectVariant() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({
      projectId,
      variantId,
    }: {
      projectId: string
      variantId: string
    }) => {
      return api.post<{ status: string; selected_variant_id: string }>(
        `/api/vf/projects/${encodeURIComponent(projectId)}/ab-variants/${encodeURIComponent(variantId)}/select`
      )
    },
    onSuccess: (_, vars) => {
      queryClient.invalidateQueries({ queryKey: ['vf-project', vars.projectId] })
      queryClient.invalidateQueries({ queryKey: ['vf-ab-variants', vars.projectId] })
    },
  })
}

// ── Publishing Hooks ─────────────────────────────────────────────────

export function useTikTokAuthStatus() {
  return useQuery<{ status: string; connected: boolean }>({
    queryKey: ['publish-tiktok-status'],
    queryFn: () => api.get('/api/publish/tiktok/status'),
    staleTime: 10000,
  })
}

export function useTikTokAuthUrl() {
  return useQuery<{ status: string; auth_url: string; redirect_uri: string }>({
    queryKey: ['publish-tiktok-auth-url'],
    queryFn: () => api.get('/api/publish/tiktok/auth-url'),
    staleTime: 60000,
  })
}

export function usePublishToTikTok() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({
      projectId,
      assetId,
      videoPath,
      caption,
      visibility,
    }: {
      projectId: string
      assetId: string
      videoPath?: string
      caption?: string
      visibility?: string
    }) => {
      return api.post<{
        status: string
        publication_id: string
        platform_post_id?: string
        publication_status: string
      }>('/api/publish/tiktok', {
        project_id: projectId,
        asset_id: assetId,
        video_path: videoPath || '',
        caption: caption || '',
        visibility: visibility || 'public',
      })
    },
    onSuccess: (_, vars) => {
      queryClient.invalidateQueries({ queryKey: ['publish-publications', vars.projectId] })
      queryClient.invalidateQueries({ queryKey: ['publish-history'] })
    },
  })
}

export function usePublicationStatus(publicationId?: string) {
  return useQuery<{ status: string; publication: Publication }>({
    queryKey: ['publish-publication', publicationId],
    queryFn: () => api.get(`/api/publish/tiktok/${publicationId}`),
    enabled: Boolean(publicationId),
    refetchInterval: 5000,
  })
}

export function usePublicationHistory(projectId?: string) {
  return useQuery<{ status: string; publications: Publication[] }>({
    queryKey: ['publish-history', projectId],
    queryFn: () => {
      const params = projectId ? `?project_id=${encodeURIComponent(projectId)}` : ''
      return api.get(`/api/publish/history${params}`)
    },
    staleTime: 5000,
  })
}

export function useYouTubeStatus() {
  return useQuery<{ status: string; connected: boolean }>({
    queryKey: ['publish-youtube-status'],
    queryFn: () => api.get('/api/publish/youtube/status'),
    staleTime: 10000,
  })
}

export function useInstagramStatus() {
  return useQuery<{ status: string; connected: boolean }>({
    queryKey: ['publish-instagram-status'],
    queryFn: () => api.get('/api/publish/instagram/status'),
    staleTime: 10000,
  })
}

