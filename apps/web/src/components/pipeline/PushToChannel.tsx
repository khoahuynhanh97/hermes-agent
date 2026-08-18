import React, { useState, useEffect } from 'react'
import {
  Send, ChevronDown, ExternalLink, AlertCircle, CheckCircle2,
  Link2, Loader2, History, RefreshCw, X,
} from 'lucide-react'
import { Button } from '../common/Button'
import { Badge } from '../common/Badge'
import {
  useTikTokAuthStatus, useTikTokAuthUrl, usePublishToTikTok,
  usePublicationHistory,
} from '../../hooks/useVideoFactory'
import { Publication } from '../../types/videoFactory'

interface PushToChannelProps {
  projectId: string
  assetId: string
  videoPath?: string
  onPublishComplete?: (publicationId: string, platform: string) => void
}

type Platform = 'tiktok' | 'youtube-shorts' | 'instagram-reels'

const PLATFORM_OPTIONS: { key: Platform; label: string; icon: string; disabled?: boolean }[] = [
  { key: 'tiktok', label: 'TikTok', icon: '\uD83C\uDFB5' },
  { key: 'youtube-shorts', label: 'YouTube Shorts', icon: '\u25B6\uFE0F', disabled: true },
  { key: 'instagram-reels', label: 'Instagram Reels', icon: '\uD83D\uDCF8', disabled: true },
]

const STATUS_MAP: Record<string, { label: string; variant: 'success' | 'error' | 'running' | 'active' | 'neutral' }> = {
  uploaded: { label: 'Uploaded', variant: 'success' },
  processing: { label: 'Processing', variant: 'running' },
  publish_complete: { label: 'Published', variant: 'success' },
  publish_failed: { label: 'Failed', variant: 'error' },
  not_published: { label: 'Not Published', variant: 'neutral' },
  uploading: { label: 'Uploading', variant: 'running' },
  published: { label: 'Published', variant: 'success' },
  failed: { label: 'Failed', variant: 'error' },
}

