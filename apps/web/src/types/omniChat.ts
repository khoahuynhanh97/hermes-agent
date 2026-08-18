export interface ToolCall {
  id: string
  name: 'read_file' | 'product_to_video' | 'web_search' | 'video_render' | string
  title?: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  args?: Record<string, any>
  data?: Record<string, any>
  durationMs?: number
}

export interface PipelineProgress {
  step: number
  totalSteps: number
  stepName: string
  percent: number
  status: 'running' | 'completed' | 'failed'
  message: string
}

export interface GeneratedAssetItem {
  asset_id: string
  label?: string
  scene?: string
  duration?: number
  url: string
}

export interface VideoResult {
  projectId: string
  productName: string
  videoAssetId: string
  videoUrl: string
  thumbnailUrl?: string
  durationSeconds: number
  aspectRatio: string
  resolution: string
  format?: string
  scenesCount: number
  status: string
  workspaceUrl: string
  assets?: GeneratedAssetItem[]
}

export interface ChatMessage {
  id: string
  sender: 'user' | 'assistant' | 'system'
  text: string
  timestamp: string
  isStreaming?: boolean
  intent?: 'read_file' | 'product_to_video' | 'general_chat' | string
  toolCalls?: ToolCall[]
  pipelineProgress?: PipelineProgress
  videoResult?: VideoResult
  error?: string
}

export interface PromptTemplate {
  id: string
  icon: string
  title: string
  category: 'video' | 'docs' | 'creative' | 'analysis'
  prompt: string
  description: string
}
