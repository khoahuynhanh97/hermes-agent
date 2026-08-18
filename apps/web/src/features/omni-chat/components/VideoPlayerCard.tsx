import React, { useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Play,
  Pause,
  Maximize2,
  ExternalLink,
  Film,
  Sparkles,
  Layers,
  Volume2,
  VolumeX,
  Eye,
  Clock,
  CheckCircle2,
} from 'lucide-react'
import { VideoResult, GeneratedAssetItem } from '../../../types/omniChat'
import { Badge } from '../../../components/common/Badge'
import { Button } from '../../../components/common/Button'

interface VideoPlayerCardProps {
  video: VideoResult
  onInspectAsset?: (assetId: string) => void
}

export const VideoPlayerCard: React.FC<VideoPlayerCardProps> = ({
  video,
  onInspectAsset,
}) => {
  const navigate = useNavigate()
  const videoRef = useRef<HTMLVideoElement>(null)
  const [isPlaying, setIsPlaying] = useState(false)
  const [isMuted, setIsMuted] = useState(false)
  const [currentTime, setCurrentTime] = useState(0)
  const [duration, setDuration] = useState(video.durationSeconds || 30)

  const togglePlay = () => {
    if (!videoRef.current) return
    if (isPlaying) {
      videoRef.current.pause()
      setIsPlaying(false)
    } else {
      videoRef.current.play().catch(() => {
        // Autoplay may be restricted
      })
      setIsPlaying(true)
    }
  }

  const toggleMute = () => {
    if (!videoRef.current) return
    videoRef.current.muted = !isMuted
    setIsMuted(!isMuted)
  }

  const handleTimeUpdate = () => {
    if (!videoRef.current) return
    setCurrentTime(videoRef.current.currentTime)
    if (videoRef.current.duration) {
      setDuration(videoRef.current.duration)
    }
  }

  const handleSeek = (e: React.ChangeEvent<HTMLInputElement>) => {
    const time = parseFloat(e.target.value)
    if (videoRef.current) {
      videoRef.current.currentTime = time
      setCurrentTime(time)
    }
  }

  const handleOpenWorkspace = () => {
    if (video.workspaceUrl) {
      navigate(video.workspaceUrl)
    } else {
      navigate(`/projects/${encodeURIComponent(video.projectId)}/workflow/export`)
    }
  }

  const formatTime = (secs: number) => {
    const m = Math.floor(secs / 60)
    const s = Math.floor(secs % 60)
    return `${m}:${s < 10 ? '0' : ''}${s}`
  }

  return (
    <div
      style={{
        margin: '14px 0',
        padding: '16px',
        backgroundColor: 'var(--bg-panel)',
        border: '1px solid var(--border-strong)',
        borderRadius: 'var(--radius-lg)',
        boxShadow: 'var(--shadow-md)',
        display: 'flex',
        flexDirection: 'column',
        gap: '14px',
        maxWidth: '680px',
      }}
    >
      {/* Header Info */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', flexWrap: 'wrap', gap: '8px' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Film size={16} color="var(--accent-primary)" />
            <strong style={{ fontSize: '14px', color: 'var(--text-primary)' }}>
              {video.productName}
            </strong>
            <Badge variant="success" size="sm" dot>
              Ready to Publish
            </Badge>
          </div>
          <span style={{ fontSize: '12px', color: 'var(--text-secondary)', marginTop: '2px', display: 'block' }}>
            Workspace: <code style={{ fontFamily: 'var(--font-mono)' }}>{video.projectId}</code> • {video.resolution}
          </span>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Button
            variant="primary"
            size="sm"
            icon={<ExternalLink size={13} />}
            onClick={handleOpenWorkspace}
          >
            Open in Workspace
          </Button>
        </div>
      </div>

      {/* Main Video & Details Split */}
      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(180px, 220px) 1fr', gap: '16px' }}>
        {/* 9:16 Vertical Video Player */}
        <div
          style={{
            position: 'relative',
            aspectRatio: '9/16',
            maxHeight: '380px',
            backgroundColor: '#000000',
            borderRadius: 'var(--radius-md)',
            overflow: 'hidden',
            border: '1px solid var(--border-default)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          <video
            ref={videoRef}
            src={video.videoUrl}
            poster={video.thumbnailUrl}
            playsInline
            loop
            onTimeUpdate={handleTimeUpdate}
            onEnded={() => setIsPlaying(false)}
            style={{ width: '100%', height: '100%', objectFit: 'cover' }}
          />

          {/* Center Play Overlay Button */}
          <button
            type="button"
            onClick={togglePlay}
            aria-label={isPlaying ? 'Pause video' : 'Play video'}
            style={{
              position: 'absolute',
              width: '44px',
              height: '44px',
              borderRadius: '50%',
              backgroundColor: 'rgba(10, 12, 16, 0.75)',
              backdropFilter: 'blur(4px)',
              border: '1px solid rgba(255, 255, 255, 0.2)',
              color: '#ffffff',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              cursor: 'pointer',
              opacity: isPlaying ? 0 : 1,
              transition: 'opacity 0.2s ease',
            }}
          >
            {isPlaying ? <Pause size={18} /> : <Play size={18} style={{ marginLeft: '2px' }} />}
          </button>

          {/* Bottom Video Controls Overlay */}
          <div
            style={{
              position: 'absolute',
              bottom: 0,
              left: 0,
              right: 0,
              padding: '8px 10px',
              background: 'linear-gradient(to top, rgba(0,0,0,0.85), transparent)',
              display: 'flex',
              flexDirection: 'column',
              gap: '4px',
            }}
          >
            <input
              type="range"
              min="0"
              max={duration || 30}
              step="0.1"
              value={currentTime}
              onChange={handleSeek}
              style={{
                width: '100%',
                height: '4px',
                accentColor: 'var(--accent-primary)',
                cursor: 'pointer',
              }}
            />

            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', color: '#ffffff', fontSize: '11px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <button
                  type="button"
                  onClick={togglePlay}
                  style={{ color: '#ffffff', background: 'none', border: 'none', cursor: 'pointer', padding: '2px' }}
                >
                  {isPlaying ? <Pause size={13} /> : <Play size={13} />}
                </button>
                <button
                  type="button"
                  onClick={toggleMute}
                  style={{ color: '#ffffff', background: 'none', border: 'none', cursor: 'pointer', padding: '2px' }}
                >
                  {isMuted ? <VolumeX size={13} /> : <Volume2 size={13} />}
                </button>
                <span style={{ fontFamily: 'var(--font-mono)' }}>
                  {formatTime(currentTime)} / {formatTime(duration)}
                </span>
              </div>

              <Badge variant="timeline" size="sm">
                9:16 HD
              </Badge>
            </div>
          </div>
        </div>

        {/* Video Production Breakdown & Asset List */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
          <div>
            <span style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
              VIDEO METADATA & SPECS
            </span>
            <div
              style={{
                marginTop: '6px',
                padding: '8px 12px',
                backgroundColor: 'var(--bg-surface)',
                borderRadius: 'var(--radius-md)',
                display: 'grid',
                gridTemplateColumns: '1fr 1fr',
                gap: '8px',
                fontSize: '12px',
              }}
            >
              <div>
                <span style={{ color: 'var(--text-muted)', display: 'block', fontSize: '11px' }}>DURATION</span>
                <strong style={{ color: 'var(--text-primary)' }}>{video.durationSeconds} Seconds</strong>
              </div>
              <div>
                <span style={{ color: 'var(--text-muted)', display: 'block', fontSize: '11px' }}>ASPECT RATIO</span>
                <strong style={{ color: 'var(--text-primary)' }}>{video.aspectRatio} Vertical</strong>
              </div>
              <div>
                <span style={{ color: 'var(--text-muted)', display: 'block', fontSize: '11px' }}>SCENE BEATS</span>
                <strong style={{ color: 'var(--text-primary)' }}>{video.scenesCount} Scenes</strong>
              </div>
              <div>
                <span style={{ color: 'var(--text-muted)', display: 'block', fontSize: '11px' }}>VOICEOVER</span>
                <strong style={{ color: 'var(--text-primary)' }}>Zephyr AI (vi-VN)</strong>
              </div>
            </div>
          </div>

          {/* Generated Asset Keyframe Strip */}
          {video.assets && video.assets.length > 0 && (
            <div>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '6px' }}>
                <span style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                  KEYFRAME ASSETS ({video.assets.length})
                </span>
                <span style={{ fontSize: '11px', color: 'var(--accent-primary)', cursor: 'pointer' }} onClick={() => onInspectAsset && onInspectAsset(video.videoAssetId)}>
                  Inspect Master
                </span>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(95px, 1fr))', gap: '8px' }}>
                {video.assets.map((asset, idx) => (
                  <div
                    key={asset.asset_id}
                    onClick={() => onInspectAsset && onInspectAsset(asset.asset_id)}
                    style={{
                      padding: '6px',
                      backgroundColor: 'var(--bg-surface)',
                      border: '1px solid var(--border-default)',
                      borderRadius: 'var(--radius-md)',
                      cursor: 'pointer',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: '4px',
                      transition: 'border-color 0.15s ease',
                    }}
                  >
                    <div
                      style={{
                        width: '100%',
                        aspectRatio: '9/16',
                        backgroundColor: 'var(--bg-app)',
                        borderRadius: 'var(--radius-sm)',
                        overflow: 'hidden',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                      }}
                    >
                      <img
                        src={asset.url}
                        alt={asset.label || asset.asset_id}
                        style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                        onError={(e) => {
                          // Fallback placeholder pattern
                          ;(e.target as HTMLElement).style.display = 'none'
                        }}
                      />
                      <Sparkles size={14} color="var(--accent-timeline)" style={{ position: 'absolute' }} />
                    </div>

                    <span
                      style={{
                        fontSize: '10px',
                        color: 'var(--text-primary)',
                        fontWeight: 500,
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {asset.label || `Beat ${idx + 1}`}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
