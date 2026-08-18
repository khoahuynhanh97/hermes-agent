export interface ProductSummaryItem {
  snapshot_id: string
  research_id?: string
  product_id: string
  product_name: string
  brand: string
  model: string
  source_domain?: string
  media_count: number
  created_at: string
  pack_status?: string
  resource_pack_id?: string
  resource_pack_lock_id: string
  manifest_digest: string
}

export interface ProductAssetItem {
  asset_id: string
  role?: string
  mime_type?: string
  file_size?: number
  created_at?: string
  metadata?: Record<string, any>
}

export interface ProductDetailItem {
  snapshot_id: string
  product_id: string
  product_name: string
  brand: string
  model: string
  source_domain?: string
  status: string
  overview?: Record<string, any>
  research?: Record<string, any>
  resource_pack?: Record<string, any>
  storyboard?: Record<string, any>
  assets?: ProductAssetItem[]
  generated_media?: ProductAssetItem[]
}

export interface ResearchRunItem {
  run_id: string
  product_name: string
  status: string
  snapshot_id: string
  resource_pack_lock_id?: string
  created_at?: string
}

export interface ProductResearchRunResult {
  run_id: string
  status: string
  imported: number
  shortlisted: number
  package_ids: string[]
  local_sheet_paths: Record<string, string>
  warnings?: string[]
  phase_summary: Record<'research' | 'analysis' | 'script' | 'prompt', string>
  content_previews: Array<{
    package_id?: string
    product_id?: string
    product_name?: string
    angle?: string
    hook?: string
    script?: string
    ai_prompts?: string
    voiceover_plan?: string
  }>
  report?: string
}

export interface ProductResearchRunResponse {
  status: string
  intent: {
    raw_message: string
    category: string
    keyword: string
    min_price_vnd: number
    max_price_vnd: number
  }
  result: ProductResearchRunResult
}
