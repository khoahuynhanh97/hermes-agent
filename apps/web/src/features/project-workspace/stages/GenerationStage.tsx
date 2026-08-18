import React from 'react'
import {
  Film,
  Play,
  Sliders,
} from 'lucide-react'
import { VideoFactoryProject, GeneratedScene } from '../../../types/videoFactory'
import { Badge, BadgeVariant } from '../../../components/common/Badge'
import { AssetThumbnail } from '../../../components/common/AssetThumbnail'
import { EmptyState } from '../../../components/common/EmptyState'
import { DependencyNotice } from '../../../components/pipeline/DependencyNotice'

interface GenerationStageProps {
  project: VideoFactoryProject
  onInspectAsset: (assetId: string) => void
  onSelectSceneForInspector: (scene: GeneratedScene) => void
}

export const GenerationStage: React.FC<GenerationStageProps> = ({
  project,
  onInspectAsset,
  onSelectSceneForInspector,
}) => {
  const storyboardFrames = project.storyboard?.frames || []
  const generatedScenes = project.generated_scenes || []
  const isStoryboardReady = storyboardFrames.length > 0

  const getSceneStatusVariant = (status: string): BadgeVariant => {
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

  // Derive provenance label strictly from explicit metadata (e.g. provider or review notes)
  const deriveProvenanceLabel = (scene?: GeneratedScene): string | null => {
    if (!scene) return null
    if (scene.review_notes && scene.review_notes.trim().length > 0) {
      return scene.review_notes.trim()
    }
    const provider = scene.video_prompt?.provider_options?.provider
    if (provider && typeof provider === 'string') {
      return String(provider).toUpperCase()
    }
    return null
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      {!isStoryboardReady && <DependencyNotice projectId={project.id} currentStage="generation" />}

      {/* Header Banner */}
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
          opacity: !isStoryboardReady ? 0.6 : 1,
          pointerEvents: !isStoryboardReady ? 'none' : 'auto',
        }}
      >
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <h3 style={{ fontSize: '15px', fontWeight: 600, color: 'var(--text-primary)' }}>
              Scene Video Generation ({generatedScenes.length || storyboardFrames.length} Scenes)
            </h3>
            <Badge variant={generatedScenes.length > 0 ? 'success' : 'neutral'} size="md">
              9:16 Video Clips
            </Badge>
          </div>
          <p style={{ fontSize: '12px', color: 'var(--text-secondary)', marginTop: '2px' }}>
            Video synthesis generated per scene beat according to storyboard frame visual states.
          </p>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Badge variant="active" size="md">
            {generatedScenes.filter((s) => s.generated_asset_id).length} / {storyboardFrames.length || 4} Clips Ready
          </Badge>
        </div>
      </section>

      {/* Scenes Grid */}
      {storyboardFrames.length > 0 ? (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '18px' }}>
          {storyboardFrames.map((frame, idx) => {
            const genScene = generatedScenes.find((s) => s.scene_id === frame.scene_id || s.scene_id === `scene_${frame.order}`)
            const videoAssetId = genScene?.generated_asset_id
            const provenanceLabel = deriveProvenanceLabel(genScene)
            const duration = genScene?.video_prompt?.duration_seconds || (idx === 0 ? 6 : 8)

            return (
              <div
                key={frame.frame_id || idx}
                style={{
                  backgroundColor: 'var(--bg-panel)',
                  border: '1px solid var(--border-default)',
                  borderRadius: 'var(--radius-lg)',
                  overflow: 'hidden',
                  display: 'flex',
                  flexDirection: 'column',
                }}
                className="generation-scene-card"
              >
                {/* Media Preview Area */}
                <div style={{ position: 'relative' }}>
                  {videoAssetId ? (
                    <AssetThumbnail
                      assetId={videoAssetId}
                      aspectRatio="9:16"
                      onInspect={onInspectAsset}
                    />
                  ) : (
                    <AssetThumbnail
                      assetId={frame.generated_asset_id}
                      aspectRatio="9:16"
                      roleLabel={frame.generated_asset_id ? 'Keyframe' : undefined}
                      onInspect={onInspectAsset}
                    />
                  )}

                  {/* Top Badges */}
                  <div
                    style={{
                      position: 'absolute',
                      top: '8px',
                      left: '8px',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '6px',
                    }}
                  >
                    <span
                      style={{
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
                      Scene #{frame.order}
                    </span>

                    {provenanceLabel && (
                      <span
                        style={{
                          backgroundColor: 'rgba(6, 182, 212, 0.85)',
                          padding: '2px 6px',
                          borderRadius: 'var(--radius-sm)',
                          fontSize: '10px',
                          fontWeight: 600,
                          color: '#000000',
                        }}
                      >
                        {provenanceLabel}
                      </span>
                    )}
                  </div>

                  {/* Status Overlay */}
                  <div style={{ position: 'absolute', top: '8px', right: '8px' }}>
                    <Badge
                      variant={getSceneStatusVariant(genScene?.generation_status || (videoAssetId ? 'completed' : 'not_started'))}
                      size="sm"
                    >
                      {genScene?.generation_status || (videoAssetId ? 'completed' : 'pending')}
                    </Badge>
                  </div>
                </div>

                {/* Information Area */}
                <div style={{ padding: '14px', display: 'flex', flexDirection: 'column', gap: '8px', flex: 1 }}>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <strong style={{ fontSize: '13px', color: 'var(--text-primary)' }}>
                      {frame.label}
                    </strong>
                    <Badge variant="timeline" size="sm">
                      {duration}s
                    </Badge>
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
                    {genScene?.video_prompt?.subject_action || frame.subject_action || frame.visual_state}
                  </p>

                  {/* Footer Actions */}
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
                    {genScene && (
                      <button
                        onClick={() => onSelectSceneForInspector(genScene)}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: '4px',
                          fontSize: '11px',
                          color: 'var(--accent-primary)',
                          background: 'none',
                          border: 'none',
                          cursor: 'pointer',
                        }}
                      >
                        <Sliders size={12} />
                        <span>Inspect Video Prompt</span>
                      </button>
                    )}

                    {videoAssetId && (
                      <button
                        onClick={() => onInspectAsset(videoAssetId)}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: '4px',
                          fontSize: '11px',
                          color: 'var(--text-primary)',
                          background: 'none',
                          border: 'none',
                          cursor: 'pointer',
                        }}
                      >
                        <Play size={12} color="var(--accent-primary)" />
                        <span>Play Clip</span>
                      </button>
                    )}
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      ) : (
        <EmptyState
          icon={Film}
          title="No Scenes Generated"
          description="Generate Storyboard Keyframes in the previous step before initiating video generation for individual scene clips."
        />
      )}
    </div>
  )
}
