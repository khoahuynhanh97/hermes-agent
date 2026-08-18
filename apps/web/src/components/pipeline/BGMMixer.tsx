import React, { useState, useRef, useEffect } from 'react'
import { Music, Play, Pause, Volume2 } from 'lucide-react'
import { Button } from '../common/Button'
import { Badge } from '../common/Badge'

export type BGMTone = 'ambient' | 'upbeat' | 'cinematic' | 'minimal' | 'energetic'

interface BGMMixerProps {
  project_id: string
  onBgmChange?: (bgmPath: string, volume: number) => void
}

const TONE_OPTIONS: { value: BGMTone; label: string }[] = [
  { value: 'ambient', label: 'Ambient' },
  { value: 'upbeat', label: 'Upbeat' },
  { value: 'cinematic', label: 'Cinematic' },
  { value: 'minimal', label: 'Minimal' },
  { value: 'energetic', label: 'Energetic' },
]

export const BGMMixer: React.FC<BGMMixerProps> = ({ project_id, onBgmChange }) => {
  const [tone, setTone] = useState<BGMTone>('ambient')
  const [volume, setVolume] = useState(60)
  const [autoDuck, setAutoDuck] = useState(true)
  const [isPreviewing, setIsPreviewing] = useState(false)
  const [duckLevel, setDuckLevel] = useState(0)
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const duckIntervalRef = useRef<number | null>(null)

  useEffect(() => {
    return () => {
      if (audioRef.current) {
        audioRef.current.pause()
        audioRef.current = null
      }
      if (duckIntervalRef.current) clearInterval(duckIntervalRef.current)
    }
  }, [])

  useEffect(() => {
    if (isPreviewing && autoDuck) {
      duckIntervalRef.current = window.setInterval(() => {
        setDuckLevel((prev) => {
          const next = prev + (Math.random() > 0.5 ? 8 : -12)
          return Math.max(0, Math.min(100, next))
        })
      }, 400)
    } else {
      if (duckIntervalRef.current) clearInterval(duckIntervalRef.current)
      setDuckLevel(0)
    }
    return () => {
      if (duckIntervalRef.current) clearInterval(duckIntervalRef.current)
    }
  }, [isPreviewing, autoDuck])

  const handlePreview = () => {
    if (isPreviewing) {
      audioRef.current?.pause()
      setIsPreviewing(false)
      return
    }
    setIsPreviewing(true)
    setTimeout(() => setIsPreviewing(false), 5000)
  }

  const handleToneChange = (newTone: BGMTone) => {
    setTone(newTone)
    onBgmChange?.(newTone, volume)
  }

  const handleVolumeChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const v = Number(e.target.value)
    setVolume(v)
    onBgmChange?.(tone, v)
  }

  return (
    <div className="bgm-mixer-panel" style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <Music size={14} color="var(--accent-primary)" />
          <span style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-primary)' }}>BGM Mixer</span>
        </div>
        <Badge variant="neutral" size="sm">{tone}</Badge>
      </div>

      <div>
        <label style={{ display: 'block', fontSize: '11px', color: 'var(--text-muted)', marginBottom: '4px' }}>
          Tone Selector
        </label>
        <select
          value={tone}
          onChange={(e) => handleToneChange(e.target.value as BGMTone)}
          style={{ width: '100%' }}
        >
          {TONE_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </select>
      </div>

      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
          <label style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Volume</label>
          <span style={{ fontSize: '11px', fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>{volume}%</span>
        </div>
        <input
          type="range"
          min={0}
          max={100}
          value={volume}
          onChange={handleVolumeChange}
          style={{ width: '100%' }}
        />
      </div>

      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Auto-Ducking</span>
        <button
          onClick={() => setAutoDuck(!autoDuck)}
          style={{
            padding: '2px 8px',
            borderRadius: 'var(--radius-sm)',
            fontSize: '11px',
            border: `1px solid ${autoDuck ? 'var(--status-success-border)' : 'var(--border-default)'}`,
            backgroundColor: autoDuck ? 'var(--status-success-bg)' : 'transparent',
            color: autoDuck ? 'var(--status-success)' : 'var(--text-muted)',
            cursor: 'pointer',
          }}
        >
          {autoDuck ? 'ON' : 'OFF'}
        </button>
      </div>

      {isPreviewing && autoDuck && (
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '2px' }}>
            <span style={{ fontSize: '10px', color: 'var(--text-muted)' }}>Voice Activity</span>
            <span style={{ fontSize: '10px', fontFamily: 'var(--font-mono)', color: 'var(--accent-timeline)' }}>{duckLevel}%</span>
          </div>
          <div className="bgm-visualizer" style={{
            height: '6px',
            backgroundColor: 'var(--bg-app)',
            borderRadius: 'var(--radius-sm)',
            overflow: 'hidden',
          }}>
            <div style={{
              width: `${100 - duckLevel}%`,
              height: '100%',
              backgroundColor: 'var(--accent-primary)',
              borderRadius: 'var(--radius-sm)',
              transition: 'width 0.3s ease',
            }} />
          </div>
          <span style={{ fontSize: '10px', color: 'var(--accent-timeline)', display: 'block', marginTop: '2px' }}>
            BGM ducks {duckLevel}% under voice
          </span>
        </div>
      )}

      <Button
        variant="outline"
        size="sm"
        icon={isPreviewing ? <Pause size={13} /> : <Play size={13} />}
        onClick={handlePreview}
        style={{ width: '100%' }}
      >
        {isPreviewing ? 'Stop Preview' : 'Preview 5s Mix'}
      </Button>

      <div style={{ fontSize: '11px', color: 'var(--text-muted)', display: 'flex', justifyContent: 'space-between' }}>
        <span>Track: {tone}.mp3</span>
        <span>~30s</span>
      </div>
    </div>
  )
}
