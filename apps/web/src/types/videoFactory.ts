export type StageKey =
  | 'resources'
  | 'brief'
  | 'scenes'
  | 'storyboard'
  | 'generation'
  | 'timeline'
  | 'export'

export type StageState =
  | 'completed'
  | 'active'
  | 'running'
  | 'blocked'
  | 'not_started'
  | 'failed'

export interface StageMeta {
  key: StageKey
  label: string
  shortLabel: string
  description: string
  order: number
}

export const CANONICAL_STAGES: StageMeta[] = [
  { key: 'resources', label: '1. Product Resources', shortLabel: 'Resources', description: 'Product identity & locked references', order: 1 },
  { key: 'brief', label: '2. Creative Brief', shortLabel: 'Brief', description: 'Objective, target audience & core message', order: 2 },
  { key: 'scenes', label: '3. Scene Plan', shortLabel: 'Scenes', description: '30s timeline structure & pacing', order: 3 },
  { key: 'storyboard', label: '4. Storyboard Keyframes', shortLabel: 'Storyboard', description: 'Visual keyframe generation & review', order: 4 },
  { key: 'generation', label: '5. Scene Videos', shortLabel: 'Generation', description: 'Video generation per scene & QC', order: 5 },
  { key: 'timeline', label: '6. Timeline & Voiceover', shortLabel: 'Timeline', description: 'TTS, pacing & rough draft assembly', order: 6 },
  { key: 'export', label: '7. Final Export', shortLabel: 'Export', description: 'Full 30s master video & publishing', order: 7 },
]

export interface AssetRef {
  asset_id: string
  uri?: string
  metadata?: {
    physical_hash_filename?: string
    mime_type?: string
    snapshot_id?: string
    resource_pack_lock_id?: string
    [key: string]: any
  }
}

export interface ResourceIdentity {
  description?: string
  color?: string
  distinctive_features?: string[]
}

export interface ResourcePack {
  id: string
  owner_user_id: string
  product_references: AssetRef[]
  primary_product_asset_id: string
  product_identity_description: string
  locked_product_identity?: ResourceIdentity
  locked_at: string
  version: number
}

export interface CreativeBrief {
  objective: string
  target_audience: string
  core_message: string
  content_blocks: string[]
}

export interface Scene {
  scene_id: string
  order: number
  title: string
  purpose: string
  content: string
  visual_style: string
  duration_seconds: number
  setting: string
  camera_movement: string
}

export interface ScenePlan {
  scenes: Scene[]
}

export interface FramePrompt {
  positive_prompt: string
  negative_constraints: string
  product_identity_constraints: string
  character_identity_constraints?: string
  aspect_ratio?: string
  reference_asset_ids?: string[]
  provider_options?: Record<string, any>
}

export interface StoryboardFrame {
  frame_id: string
  scene_id: string
  order: number
  label: string
  purpose: string
  visual_state: string
  subject_action: string
  product_state: string
  context: string
  camera_intention: string
  required_resource_ids: string[]
  prompt: FramePrompt
  generation_status: 'not_started' | 'generating' | 'completed' | 'failed'
  generated_asset_id?: string
  generation_job_id?: string
  review_notes?: string
  version: number
  created_at?: string
}

export interface Storyboard {
  frames: StoryboardFrame[]
}

export interface VideoPrompt {
  scene_id: string
  duration_seconds: number
  start_visual_state: string
  end_visual_state: string
  subject_action: string
  product_action: string
  camera_movement: string
  camera_framing: string
  environment_motion: string
  identity_constraints: string
  reference_frame_ids: string[]
  dialogue_or_vo: string
  negative_constraints: string
  provider_options: Record<string, any>
}

export interface GeneratedScene {
  scene_id: string
  video_prompt: VideoPrompt
  generation_status: 'not_started' | 'generating' | 'completed' | 'failed'
  generated_asset_id?: string
  generation_job_id?: string
  provider_operation_id?: string | null
  review_notes?: string
  version: number
  created_at?: string
  updated_at?: string
}

export interface TimelineClip {
  scene_id: string
  start_time_seconds: number
  duration_seconds: number
  asset_id: string
}

export interface Timeline {
  clips: TimelineClip[]
  voiceover_asset_id?: string
  total_duration_seconds: number
}

export interface HookVariant {
  variant_id: string
  variant_label: string
  hook_angle: string
  creative_brief: CreativeBrief
  scene_plan: ScenePlan
  final_asset_id: string
  export_status: string
  timeline?: Timeline | null
}

export interface ABVariantSet {
  variants: HookVariant[]
  selected_variant_id: string
}

export interface VideoFactoryProject {
  id: string
  owner_user_id: string
  status: string
  resource_pack?: ResourcePack
  raw_idea?: any
  creative_brief?: CreativeBrief
  brief_approval?: 'draft' | 'approved' | 'rejected'
  scene_plan?: ScenePlan
  scene_plan_approval?: 'draft' | 'approved' | 'rejected'
  storyboard?: Storyboard
  generated_scenes?: GeneratedScene[]
  timeline?: Timeline
  draft_video_asset_id?: string
  final_video_asset_id?: string
  final_approval?: string
  final_approval_notes?: string
  ab_variants?: ABVariantSet
  resource_version?: number
  brief_version?: number
  scene_version?: number
  storyboard_version?: number
  video_generation_version?: number
  timeline_version?: number
  created_at?: string
  updated_at?: string
}

export interface ProjectSummary {
  id: string
  status: string
  product_name?: string
  primary_asset_id?: string
  current_stage?: StageKey
  progress_percent?: number
}

export interface Publication {
  id: string
  platform: 'tiktok' | 'youtube_shorts' | 'instagram_reels'
  project_id: string
  status: 'not_published' | 'uploading' | 'processing' | 'published' | 'failed'
  platform_post_id?: string
  caption?: string
  published_at?: string
  last_error?: string
  created_at: string
  updated_at: string
}

export interface TikTokConnectionStatus {
  connected: boolean
  scopes?: string[]
  expires_at?: string
}