export const PushToChannel: React.FC<PushToChannelProps> = ({
  projectId,
  assetId,
  videoPath,
  onPublishComplete,
}) => {
  const [selectedPlatform, setSelectedPlatform] = useState<Platform | null>(null)
  const [dropdownOpen, setDropdownOpen] = useState(false)
  const [caption, setCaption] = useState('')
  const [showHistory, setShowHistory] = useState(false)
  const [publishError, setPublishError] = useState<string | null>(null)

  const tiktokStatusQuery = useTikTokAuthStatus()
  const tiktokAuthUrlQuery = useTikTokAuthUrl()
  const publishMutation = usePublishToTikTok()
  const historyQuery = usePublicationHistory(projectId)
  const publications = historyQuery.data?.publications || []

  const selectedOption = PLATFORM_OPTIONS.find(c => c.key === selectedPlatform)
  const isTikTokConnected = tiktokStatusQuery.data?.connected ?? false
  const currentPublicationId = publishMutation.data?.publication_id

  const handleOAuth = () => {
    const url = tiktokAuthUrlQuery.data?.auth_url
    if (url) {
      window.open(url, 'tiktok-oauth', 'width=600,height=700')
    }
  }

  const handlePublish = () => {
    if (!selectedPlatform || !isTikTokConnected) return
    setPublishError(null)
    publishMutation.mutate(
      {
        projectId,
        assetId,
        videoPath,
        caption,
      },
      {
        onSuccess: (data) => {
          if (data?.publication_id) {
            onPublishComplete?.(data.publication_id, selectedPlatform)
          }
        },
        onError: (err: any) => {
          setPublishError(err?.detail || err?.message || 'Publish failed')
        },
      }
    )
  }

  const handleCaptionChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const val = e.target.value
    if (val.length <= 150) setCaption(val)
  }

  return (
    <div
      style={{
        padding: '16px 20px',
        backgroundColor: 'var(--bg-panel)',
        border: '1px solid var(--border-default)',
        borderRadius: 'var(--radius-lg)',
        display: 'flex',
        flexDirection: 'column',
        gap: '12px',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <h4
          style={{
            fontSize: '13px',
            fontWeight: 600,
            color: 'var(--text-primary)',
            borderBottom: '1px solid var(--border-subtle)',
            paddingBottom: '8px',
            flex: 1,
          }}
        >
          Publish to Channel
        </h4>
        <button
          onClick={() => setShowHistory(!showHistory)}
          style={{
            background: 'none',
            border: 'none',
            color: 'var(--text-muted)',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: '4px',
            fontSize: '11px',
            padding: '4px 6px',
            borderRadius: 'var(--radius-sm)',
          }}
          title="Publication history"
        >
          <History size={13} />
          <span>{publications.length}</span>
        </button>
      </div>

      {/* Publication History Panel */}
      {showHistory && (
        <div
          style={{
            backgroundColor: 'var(--bg-app)',
            border: '1px solid var(--border-default)',
            borderRadius: 'var(--radius-md)',
            padding: '10px',
            display: 'flex',
            flexDirection: 'column',
            gap: '6px',
            maxHeight: '200px',
            overflowY: 'auto',
          }}
        >
          {publications.length === 0 ? (
            <span style={{ fontSize: '11px', color: 'var(--text-muted)', textAlign: 'center', padding: '8px' }}>
              No publications yet
            </span>
          ) : (
            publications.map((pub: Publication) => {
              const statusInfo = STATUS_MAP[pub.status] || STATUS_MAP.not_published
              return (
                <div
                  key={pub.id}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px',
                    padding: '6px 8px',
                    borderRadius: 'var(--radius-sm)',
                    backgroundColor: 'var(--bg-panel)',
                    border: '1px solid var(--border-subtle)',
                    fontSize: '11px',
                  }}
                >
                  <span style={{ fontSize: '12px' }}>
                    {pub.platform === 'tiktok' ? '\uD83C\uDFB5' : pub.platform === 'youtube_shorts' ? '\u25B6\uFE0F' : '\uD83D\uDCF8'}
                  </span>
                  <span style={{ flex: 1, color: 'var(--text-primary)', fontWeight: 500 }}>
                    {pub.platform}
                  </span>
                  <Badge variant={statusInfo.variant} size="sm">{statusInfo.label}</Badge>
                  <span style={{ color: 'var(--text-muted)', fontSize: '10px' }}>
                    {new Date(pub.created_at).toLocaleDateString()}
                  </span>
                </div>
              )
            })
          )}
        </div>
      )}

      {/* Platform Selector */}
      <div style={{ position: 'relative' }}>
        <button
          onClick={() => setDropdownOpen(!dropdownOpen)}
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            width: '100%',
            padding: '8px 12px',
            borderRadius: 'var(--radius-md)',
            border: '1px solid var(--border-default)',
            backgroundColor: 'var(--bg-app)',
            color: selectedOption ? 'var(--text-primary)' : 'var(--text-muted)',
            fontSize: '12px',
            cursor: 'pointer',
          }}
        >
          <span>
            {selectedOption ? `${selectedOption.icon} ${selectedOption.label}` : 'Select a platform'}
          </span>
          <ChevronDown size={14} />
        </button>
        {dropdownOpen && (
          <div
            style={{
              position: 'absolute',
              top: '100%',
              left: 0,
              right: 0,
              zIndex: 10,
              marginTop: '4px',
              backgroundColor: 'var(--bg-panel)',
              border: '1px solid var(--border-default)',
              borderRadius: 'var(--radius-md)',
              boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
              overflow: 'hidden',
            }}
          >
            {PLATFORM_OPTIONS.map(platform => (
              <button
                key={platform.key}
                onClick={() => {
                  if (!platform.disabled) {
                    setSelectedPlatform(platform.key)
                    setDropdownOpen(false)
                  }
                }}
                disabled={platform.disabled}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  width: '100%',
                  padding: '8px 12px',
                  border: 'none',
                  borderBottom: '1px solid var(--border-subtle)',
                  backgroundColor:
                    selectedPlatform === platform.key
                      ? 'var(--status-active-bg)'
                      : 'transparent',
                  color: platform.disabled
                    ? 'var(--text-muted)'
                    : 'var(--text-primary)',
                  fontSize: '12px',
                  cursor: platform.disabled ? 'not-allowed' : 'pointer',
                  textAlign: 'left',
                  opacity: platform.disabled ? 0.5 : 1,
                }}
              >
                <span>{platform.icon}</span>
                <span>{platform.label}</span>
                {platform.disabled && (
                  <span style={{ fontSize: '9px', color: 'var(--text-muted)', marginLeft: 'auto' }}>
                    Coming soon
                  </span>
                )}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* TikTok Connection Status */}
      {selectedPlatform === 'tiktok' && (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            padding: '8px 10px',
            borderRadius: 'var(--radius-sm)',
            backgroundColor: isTikTokConnected ? 'var(--status-success-bg)' : 'var(--status-error-bg)',
            border: `1px solid ${isTikTokConnected ? 'var(--status-success-border)' : 'var(--status-error-border)'}`,
            fontSize: '11px',
          }}
        >
          {isTikTokConnected ? (
            <>
              <CheckCircle2 size={13} color="var(--status-success)" />
              <span style={{ color: 'var(--status-success)', fontWeight: 500 }}>TikTok Connected</span>
            </>
          ) : (
            <>
              <AlertCircle size={13} color="var(--status-error)" />
              <span style={{ color: 'var(--status-error)', flex: 1, fontWeight: 500 }}>TikTok not connected</span>
              <Button
                variant="outline"
                size="sm"
                icon={<Link2 size={11} />}
                onClick={handleOAuth}
                disabled={tiktokAuthUrlQuery.isPending}
              >
                Connect
              </Button>
            </>
          )}
        </div>
      )}

      {/* Caption Input */}
      {selectedPlatform === 'tiktok' && isTikTokConnected && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>Caption</span>
            <span style={{ fontSize: '10px', color: caption.length > 140 ? 'var(--status-error)' : 'var(--text-muted)' }}>
              {caption.length}/150
            </span>
          </div>
          <textarea
            value={caption}
            onChange={handleCaptionChange}
            placeholder="Write a caption... #hashtags"
            rows={2}
            style={{
              padding: '8px 10px',
              borderRadius: 'var(--radius-md)',
              border: '1px solid var(--border-default)',
              backgroundColor: 'var(--bg-app)',
              color: 'var(--text-primary)',
              fontSize: '12px',
              resize: 'none',
              fontFamily: 'inherit',
            }}
          />
        </div>
      )}

      {/* Publish Error */}
      {publishError && (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            padding: '6px 10px',
            backgroundColor: 'var(--status-error-bg)',
            border: '1px solid var(--status-error-border)',
            borderRadius: 'var(--radius-sm)',
            fontSize: '11px',
            color: 'var(--status-error)',
          }}
        >
          <AlertCircle size={12} />
          <span style={{ flex: 1 }}>{publishError}</span>
          <button
            onClick={() => setPublishError(null)}
            style={{ background: 'none', border: 'none', color: 'var(--status-error)', cursor: 'pointer', display: 'flex' }}
          >
            <X size={12} />
          </button>
        </div>
      )}

      {/* Publishing Progress */}
      {publishMutation.isPending && (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            padding: '8px 10px',
            backgroundColor: 'var(--status-active-bg)',
            border: '1px solid var(--status-active-border)',
            borderRadius: 'var(--radius-sm)',
            fontSize: '11px',
            color: 'var(--status-active)',
          }}
        >
          <Loader2 size={13} className="animate-spin" style={{ animation: 'spin 1s linear infinite' }} />
          <span>Publishing to TikTok...</span>
        </div>
      )}

      {/* Publish Success */}
      {currentPublicationId && publishMutation.isSuccess && (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            padding: '6px 10px',
            backgroundColor: 'var(--status-success-bg)',
            border: '1px solid var(--status-success-border)',
            borderRadius: 'var(--radius-sm)',
            fontSize: '11px',
            color: 'var(--status-success)',
          }}
        >
          <ExternalLink size={12} />
          <span>Publication submitted (ID: {currentPublicationId.slice(0, 12)}...)</span>
        </div>
      )}

      {/* Publish Button */}
      <Button
        variant="primary"
        size="md"
        icon={<Send size={13} />}
        disabled={!selectedPlatform || !isTikTokConnected || publishMutation.isPending}
        loading={publishMutation.isPending}
        onClick={handlePublish}
        style={{ width: '100%' }}
      >
        {publishMutation.isSuccess ? 'Published' : publishMutation.isPending ? 'Publishing...' : 'Publish Now'}
      </Button>
    </div>
  )
}
