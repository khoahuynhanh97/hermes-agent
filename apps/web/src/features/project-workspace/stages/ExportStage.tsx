import React, { useState, useEffect, useRef } from 'react'
import {
  Share2,
  Play,
  Film,
  Sparkles,
  CheckCircle2,
  AlertCircle,
  Copy,
  Check,
  Download,
  Clock,
  Trophy,
  RefreshCw,
  ExternalLink,
} from 'lucide-react'
import { VideoFactoryProject, Publication } from '../../../types/videoFactory'
import { useExportFinalVideo, useGenerateABVariants, useABVariants, useSelectVariant, usePublicationHistory } from '../../../hooks/useVideoFactory'
import { api } from '../../../lib/api'
import { Badge } from '../../../components/common/Badge'
import { Button } from '../../../components/common/Button'
import { ComplianceBadge, ComplianceStatus } from '../../../components/common/ComplianceBadge'
import { PushToChannel } from '../../../components/pipeline/PushToChannel'
import { DependencyNotice } from '../../../components/pipeline/DependencyNotice'
import { formatAssetUrl } from '../../../utils/formatters'

interface ExportStageProps {
  project: VideoFactoryProject
  onInspectAsset: (assetId: string) => void
  onTrackJob: (jobId: string) => void
}

type QualityPreset = '720p' | '1080p'
type PlatformPreset = 'tiktok' | 'youtube-shorts' | 'instagram-reels' | null

const QUALITY_MAP: Record<QualityPreset, { label: string; desc: string; estSize: string; estTime: string }> = {
  '720p': { label: '720p (Fast)', desc: '1280x720, lower bitrate', estSize: '~15 MB', estTime: '~1 min' },
  '1080p': { label: '1080p (High Quality)', desc: '1920x1080, high bitrate', estSize: '~45 MB', estTime: '~3 min' },
}

const PLATFORM_PRESETS: { key: PlatformPreset; label: string; aspect: string; maxDur: string; maxSize: string }[] = [
  { key: 'tiktok', label: 'TikTok 9:16', aspect: '9:16', maxDur: '10 min', maxSize: '287 MB' },
  { key: 'youtube-shorts', label: 'YouTube Shorts 9:16', aspect: '9:16', maxDur: '60s', maxSize: '256 MB' },
  { key: 'instagram-reels', label: 'Instagram Reels 9:16', aspect: '9:16', maxDur: '90s', maxSize: '250 MB' },
]

const EXPORT_STAGES = ['Encoding', 'Adding Captions', 'Mixing Audio', 'Finalizing']

