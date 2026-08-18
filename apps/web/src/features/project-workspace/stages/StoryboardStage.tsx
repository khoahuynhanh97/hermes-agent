import React, { useState, useRef } from 'react'
import {
  Image as ImageIcon,
  Sparkles,
  RefreshCw,
  Eye,
  Sliders,
  CheckCircle2,
  AlertCircle,
  Clock,
  Layers,
  Upload,
  Loader2,
} from 'lucide-react'
import { VideoFactoryProject, StoryboardFrame } from '../../../types/videoFactory'
import { useGenerateStoryboard } from '../../../hooks/useVideoFactory'
import { api } from '../../../lib/api'
import { Badge, BadgeVariant } from '../../../components/common/Badge'
import { Button } from '../../../components/common/Button'
import { AssetThumbnail } from '../../../components/common/AssetThumbnail'
import { EmptyState } from '../../../components/common/EmptyState'
import { DependencyNotice } from '../../../components/pipeline/DependencyNotice'

interface StoryboardStageProps {
  project: VideoFactoryProject
  onInspectAsset: (assetId: string) => void
  onSelectFrameForInspector: (frame: StoryboardFrame) => void
  onTrackJob: (jobId: string) => void
}

export const StoryboardStage: React.FC<StoryboardStageProps> = ({
  project,
  onInspectAsset,
  onSelectFrameForInspector,
  onTrackJob,
}) => {
  const [notice, setNotice] = useState<{ text: string; ok: boolean } | null>(null)
  const [regeneratingFrameId, setRegeneratingFrameId] = useState<string | null>(null)
  const [uploadingFrameId, setUploadingFrameId] = useState<string | null>(null)
  const [bulkRegenerating, setBulkRegenerating] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [pendingUploadFrameId, setPendingUploadFrameId] = useState<string | null>(null)
  const generateMutation = useGenerateStoryboard()

  const isSceneApproved = project.scene_plan_approval === 'approved'
  const storyboard = project.storyboard
  const frames = storyboard?.frames || []
  const productAssets = project.resource_pack?.product_references || []

  const handleGenerateFrames = async () => {
    setNotice(null)
    try {
      const res = await generateMutation.mutateAsync(project.id)
      const jobId = res?.jobs?.[0]?.job_id
      if (jobId) {
        onTrackJob(jobId)
      }
      setNotice({ text: 'Storyboard generation triggered.', ok: true })
    } catch (err: any) {
      setNotice({ text: err.message || 'Failed to generate storyboard frames', ok: false })
    }
  }

  const handleRegenerateFrame = async (frameId: string) => {
    setNotice(null)
    setRegeneratingFrameId(frameId)
    try {
      await api.post(`/api/vf/projects/${encodeURIComponent(project.id)}/storyboard/frames/${encodeURIComponent(frameId)}/regenerate`)
      setNotice({ text: `Frame regeneration triggered.`, ok: true })
    } catch (err: any) {
      setNotice({ text: err.message || 'Failed to regenerate frame', ok: false })
    } finally {
      setRegeneratingFrameId(null)
    }
  }

  const handleUploadClick = (frameId: string) => {
    setPendingUploadFrameId(frameId)
    fileInputRef.current?.click()
  }

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file || !pendingUploadFrameId) return
    e.target.value = ''
    setNotice(null)
    setUploadingFrameId(pendingUploadFrameId)
    try {
      const formData = new FormData()
      formData.append('file', file)
      await api.post(
        `/api/vf/projects/${encodeURIComponent(project.id)}/storyboard/frames/${encodeURIComponent(pendingUploadFrameId)}/upload`,
        formData
      )
      setNotice({ text: 'Frame image uploaded.', ok: true })
    } catch (err: any) {
      setNotice({ text: err.message || 'Failed to upload frame image', ok: false })
    } finally {
      setUploadingFrameId(null)
      setPendingUploadFrameId(null)
    }
  }

  const handleBulkRegenerate = async () => {
    setNotice(null)
    setBulkRegenerating(true)
    try {
      const res = await generateMutation.mutateAsync(project.id)
      const jobId = res?.jobs?.[0]?.job_id
      if (jobId) onTrackJob(jobId)
      setNotice({ text: 'Bulk regeneration triggered for all frames.', ok: true })
    } catch (err: any) {
      setNotice({ text: err.message || 'Failed to regenerate all frames', ok: false })
    } finally {
      setBulkRegenerating(false)
    }
  }

  const getFrameStatusVariant = (status: string): BadgeVariant => {
    switch (status) {
      case 'completed':
        return 'success'
      case 'generating':
        return 'running'
      case 'failed':
        return 'error'
      default:
        return 'neutral'
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      {!isSceneApproved && <DependencyNotice projectId={project.id} currentStage="storyboard" />}

      {/* Control Banner */}
      <section
        style={{
          padding: '16px 20px',
          backgroundColor: 'var(--bg-panel)',
          border: '1px solid var(--border-default)',
          borderRadius: 'var(--radius-lg)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: '12px',
          opacity: !isSceneApproved ? 0.6 : 1,
          pointerEvents: !isSceneApproved ? 'none' : 'auto',
        }}
      >
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <h3 style={{ fontSize: '15px', fontWeight: 600, color: 'var(--text-primary)' }}>
              Storyboard Keyframes ({frames.length} Beats)
            </h3>
            <Badge variant={frames.length > 0 ? 'active' : 'neutral'} size="md">
              9:16 Vertical Composition
            </Badge>
          </div>
          <p style={{ fontSize: '12px', color: 'var(--text-secondary)', marginTop: '2px' }}>
            High-fidelity reference visual keyframes preserving exact product identity for video diffusion generation.
          </p>
        </div>

        <Button
          variant="primary"
          size="md"
          icon={<Sparkles size={14} />}
          disabled={!isSceneApproved || generateMutation.isPending}
          loading={generateMutation.isPending}
          onClick={handleGenerateFrames}
          title="Generate image prompts and keyframe assets"
        >
          {frames.length > 0 ? 'Regenerate Keyframes' : 'Generate Keyframes'}
        </Button>
      </section>

      {/* Bulk Actions */}
      {frames.length > 0 && (
        <div className="bulk-actions" style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <Button
            variant="outline"
            size="sm"
            icon={<RefreshCw size={13} className={bulkRegenerating ? 'animate-spin' : ''} />}
            disabled={!isSceneApproved || bulkRegenerating || generateMutation.isPending}
            loading={bulkRegenerating || generateMutation.isPending}
            onClick={handleBulkRegenerate}
          >
            Regenerate All
          </Button>
          <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
            {frames.filter(f => f.generation_status === 'completed').length} / {frames.length} completed
          </span>
        </div>
      )}

      {/* Hidden file input for frame uploads */}
      <input
        ref={fileInputRef}
        type="file"
        accept="image/*"
        style={{ display: 'none' }}
        onChange={handleFileChange}
      />

      {notice && (
        <div
          style={{
            padding: '10px 14px',
            backgroundColor: notice.ok ? 'var(--status-success-bg)' : 'var(--status-error-bg)',
            border: `1px solid ${notice.ok ? 'var(--status-success-border)' : 'var(--status-error-border)'}`,
            borderRadius: 'var(--radius-sm)',
            fontSize: '12px',
            color: notice.ok ? 'var(--status-success)' : 'var(--status-error)',
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
          }}
        >
          {notice.ok ? <CheckCircle2 size={14} /> : <AlertCircle size={14} />}
          <span>{notice.text}</span>
        </div>
      )}

      {/* Keyframe Grid */}
      {frames.length > 0 ? (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))',
            gap: '18px',
          }}
        >
          {frames.map((frame) => {
            const assetId = frame.generated_asset_id || productAssets[0]?.asset_id
            return (
              <div
                key={frame.frame_id}
                style={{
                  backgroundColor: 'var(--bg-panel)',
                  border: '1px solid var(--border-default)',
                  borderRadius: 'var(--radius-lg)',
                  overflow: 'hidden',
                  display: 'flex',
                  flexDirection: 'column',
                  transition: 'border-color 0.15s ease',
                }}
                className="storyboard-card"
              >
                {/* Thumbnail Container */}
                <div style={{ position: 'relative' }}>
                  <AssetThumbnail
                    assetId={assetId}
                    aspectRatio="9:16"
                    onInspect={onInspectAsset}
                  />

                  {/* Scene Number Badge Overlay */}
                  <div
                    style={{
                      position: 'absolute',
                      top: '8px',
                      left: '8px',
                      backgroundColor: 'rgba(10, 12, 16, 0.85)',
                      padding: '2px 8px',
                      borderRadius: 'var(--radius-sm)',
                      fontSize: '11px',
                      fontWeight: 600,
                      color: 'var(--text-primary)',
                      fontFamily: 'var(--font-mono)',
                      backdropFilter: 'blur(4px)',
                      border: '1px solid var(--border-subtle)',
                    }}
                  >
                    Beat #{frame.order}
                  </div>

                  {/* Status Overlay */}
                  <div
                    style={{
                      position: 'absolute',
                      top: '8px',
                      right: '8px',
                    }}
                  >
                    <Badge variant={getFrameStatusVariant(frame.generation_status)} size="sm">
                      {frame.generation_status}
                    </Badge>
                  </div>
                </div>

                {/* Card Information */}
                <div
                  style={{
                    padding: '14px',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '8px',
                    flex: 1,
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <strong style={{ fontSize: '13px', color: 'var(--text-primary)' }}>
                      {frame.label}
                    </strong>
                    <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                      {frame.purpose}
                    </span>
                  </div>

                  <p
                    style={{
                      fontSize: '12px',
                      color: 'var(--text-secondary)',
                      lineHeight: 1.35,
                      display: '-webkit-box',
                      WebkitLineClamp: 2,
                      WebkitBoxOrient: 'vertical',
                      overflow: 'hidden',
                    }}
                  >
                    {frame.visual_state}
                  </p>

                    {/* Action to open prompt in inspector */}
                    <div
                      style={{
                        marginTop: 'auto',
                        paddingTop: '8px',
                        borderTop: '1px solid var(--border-subtle)',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                      }}
                    >
                      <button
                        onClick={() => onSelectFrameForInspector(frame)}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: '4px',
                          fontSize: '11px',
                          color: 'var(--accent-primary)',
                          background: 'none',
                          border: 'none',
                          cursor: 'pointer',
                          padding: '2px 0',
                        }}
                        title="Inspect prompt & identity constraints"
                      >
                        <Sliders size={12} />
                        <span>Inspect</span>
                      </button>

                      {assetId && (
                        <button
                          onClick={() => onInspectAsset(assetId)}
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: '4px',
                            fontSize: '11px',
                            color: 'var(--text-muted)',
                            background: 'none',
                            border: 'none',
                            cursor: 'pointer',
                          }}
                        >
                          <Eye size={12} />
                          <span>Preview</span>
                        </button>
                      )}
                    </div>

                    {/* Per-Frame Actions */}
                    <div style={{ display: 'flex', gap: '6px', marginTop: '6px' }}>
                      <button
                        onClick={() => handleRegenerateFrame(frame.frame_id)}
                        disabled={regeneratingFrameId === frame.frame_id}
                        style={{
                          display: 'flex', alignItems: 'center', gap: '3px', fontSize: '10px',
                          color: 'var(--accent-timeline)', background: 'none', border: 'none',
                          cursor: regeneratingFrameId === frame.frame_id ? 'not-allowed' : 'pointer',
                          opacity: regeneratingFrameId === frame.frame_id ? 0.6 : 1,
                        }}
                      >
                        {regeneratingFrameId === frame.frame_id ? <Loader2 size={10} className="animate-spin" /> : <RefreshCw size={10} />}
                        Regenerate
                      </button>
                      <button
                        onClick={() => handleUploadClick(frame.frame_id)}
                        disabled={uploadingFrameId === frame.frame_id}
                        style={{
                          display: 'flex', alignItems: 'center', gap: '3px', fontSize: '10px',
                          color: 'var(--accent-primary)', background: 'none', border: 'none',
                          cursor: uploadingFrameId === frame.frame_id ? 'not-allowed' : 'pointer',
                          opacity: uploadingFrameId === frame.frame_id ? 0.6 : 1,
                        }}
                      >
                        {uploadingFrameId === frame.frame_id ? <Loader2 size={10} className="animate-spin" /> : <Upload size={10} />}
                        Upload
                      </button>
                    </div>
                </div>
              </div>
            )
          })}
        </div>
      ) : (
        <EmptyState
          icon={ImageIcon}
          title="No Storyboard Keyframes Yet"
          description="Storyboard keyframes establish the exact visual composition and product geometry for video generation."
          actionLabel={isSceneApproved ? 'Generate Keyframe Prompts' : undefined}
          onAction={handleGenerateFrames}
        />
      )}
    </div>
  )
}
