import React, { useState, useEffect } from 'react'
import {
  SlidersHorizontal,
  Mic,
  Music,
  Play,
  Film,
  Sparkles,
  CheckCircle2,
  AlertCircle,
  Clock,
  Volume2,
} from 'lucide-react'
import { VideoFactoryProject } from '../../../types/videoFactory'
import {
  useGenerateVoiceover,
  useMixAudio,
  useRenderTimeline,
  useABVariants,
} from '../../../hooks/useVideoFactory'
import { api } from '../../../lib/api'
import { Badge } from '../../../components/common/Badge'
import { Button } from '../../../components/common/Button'
import { AssetThumbnail } from '../../../components/common/AssetThumbnail'
import { DependencyNotice } from '../../../components/pipeline/DependencyNotice'
import { CaptionPreview, CaptionStyle, CaptionSize, CaptionPosition } from '../../../components/pipeline/CaptionPreview'
import { BGMMixer } from '../../../components/pipeline/BGMMixer'
import { formatAssetUrl } from '../../../utils/formatters'

interface TimelineStageProps {
  project: VideoFactoryProject
  onInspectAsset: (assetId: string) => void
  onTrackJob: (jobId: string) => void
}

export const TimelineStage: React.FC<TimelineStageProps> = ({
  project,
  onInspectAsset,
  onTrackJob,
}) => {
  const [voiceText, setVoiceText] = useState('')
  const [voiceStyle, setVoiceStyle] = useState('Clear Vietnamese product review, confident and natural pacing')
  const [voiceChoice, setVoiceChoice] = useState('Zephyr')
  const [voiceSpeed, setVoiceSpeed] = useState(1.0)
  const [notice, setNotice] = useState<{ text: string; ok: boolean } | null>(null)
  const [previewingVoice, setPreviewingVoice] = useState(false)

  // Caption state
  const [captionsEnabled, setCaptionsEnabled] = useState(false)
  const [captionStyle, setCaptionStyle] = useState<CaptionStyle>('tiktok-yellow')
  const [captionSize, setCaptionSize] = useState<CaptionSize>('medium')
  const [captionPosition, setCaptionPosition] = useState<CaptionPosition>('bottom-center')

  // Timeline playback for caption preview
  const [activeCaptionWord, setActiveCaptionWord] = useState(0)
  const sampleWords = 'Đánh giá tai nghe thiết kế công thái học cao cấp thời lượng pin ấn tượng chất âm vượt trội'.split(' ')

  const ttsMutation = useGenerateVoiceover()
  const mixMutation = useMixAudio()
  const renderMutation = useRenderTimeline()
  const { data: abVariantsData } = useABVariants(project.id)
  const [activeVariantTab, setActiveVariantTab] = useState<string>('main')

  const scenes = project.scene_plan?.scenes || []
  const generatedScenes = project.generated_scenes || []
  const draftAssetId = project.draft_video_asset_id
  const hasClips = generatedScenes.some((s) => s.generated_asset_id) || Boolean(draftAssetId)

  useEffect(() => {
    if (!voiceText && project.creative_brief) {
      setVoiceText(
        `Đánh giá tai nghe ${project.resource_pack?.product_identity_description || 'sản phẩm'}. ` +
        `Thiết kế công thái học cao cấp, thời lượng pin ấn tượng và chất âm vượt trội.`
      )
    }
  }, [project.id, project.creative_brief, project.resource_pack])

  // Auto-cycle caption words when captions enabled
  useEffect(() => {
    if (!captionsEnabled) return
    const interval = setInterval(() => {
      setActiveCaptionWord((prev) => (prev + 1) % sampleWords.length)
    }, 600)
    return () => clearInterval(interval)
  }, [captionsEnabled, sampleWords.length])

  const handleGenerateVoiceover = async () => {
    if (!voiceText.trim()) return
    setNotice(null)
    try {
      const res = await ttsMutation.mutateAsync({
        projectId: project.id,
        text: voiceText.trim(),
        voice: voiceChoice,
        stylePrompt: voiceStyle,
      })
      if (res?.job_id) onTrackJob(res.job_id)
      setNotice({ text: 'Voiceover generation triggered.', ok: true })
    } catch (err: any) {
      setNotice({ text: err.message || 'Failed to generate voiceover', ok: false })
    }
  }

  const handlePreviewVoice = async () => {
    setPreviewingVoice(true)
    try {
      await api.post('/api/tts/preview', { text: voiceText.slice(0, 100) || 'Hello', voice: voiceChoice })
      setTimeout(() => setPreviewingVoice(false), 3000)
    } catch {
      setPreviewingVoice(false)
    }
  }

  const handleRenderTimeline = async () => {
    setNotice(null)
    try {
      const res = await renderMutation.mutateAsync(project.id)
      if (res?.job_id) onTrackJob(res.job_id)
      setNotice({ text: 'Draft timeline rendering initiated.', ok: true })
    } catch (err: any) {
      setNotice({ text: err.message || 'Failed to render timeline', ok: false })
    }
  }

  const totalDuration = scenes.reduce((acc, s) => acc + (s.duration_seconds || 0), 30)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      {!hasClips && <DependencyNotice projectId={project.id} currentStage="timeline" />}

      {/* Draft Player & Actions Container */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(340px, 1fr))', gap: '20px' }}>
        {/* Left: Draft Video Player Showcase */}
        <section
          style={{
            padding: '20px',
            backgroundColor: 'var(--bg-panel)',
            border: '1px solid var(--border-default)',
            borderRadius: 'var(--radius-lg)',
            display: 'flex',
            flexDirection: 'column',
            gap: '14px',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <h3 style={{ fontSize: '15px', fontWeight: 600, color: 'var(--text-primary)' }}>
              Draft Video Preview
            </h3>
            <Badge variant={draftAssetId ? 'success' : 'neutral'} dot size="sm">
              {draftAssetId ? 'Draft Rendered' : 'Draft Pending'}
            </Badge>
          </div>

          <div
            style={{
              backgroundColor: 'var(--bg-app)',
              borderRadius: 'var(--radius-md)',
              border: '1px solid var(--border-default)',
              minHeight: '280px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              overflow: 'hidden',
            }}
          >
            {draftAssetId ? (
              <video
                src={formatAssetUrl(draftAssetId)}
                controls
                playsInline
                style={{ width: '100%', maxHeight: '380px', borderRadius: 'var(--radius-md)' }}
              />
            ) : (
              <div
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  color: 'var(--text-muted)',
                  gap: '8px',
                  padding: '24px',
                  textAlign: 'center',
                }}
              >
                <Film size={28} strokeWidth={1.5} />
                <span style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
                  No draft video rendered yet.
                </span>
                <span style={{ fontSize: '11px' }}>
                  Click 'Render Draft Timeline' after configuring voiceover.
                </span>
              </div>
            )}
          </div>

          {/* Caption Preview */}
          {captionsEnabled && (
            <CaptionPreview
              words={sampleWords}
              activeWordIndex={activeCaptionWord}
              style={captionStyle}
              size={captionSize}
              position={captionPosition}
              isPlaying={!!draftAssetId}
            />
          )}

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
            <Button
              variant="timeline"
              size="md"
              icon={<Sparkles size={14} />}
              disabled={renderMutation.isPending || (!generatedScenes.length && !draftAssetId)}
              loading={renderMutation.isPending}
              onClick={handleRenderTimeline}
              title="Render all scene clips into draft composite"
            >
              {draftAssetId ? 'Re-render Timeline' : 'Render Draft Timeline'}
            </Button>
          </div>
        </section>

        {/* Right: Voiceover & TTS Track Configuration */}
        <section
          style={{
            padding: '20px',
            backgroundColor: 'var(--bg-panel)',
            border: '1px solid var(--border-default)',
            borderRadius: 'var(--radius-lg)',
            display: 'flex',
            flexDirection: 'column',
            gap: '14px',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Mic size={16} color="var(--accent-primary)" />
              <h3 style={{ fontSize: '15px', fontWeight: 600, color: 'var(--text-primary)' }}>
                Voiceover & Audio Synthesis (TTS)
              </h3>
            </div>
            <Badge variant="neutral" size="sm">
              Model: {voiceChoice}
            </Badge>
          </div>

          <div>
            <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '6px' }}>
              Voiceover Script *
            </label>
            <textarea
              rows={4}
              placeholder="Enter voiceover text to be spoken across the 30-second timeline..."
              value={voiceText}
              onChange={(e) => setVoiceText(e.target.value)}
              style={{ width: '100%', resize: 'vertical' }}
            />
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
            <div>
              <label style={{ display: 'block', fontSize: '11px', color: 'var(--text-muted)', marginBottom: '4px' }}>
                Voice Actor
              </label>
              <select value={voiceChoice} onChange={(e) => setVoiceChoice(e.target.value)} style={{ width: '100%' }}>
                <option value="Zephyr">Zephyr (Confident / Tech)</option>
                <option value="Puck">Puck (Energetic / Social)</option>
                <option value="Aoede">Aoede (Warm / Review)</option>
              </select>
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '11px', color: 'var(--text-muted)', marginBottom: '4px' }}>
                Pacing & Tone
              </label>
              <input
                type="text"
                value={voiceStyle}
                onChange={(e) => setVoiceStyle(e.target.value)}
                style={{ width: '100%' }}
              />
            </div>
          </div>

          {/* Voice Speed Selector */}
          <div className="voice-selector">
            <label style={{ display: 'block', fontSize: '11px', color: 'var(--text-muted)', marginBottom: '4px' }}>
              Voice Speed
            </label>
            <div style={{ display: 'flex', gap: '6px' }}>
              {[0.8, 1.0, 1.2].map((speed) => (
                <button
                  key={speed}
                  onClick={() => setVoiceSpeed(speed)}
                  style={{
                    padding: '4px 10px',
                    borderRadius: 'var(--radius-sm)',
                    fontSize: '11px',
                    border: `1px solid ${voiceSpeed === speed ? 'var(--accent-primary)' : 'var(--border-default)'}`,
                    backgroundColor: voiceSpeed === speed ? 'var(--status-active-bg)' : 'transparent',
                    color: voiceSpeed === speed ? 'var(--accent-primary)' : 'var(--text-muted)',
                    cursor: 'pointer',
                  }}
                >
                  {speed}x
                </button>
              ))}
            </div>
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px', marginTop: 'auto', paddingTop: '10px' }}>
            <Button
              variant="ghost"
              size="sm"
              icon={<Play size={13} />}
              disabled={!voiceText.trim() || previewingVoice}
              loading={previewingVoice}
              onClick={handlePreviewVoice}
            >
              Preview Voice
            </Button>
            <Button
              variant="secondary"
              size="md"
              icon={<Volume2 size={14} />}
              disabled={!voiceText.trim() || ttsMutation.isPending}
              loading={ttsMutation.isPending}
              onClick={handleGenerateVoiceover}
              title="Generate synthetic voice audio"
            >
              Generate Voiceover
            </Button>
          </div>
        </section>
      </div>

      {/* Caption & BGM Controls */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '20px' }}>
        {/* Caption Controls */}
        <section className="caption-controls" style={{
          padding: '20px',
          backgroundColor: 'var(--bg-panel)',
          border: '1px solid var(--border-default)',
          borderRadius: 'var(--radius-lg)',
          display: 'flex',
          flexDirection: 'column',
          gap: '12px',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <SlidersHorizontal size={14} color="var(--accent-primary)" />
              <span style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-primary)' }}>Captions</span>
            </div>
            <button
              onClick={() => setCaptionsEnabled(!captionsEnabled)}
              style={{
                padding: '3px 10px',
                borderRadius: 'var(--radius-sm)',
                fontSize: '11px',
                border: `1px solid ${captionsEnabled ? 'var(--status-success-border)' : 'var(--border-default)'}`,
                backgroundColor: captionsEnabled ? 'var(--status-success-bg)' : 'transparent',
                color: captionsEnabled ? 'var(--status-success)' : 'var(--text-muted)',
                cursor: 'pointer',
              }}
            >
              {captionsEnabled ? 'ON' : 'OFF'}
            </button>
          </div>

          {captionsEnabled && (
            <>
              <div>
                <label style={{ display: 'block', fontSize: '11px', color: 'var(--text-muted)', marginBottom: '4px' }}>Style</label>
                <select value={captionStyle} onChange={(e) => setCaptionStyle(e.target.value as CaptionStyle)} style={{ width: '100%' }}>
                  <option value="tiktok-yellow">TikTok Yellow</option>
                  <option value="clean-white">Clean White</option>
                  <option value="neon-green">Neon Green</option>
                </select>
              </div>
              <div>
                <label style={{ display: 'block', fontSize: '11px', color: 'var(--text-muted)', marginBottom: '4px' }}>Font Size</label>
                <select value={captionSize} onChange={(e) => setCaptionSize(e.target.value as CaptionSize)} style={{ width: '100%' }}>
                  <option value="small">Small</option>
                  <option value="medium">Medium</option>
                  <option value="large">Large</option>
                </select>
              </div>
              <div>
                <label style={{ display: 'block', fontSize: '11px', color: 'var(--text-muted)', marginBottom: '4px' }}>Position</label>
                <select value={captionPosition} onChange={(e) => setCaptionPosition(e.target.value as CaptionPosition)} style={{ width: '100%' }}>
                  <option value="bottom-center">Bottom Center</option>
                  <option value="top-center">Top Center</option>
                </select>
              </div>
            </>
          )}
        </section>

        {/* BGM Mixer */}
        <section style={{
          padding: '20px',
          backgroundColor: 'var(--bg-panel)',
          border: '1px solid var(--border-default)',
          borderRadius: 'var(--radius-lg)',
        }}>
          <BGMMixer project_id={project.id} />
        </section>
      </div>

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

      {/* A/B Variant Timeline Tabs */}
      {abVariantsData?.data?.variants && abVariantsData.data.variants.length > 0 && (
        <section
          style={{
            padding: '14px 20px',
            backgroundColor: 'var(--bg-panel)',
            border: '1px solid var(--border-default)',
            borderRadius: 'var(--radius-lg)',
            display: 'flex',
            flexDirection: 'column',
            gap: '10px',
          }}
        >
          <h4 style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-primary)' }}>
            Variant Timeline Comparison
          </h4>
          <div style={{ display: 'flex', gap: '4px' }}>
            <button
              onClick={() => setActiveVariantTab('main')}
              style={{
                padding: '6px 14px',
                borderRadius: 'var(--radius-sm)',
                fontSize: '11px',
                fontWeight: 600,
                border: `1px solid ${activeVariantTab === 'main' ? 'var(--accent-primary)' : 'var(--border-default)'}`,
                backgroundColor: activeVariantTab === 'main' ? 'var(--status-active-bg)' : 'transparent',
                color: activeVariantTab === 'main' ? 'var(--accent-primary)' : 'var(--text-muted)',
                cursor: 'pointer',
              }}
            >
              Main Timeline
            </button>
            {abVariantsData.data.variants.map((variant: any, idx: number) => (
              <button
                key={variant.variant_id}
                onClick={() => setActiveVariantTab(variant.variant_id)}
                style={{
                  padding: '6px 14px',
                  borderRadius: 'var(--radius-sm)',
                  fontSize: '11px',
                  fontWeight: 600,
                  border: `1px solid ${activeVariantTab === variant.variant_id ? 'var(--accent-primary)' : 'var(--border-default)'}`,
                  backgroundColor: activeVariantTab === variant.variant_id ? 'var(--status-active-bg)' : 'transparent',
                  color: activeVariantTab === variant.variant_id ? 'var(--accent-primary)' : 'var(--text-muted)',
                  cursor: 'pointer',
                }}
              >
                Variant {String.fromCharCode(65 + idx)}: {variant.variant_label}
              </button>
            ))}
          </div>
          {activeVariantTab !== 'main' && (() => {
            const activeVariant = abVariantsData.data.variants.find((v: any) => v.variant_id === activeVariantTab)
            if (!activeVariant?.scene_plan) return null
            const variantScenes = activeVariant.scene_plan.scenes || []
            const totalDur = variantScenes.reduce((acc: number, s: any) => acc + (s.duration_seconds || 0), 0)
            return (
              <div style={{ display: 'flex', height: '32px', gap: '2px', borderRadius: 'var(--radius-sm)', overflow: 'hidden' }}>
                {variantScenes.map((s: any, i: number) => {
                  const pct = ((s.duration_seconds || 6) / totalDur) * 100
                  return (
                    <div
                      key={s.scene_id}
                      style={{
                        flex: `0 0 ${pct}%`,
                        backgroundColor: i % 2 === 0 ? 'var(--bg-surface-active)' : 'var(--bg-surface)',
                        borderRight: '1px solid var(--border-default)',
                        padding: '4px 6px',
                        display: 'flex',
                        flexDirection: 'column',
                        justifyContent: 'center',
                        overflow: 'hidden',
                      }}
                    >
                      <span style={{ fontSize: '10px', fontWeight: 600, color: 'var(--text-primary)' }} className="truncate">
                        #{s.order} {s.title}
                      </span>
                      <span style={{ fontSize: '9px', color: 'var(--accent-timeline)', fontFamily: 'var(--font-mono)' }}>
                        {s.duration_seconds}s
                      </span>
                    </div>
                  )
                })}
              </div>
            )
          })()}
        </section>
      )}

      {/* Horizontal Multi-Track Timeline */}
      <section
        style={{
          padding: '18px 20px',
          backgroundColor: 'var(--bg-panel)',
          border: '1px solid var(--border-default)',
          borderRadius: 'var(--radius-lg)',
          display: 'flex',
          flexDirection: 'column',
          gap: '14px',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <h4 style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-primary)' }}>
            Horizontal Timeline Track (30 Seconds)
          </h4>
          <span style={{ fontSize: '11px', fontFamily: 'var(--font-mono)', color: 'var(--accent-timeline)' }}>
            00:00 - 00:30
          </span>
        </div>

        {/* Video Track */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
          <span style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
            Video Track (9:16 Composite)
          </span>
          <div
            style={{
              display: 'flex',
              height: '44px',
              backgroundColor: 'var(--bg-app)',
              borderRadius: 'var(--radius-md)',
              border: '1px solid var(--border-default)',
              overflow: 'hidden',
              gap: '2px',
            }}
          >
            {(scenes.length > 0 ? scenes : [
              { order: 1, title: 'Hook', duration_seconds: 6 },
              { order: 2, title: 'Use case', duration_seconds: 8 },
              { order: 3, title: 'Highlights', duration_seconds: 8 },
              { order: 4, title: 'CTA', duration_seconds: 8 },
            ]).map((s, idx) => {
              const pct = ((s.duration_seconds || 6) / totalDuration) * 100
              return (
                <div
                  key={idx}
                  style={{
                    flex: `0 0 ${pct}%`,
                    backgroundColor: idx % 2 === 0 ? 'var(--bg-surface-active)' : 'var(--bg-surface)',
                    borderRight: '1px solid var(--border-default)',
                    padding: '6px 8px',
                    display: 'flex',
                    flexDirection: 'column',
                    justifyContent: 'center',
                    overflow: 'hidden',
                  }}
                  title={`Scene ${s.order}: ${s.title} (${s.duration_seconds}s)`}
                >
                  <span style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-primary)' }} className="truncate">
                    #{s.order} {s.title}
                  </span>
                  <span style={{ fontSize: '10px', color: 'var(--accent-timeline)', fontFamily: 'var(--font-mono)' }}>
                    {s.duration_seconds}s
                  </span>
                </div>
              )
            })}
          </div>
        </div>

        {/* Audio Waveform Track */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
          <span style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
            Audio Waveform
          </span>
          <div style={{
            height: '24px',
            backgroundColor: 'var(--bg-app)',
            borderRadius: 'var(--radius-md)',
            border: '1px solid var(--border-default)',
            display: 'flex',
            alignItems: 'center',
            padding: '0 8px',
            gap: '2px',
            overflow: 'hidden',
          }}>
            {Array.from({ length: 40 }).map((_, i) => (
              <div
                key={i}
                style={{
                  width: '3px',
                  height: `${8 + Math.random() * 14}px`,
                  backgroundColor: 'var(--accent-primary)',
                  borderRadius: '1px',
                  opacity: 0.6,
                  flexShrink: 0,
                }}
              />
            ))}
          </div>
        </div>

        {/* Audio & Dialogue Track */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
          <span style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
            Audio & Dialogue Track
          </span>
          <div
            style={{
              height: '32px',
              backgroundColor: 'var(--bg-app)',
              borderRadius: 'var(--radius-md)',
              border: '1px solid var(--border-default)',
              display: 'flex',
              alignItems: 'center',
              padding: '0 12px',
              gap: '8px',
            }}
          >
            <Volume2 size={13} color="var(--accent-primary)" />
            <span style={{ fontSize: '11px', color: 'var(--text-secondary)' }} className="truncate">
              {voiceText || 'Voiceover & Background Audio Track (30s Normalized)'}
            </span>
          </div>
        </div>

        {/* Caption Markers Track */}
        {captionsEnabled && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            <span style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
              Caption Markers
            </span>
            <div style={{
              height: '20px',
              backgroundColor: 'var(--bg-app)',
              borderRadius: 'var(--radius-md)',
              border: '1px solid var(--border-default)',
              display: 'flex',
              alignItems: 'center',
              padding: '0 8px',
              gap: '4px',
            }}>
              {sampleWords.slice(0, 10).map((word, i) => (
                <div
                  key={i}
                  style={{
                    padding: '1px 6px',
                    borderRadius: '2px',
                    fontSize: '9px',
                    backgroundColor: i === activeCaptionWord ? 'var(--accent-primary)' : 'var(--bg-surface)',
                    color: i === activeCaptionWord ? 'var(--text-inverse)' : 'var(--text-muted)',
                    whiteSpace: 'nowrap',
                    transition: 'all 0.15s ease',
                  }}
                >
                  {word}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Duration per scene */}
        <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
          {(scenes.length > 0 ? scenes : [
            { order: 1, title: 'Hook', duration_seconds: 6 },
            { order: 2, title: 'Use case', duration_seconds: 8 },
            { order: 3, title: 'Highlights', duration_seconds: 8 },
            { order: 4, title: 'CTA', duration_seconds: 8 },
          ]).map((s, idx) => (
            <div key={idx} style={{
              display: 'flex', alignItems: 'center', gap: '4px',
              fontSize: '10px', color: 'var(--text-muted)',
            }}>
              <Clock size={10} />
              <span>#{s.order}: {s.duration_seconds}s</span>
            </div>
          ))}
        </div>
      </section>
    </div>
  )
}