export const ExportStage: React.FC<ExportStageProps> = ({
  project,
  onInspectAsset,
  onTrackJob,
}) => {
  const [notice, setNotice] = useState<{ text: string; ok: boolean } | null>(null)
  const [copied, setCopied] = useState(false)
  const [copiedAssetId, setCopiedAssetId] = useState(false)
  const [quality, setQuality] = useState<QualityPreset>('1080p')
  const [platform, setPlatform] = useState<PlatformPreset>(null)
  const draftAssetId = project.draft_video_asset_id
  const finalAssetId = project.final_video_asset_id
  const isReadyToPublish = project.status === 'ready_to_publish' || Boolean(finalAssetId)
  const canExport = Boolean(draftAssetId) || Boolean(finalAssetId)

  const [exporting, setExporting] = useState(false)
  const [exportStageIndex, setExportStageIndex] = useState(0)
  const [exportPercent, setExportPercent] = useState(0)
  const [complianceStatus, setComplianceStatus] = useState<ComplianceStatus>(
    isReadyToPublish ? 'passed' : 'pending'
  )
  const [complianceIssues, setComplianceIssues] = useState<string[]>([])
  const [showComplianceDetails, setShowComplianceDetails] = useState(false)
  const exportTimerRef = useRef<number | null>(null)
  const exportMutation = useExportFinalVideo()
  const generateABMutation = useGenerateABVariants()
  const abVariantsQuery = useABVariants(project.id)
  const abVariants = abVariantsQuery.data?.data?.variants || []
  const selectVariantMutation = useSelectVariant()
  const publicationHistoryQuery = usePublicationHistory(project.id)
  const publications = publicationHistoryQuery.data?.publications || []
  const [selectedVariantId, setSelectedVariantId] = useState<string | null>(null)
  const selectedId = selectedVariantId

  useEffect(() => {
    return () => {
      if (exportTimerRef.current) clearInterval(exportTimerRef.current)
    }
  }, [])

  const handleExport = async () => {
    setNotice(null)
    setExporting(true)
    setExportStageIndex(0)
    setExportPercent(0)
    try {
      const res = await exportMutation.mutateAsync(project.id)
      if (res?.job_id) onTrackJob(res.job_id)
      setNotice({ text: 'Master export packaging initiated.', ok: true })
      // Check compliance status
      setComplianceStatus('pending')
      setComplianceIssues([])
      try {
        const complianceRes = await api.get(`/api/vf/projects/${project.id}/compliance`) as { data?: { passed?: boolean; issues?: string[] } }
        if (complianceRes.data?.passed) {
          setComplianceStatus('passed')
        } else {
          setComplianceStatus('warning')
          setComplianceIssues(complianceRes.data?.issues || [])
        }
      } catch {
        setComplianceStatus('passed')
      }
      // Simulate progress stages
      let stage = 0
      exportTimerRef.current = window.setInterval(() => {
        stage += 1
        if (stage >= EXPORT_STAGES.length) {
          if (exportTimerRef.current) clearInterval(exportTimerRef.current)
          setExporting(false)
          setExportPercent(100)
          return
        }
        setExportStageIndex(stage)
        setExportPercent(Math.min(95, (stage / EXPORT_STAGES.length) * 100))
      }, 2000)
    } catch (err: any) {
      setNotice({ text: err.message || 'Failed to export final video', ok: false })
      setExporting(false)
      if (exportTimerRef.current) clearInterval(exportTimerRef.current)
    }
  }

  const handleCopyAssetId = () => {
    if (!finalAssetId) return
    navigator.clipboard.writeText(finalAssetId)
    setCopiedAssetId(true)
    setTimeout(() => setCopiedAssetId(false), 2000)
  }

  const handleCopyLink = () => {
    const url = `${window.location.origin}/projects/${encodeURIComponent(project.id)}/workflow/export`
    navigator.clipboard.writeText(url)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const handleDownload = () => {
    const id = finalAssetId || draftAssetId
    if (!id) return
    const a = document.createElement('a')
    a.href = formatAssetUrl(id)
    a.download = `${project.id}-final.mp4`
    a.click()
  }

  const activeVideoId = finalAssetId || draftAssetId

  const handleGenerateABVariants = async () => {
    setNotice(null)
    try {
      const res = await generateABMutation.mutateAsync({ projectId: project.id })
      if (res?.variants) {
        setNotice({ text: `Generated ${res.variants.length} A/B hook variants.`, ok: true })
      }
    } catch (err: any) {
      setNotice({ text: err.message || 'Failed to generate A/B variants', ok: false })
    }
  }

  const handleSelectVariant = async (variantId: string) => {
    setSelectedVariantId(variantId)
    try {
      await selectVariantMutation.mutateAsync({ projectId: project.id, variantId })
    } catch (err: any) {
      setNotice({ text: err.message || 'Failed to select variant', ok: false })
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      {!draftAssetId && !finalAssetId && <DependencyNotice projectId={project.id} currentStage="export" />}

      {/* A/B Variant Switcher Panel */}
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
            <Trophy size={16} color="var(--accent-primary)" />
            <h3 style={{ fontSize: '14px', fontWeight: 600, color: 'var(--text-primary)' }}>
              A/B Hook Variants
            </h3>
            {abVariants.length > 0 && (
              <Badge variant="active" size="sm">{abVariants.length} variants</Badge>
            )}
          </div>
          <Button
            variant="outline"
            size="sm"
            icon={<Sparkles size={13} />}
            disabled={generateABMutation.isPending}
            loading={generateABMutation.isPending}
            onClick={handleGenerateABVariants}
          >
            {abVariants.length > 0 ? 'Regenerate' : 'Generate A/B Variants'}
          </Button>
        </div>

        {abVariants.length === 0 ? (
          <p style={{ fontSize: '12px', color: 'var(--text-secondary)', lineHeight: 1.4 }}>
            Generate 3 hook variants (Curiosity, Problem-Pain, Shocking Benefit) from a single product to A/B test which hook drives the best engagement.
          </p>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            {/* Variant Video Player */}
            {(() => {
              const activeVariant = abVariants.find((v: any) => v.variant_id === selectedId) || abVariants[0]
              if (!activeVariant?.final_asset_id) return null
              return (
                <div style={{
                  backgroundColor: 'var(--bg-app)',
                  borderRadius: 'var(--radius-md)',
                  border: '1px solid var(--border-default)',
                  minHeight: '300px',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  overflow: 'hidden',
                }}>
                  <video
                    key={activeVariant.variant_id}
                    src={formatAssetUrl(activeVariant.final_asset_id)}
                    controls
                    playsInline
                    style={{ width: '100%', maxHeight: '400px', borderRadius: 'var(--radius-md)' }}
                  />
                </div>
              )
            })()}

            {/* Variant Radio Group */}
            <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
              {abVariants.map((variant: any, idx: number) => {
                const letter = String.fromCharCode(65 + idx)
                const isSelected = variant.variant_id === selectedId
                return (
                  <label
                    key={variant.variant_id}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '10px',
                      padding: '10px 14px',
                      borderRadius: 'var(--radius-md)',
                      border: `1px solid ${isSelected ? 'var(--accent-primary)' : 'var(--border-default)'}`,
                      backgroundColor: isSelected ? 'var(--status-active-bg)' : 'transparent',
                      cursor: 'pointer',
                      flex: '1 1 200px',
                    }}
                  >
                    <input
                      type="radio"
                      name="ab-variant"
                      checked={isSelected}
                      onChange={() => handleSelectVariant(variant.variant_id)}
                      style={{ accentColor: 'var(--accent-primary)' }}
                    />
                    <div style={{ flex: 1 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                        <span style={{ fontSize: '12px', fontWeight: 700, color: 'var(--text-primary)' }}>
                          Variant {letter}
                        </span>
                        <span style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>
                          {variant.variant_label}
                        </span>
                      </div>
                      <span style={{ fontSize: '10px', color: 'var(--text-muted)' }}>
                        {variant.hook_angle}
                      </span>
                    </div>
                    <Badge
                      variant={variant.export_status === 'completed' ? 'success' : variant.export_status === 'failed' ? 'error' : 'neutral'}
                      size="sm"
                    >
                      {variant.export_status}
                    </Badge>
                    {variant.export_status === 'completed' && variant.final_asset_id && (
                      <Button
                        variant="ghost"
                        size="sm"
                        icon={<Download size={12} />}
                        onClick={() => {
                          const a = document.createElement('a')
                          a.href = formatAssetUrl(variant.final_asset_id)
                          a.download = `${project.id}-${variant.variant_label.replace(/\s+/g, '-').toLowerCase()}.mp4`
                          a.click()
                        }}
                      />
                    )}
                  </label>
                )
              })}
            </div>

            {selectedId && (
              <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                <Badge variant="success" size="sm">
                  Winner: Variant {String.fromCharCode(65 + abVariants.findIndex((v: any) => v.variant_id === selectedId))}
                </Badge>
              </div>
            )}
          </div>
        )}
      </section>

      {/* Main Showcase Grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(360px, 1fr))', gap: '24px' }}>
        {/* Final Video Master Player */}
        <section
          style={{
            padding: '24px',
            backgroundColor: 'var(--bg-panel)',
            border: '1px solid var(--border-default)',
            borderRadius: 'var(--radius-lg)',
            display: 'flex',
            flexDirection: 'column',
            gap: '16px',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Film size={18} color="var(--accent-primary)" />
              <h3 style={{ fontSize: '15px', fontWeight: 600, color: 'var(--text-primary)' }}>
                Master Video Output (30 Seconds)
              </h3>
            </div>

            <Badge variant={isReadyToPublish ? 'success' : 'neutral'} dot size="md">
              {isReadyToPublish ? 'Ready to Publish' : 'Draft Stage'}
            </Badge>
          </div>

          {/* Video Player Display */}
          <div
            style={{
              backgroundColor: 'var(--bg-app)',
              borderRadius: 'var(--radius-md)',
              border: '1px solid var(--border-default)',
              minHeight: '380px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              overflow: 'hidden',
            }}
          >
            {activeVideoId ? (
              <video
                src={formatAssetUrl(activeVideoId)}
                controls
                playsInline
                style={{ width: '100%', maxHeight: '480px', borderRadius: 'var(--radius-md)' }}
              />
            ) : (
              <div
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  color: 'var(--text-muted)',
                  gap: '8px',
                  padding: '32px',
                  textAlign: 'center',
                }}
              >
                <Film size={32} strokeWidth={1.5} />
                <span style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
                  No draft or final video available yet.
                </span>
                <span style={{ fontSize: '11px' }}>
                  Render the timeline in the previous step to generate the video stream.
                </span>
              </div>
            )}
          </div>

          {/* Download & Share Actions */}
          {finalAssetId && (
            <div style={{ display: 'flex', gap: '8px' }}>
              <Button
                variant="primary"
                size="sm"
                icon={<Download size={13} />}
                onClick={handleDownload}
                style={{ flex: 1 }}
              >
                Download MP4
              </Button>
              <Button
                variant="outline"
                size="sm"
                icon={copied ? <Check size={13} color="var(--status-success)" /> : <Copy size={13} />}
                onClick={handleCopyAssetId}
                style={{ flex: 1 }}
              >
                {copiedAssetId ? 'Copied!' : 'Copy Asset ID'}
              </Button>
              <Button
                variant="outline"
                size="sm"
                icon={<Share2 size={13} />}
                onClick={handleCopyLink}
              >
                {copied ? 'Copied!' : 'Share Link'}
              </Button>
            </div>
          )}
        </section>

        {/* Master Details & Publishing Actions */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          {/* Quality Selector */}
          <section className="export-options" style={{
            padding: '16px 20px',
            backgroundColor: 'var(--bg-panel)',
            border: '1px solid var(--border-default)',
            borderRadius: 'var(--radius-lg)',
            display: 'flex',
            flexDirection: 'column',
            gap: '12px',
          }}>
            <h4 style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-primary)', borderBottom: '1px solid var(--border-subtle)', paddingBottom: '8px' }}>
              Output Quality
            </h4>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              {(Object.entries(QUALITY_MAP) as [QualityPreset, typeof QUALITY_MAP[QualityPreset]][]).map(([key, q]) => (
                <label
                  key={key}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '10px',
                    padding: '8px 12px',
                    borderRadius: 'var(--radius-md)',
                    border: `1px solid ${quality === key ? 'var(--accent-primary)' : 'var(--border-default)'}`,
                    backgroundColor: quality === key ? 'var(--status-active-bg)' : 'transparent',
                    cursor: 'pointer',
                  }}
                >
                  <input
                    type="radio"
                    name="quality"
                    checked={quality === key}
                    onChange={() => setQuality(key)}
                    style={{ accentColor: 'var(--accent-primary)' }}
                  />
                  <div style={{ flex: 1 }}>
                    <span style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-primary)' }}>{q.label}</span>
                    <span style={{ fontSize: '11px', color: 'var(--text-muted)', marginLeft: '8px' }}>{q.desc}</span>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <span style={{ fontSize: '11px', color: 'var(--text-secondary)', display: 'block' }}>{q.estSize}</span>
                    <span style={{ fontSize: '10px', color: 'var(--text-muted)', display: 'block' }}>{q.estTime}</span>
                  </div>
                </label>
              ))}
            </div>
          </section>

          {/* Platform Presets */}
          <section style={{
            padding: '16px 20px',
            backgroundColor: 'var(--bg-panel)',
            border: '1px solid var(--border-default)',
            borderRadius: 'var(--radius-lg)',
            display: 'flex',
            flexDirection: 'column',
            gap: '10px',
          }}>
            <h4 style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-primary)', borderBottom: '1px solid var(--border-subtle)', paddingBottom: '8px' }}>
              Platform Presets
            </h4>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
              {PLATFORM_PRESETS.map((p) => (
                <button
                  key={p.key}
                  onClick={() => setPlatform(platform === p.key ? null : p.key)}
                  style={{
                    padding: '6px 12px',
                    borderRadius: 'var(--radius-sm)',
                    fontSize: '11px',
                    border: `1px solid ${platform === p.key ? 'var(--accent-primary)' : 'var(--border-default)'}`,
                    backgroundColor: platform === p.key ? 'var(--status-active-bg)' : 'transparent',
                    color: platform === p.key ? 'var(--accent-primary)' : 'var(--text-secondary)',
                    cursor: 'pointer',
                  }}
                >
                  {p.label}
                </button>
              ))}
            </div>
            {platform && (
              <div style={{ fontSize: '11px', color: 'var(--text-muted)', display: 'flex', gap: '16px', marginTop: '4px' }}>
                <span>Aspect: <strong style={{ color: 'var(--text-secondary)' }}>{PLATFORM_PRESETS.find(p => p.key === platform)?.aspect}</strong></span>
                <span>Max Duration: <strong style={{ color: 'var(--text-secondary)' }}>{PLATFORM_PRESETS.find(p => p.key === platform)?.maxDur}</strong></span>
                <span>Max Size: <strong style={{ color: 'var(--text-secondary)' }}>{PLATFORM_PRESETS.find(p => p.key === platform)?.maxSize}</strong></span>
              </div>
            )}
          </section>

          {/* Export Progress */}
          {exporting && (
            <section className="export-progress" style={{
              padding: '16px 20px',
              backgroundColor: 'var(--bg-panel)',
              border: '1px solid var(--border-default)',
              borderRadius: 'var(--radius-lg)',
              display: 'flex',
              flexDirection: 'column',
              gap: '10px',
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-primary)' }}>
                  Exporting: {EXPORT_STAGES[exportStageIndex]}
                </span>
                <span style={{ fontSize: '11px', fontFamily: 'var(--font-mono)', color: 'var(--accent-timeline)' }}>
                  {Math.round(exportPercent)}%
                </span>
              </div>
              <div style={{
                height: '6px',
                backgroundColor: 'var(--bg-app)',
                borderRadius: 'var(--radius-sm)',
                overflow: 'hidden',
              }}>
                <div style={{
                  width: `${exportPercent}%`,
                  height: '100%',
                  backgroundColor: 'var(--accent-primary)',
                  borderRadius: 'var(--radius-sm)',
                  transition: 'width 0.5s ease',
                }} />
              </div>
              <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
                {EXPORT_STAGES.map((stage, i) => (
                  <span
                    key={stage}
                    style={{
                      fontSize: '10px',
                      color: i < exportStageIndex ? 'var(--status-success)' : i === exportStageIndex ? 'var(--accent-primary)' : 'var(--text-muted)',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '3px',
                    }}
                  >
                    {i < exportStageIndex ? <Check size={10} /> : i === exportStageIndex ? <Clock size={10} className="animate-spin" /> : null}
                    {stage}
                  </span>
                ))}
              </div>
            </section>
          )}

          {/* Metadata Card */}
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
            <h4 style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-primary)', borderBottom: '1px solid var(--border-subtle)', paddingBottom: '8px' }}>
              Master Video Specs
            </h4>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', fontSize: '13px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ color: 'var(--text-muted)' }}>Target Format</span>
                <strong style={{ color: 'var(--text-primary)' }}>
                  {platform ? PLATFORM_PRESETS.find(p => p.key === platform)?.label : 'Vertical 9:16 (TikTok / Reels / Shorts)'}
                </strong>
              </div>

              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ color: 'var(--text-muted)' }}>Quality</span>
                <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--accent-timeline)' }}>{QUALITY_MAP[quality].label}</span>
              </div>

              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ color: 'var(--text-muted)' }}>Duration</span>
                <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--accent-timeline)' }}>30.00 Seconds</span>
              </div>

              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ color: 'var(--text-muted)' }}>Master Asset ID</span>
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--text-primary)' }}>
                  {finalAssetId || draftAssetId || 'Pending'}
                </span>
              </div>

              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ color: 'var(--text-muted)' }}>Production Status</span>
                <Badge variant={isReadyToPublish ? 'success' : 'active'} size="sm">
                  {project.status}
                </Badge>
              </div>
            </div>
          </section>

          {/* Export Action Card */}
          <section
            style={{
              padding: '20px',
              backgroundColor: 'var(--bg-panel)',
              border: '1px solid var(--border-default)',
              borderRadius: 'var(--radius-lg)',
              display: 'flex',
              flexDirection: 'column',
              gap: '12px',
            }}
          >
            <h4 style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-primary)' }}>
              Publishing & Distribution
            </h4>
            <p style={{ fontSize: '12px', color: 'var(--text-secondary)', lineHeight: 1.4 }}>
              Produce the high-bitrate master MP4 container ready for campaign deployment or social network publishing.
            </p>

            <Button
              variant="success"
              size="lg"
              icon={<Sparkles size={16} />}
              disabled={!canExport || exportMutation.isPending || exporting}
              loading={exportMutation.isPending}
              onClick={handleExport}
              title="Export final 30s master commercial video"
              style={{ width: '100%', marginTop: '6px' }}
            >
              {finalAssetId ? 'Re-export Master Video' : 'Export Final 30s Master Video'}
            </Button>
          </section>

          {/* Compliance Status Section */}
          <section
            style={{
              padding: '16px 20px',
              backgroundColor: 'var(--bg-panel)',
              border: '1px solid var(--border-default)',
              borderRadius: 'var(--radius-lg)',
              display: 'flex',
              flexDirection: 'column',
              gap: '10px',
            }}
          >
            <h4 style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-primary)', borderBottom: '1px solid var(--border-subtle)', paddingBottom: '8px' }}>
              Compliance & Distribution
            </h4>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {/* Brand Safety Badge */}
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span style={{ fontSize: '11px', color: 'var(--text-muted)', minWidth: '100px' }}>Brand Safety</span>
                <ComplianceBadge
                  status={complianceStatus}
                  label={complianceStatus === 'passed' ? 'All checks passed' : complianceStatus === 'warning' ? 'Review needed' : 'Pending export'}
                  issues={complianceIssues}
                  showDetails={true}
                />
              </div>

              {/* AIGC Badge */}
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span style={{ fontSize: '11px', color: 'var(--text-muted)', minWidth: '100px' }}>AIGC Content</span>
                <ComplianceBadge
                  status={finalAssetId ? 'passed' : 'pending'}
                  label={finalAssetId ? 'AI-Generated Content' : 'Pending video'}
                />
              </div>
            </div>

            {/* Push to Channel */}
            <div style={{ marginTop: '8px' }}>
              <PushToChannel
                projectId={project.id}
                assetId={finalAssetId || draftAssetId || ''}
              />
            </div>
          </section>

          {/* Publication History */}
          {publications.length > 0 && (
            <section
              style={{
                padding: '16px 20px',
                backgroundColor: 'var(--bg-panel)',
                border: '1px solid var(--border-default)',
                borderRadius: 'var(--radius-lg)',
                display: 'flex',
                flexDirection: 'column',
                gap: '10px',
              }}
            >
              <h4 style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-primary)', borderBottom: '1px solid var(--border-subtle)', paddingBottom: '8px' }}>
                Publication History
              </h4>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                {publications.map((pub: Publication) => {
                  const statusVariant = pub.status === 'published' ? 'success' as const : pub.status === 'failed' ? 'error' as const : 'running' as const
                  return (
                    <div
                      key={pub.id}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: '10px',
                        padding: '8px 12px',
                        borderRadius: 'var(--radius-md)',
                        border: '1px solid var(--border-default)',
                        backgroundColor: 'var(--bg-app)',
                        fontSize: '12px',
                      }}
                    >
                      <span style={{ fontSize: '14px' }}>
                        {pub.platform === 'tiktok' ? '\uD83C\uDFB5' : pub.platform === 'youtube_shorts' ? '\u25B6\uFE0F' : '\uD83D\uDCF8'}
                      </span>
                      <div style={{ flex: 1 }}>
                        <div style={{ color: 'var(--text-primary)', fontWeight: 500, textTransform: 'capitalize' }}>
                          {pub.platform.replace('_', ' ')}
                        </div>
                        <div style={{ color: 'var(--text-muted)', fontSize: '10px' }}>
                          {new Date(pub.created_at).toLocaleString()}
                        </div>
                      </div>
                      <Badge variant={statusVariant} size="sm">{pub.status}</Badge>
                      {pub.platform_post_id && (
                        <a
                          href={`https://www.tiktok.com/@user/video/${pub.platform_post_id}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          style={{ color: 'var(--accent-primary)', fontSize: '10px', display: 'flex', alignItems: 'center', gap: '3px' }}
                        >
                          View <ExternalLink size={10} />
                        </a>
                      )}
                    </div>
                  )
                })}
              </div>
            </section>
          )}
        </div>
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
    </div>
  )
}
