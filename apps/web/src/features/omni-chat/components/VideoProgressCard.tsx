import React from 'react'
import {
  Film,
  CheckCircle2,
  Loader2,
  Sparkles,
  Layers,
  Music,
} from 'lucide-react'
import { PipelineProgress } from '../../../types/omniChat'

interface VideoProgressCardProps {
  progress: PipelineProgress
}

const STEPS = [
  { id: 1, label: 'Identity Lock', icon: Layers },
  { id: 2, label: 'Storyboard', icon: Sparkles },
  { id: 3, label: 'Scene Render', icon: Film },
  { id: 4, label: 'Master Mix', icon: Music },
]

export const VideoProgressCard: React.FC<VideoProgressCardProps> = ({ progress }) => {
  const isCompleted = progress.percent === 100 || progress.status === 'completed'

  return (
    <div
      style={{
        margin: '12px 0',
        padding: '16px',
        backgroundColor: 'var(--bg-panel)',
        border: `1px solid ${isCompleted ? 'var(--status-success-border)' : 'rgba(245, 158, 11, 0.3)'}`,
        borderRadius: 'var(--radius-lg)',
        boxShadow: 'var(--shadow-sm)',
        display: 'flex',
        flexDirection: 'column',
        gap: '12px',
        maxWidth: '560px',
      }}
    >
      {/* Header Info */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <div
            style={{
              padding: '6px',
              borderRadius: 'var(--radius-md)',
              backgroundColor: isCompleted ? 'var(--status-success-bg)' : 'rgba(245, 158, 11, 0.15)',
              color: isCompleted ? 'var(--status-success)' : 'var(--accent-timeline)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            {isCompleted ? (
              <CheckCircle2 size={16} />
            ) : (
              <Loader2 size={16} className="animate-spin" style={{ animation: 'spin 1.2s linear infinite' }} />
            )}
          </div>

          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <strong style={{ fontSize: '13px', color: 'var(--text-primary)' }}>
                {isCompleted ? 'Video Production Complete' : 'AI Video Synthesis Pipeline'}
              </strong>
              <span
                style={{
                  fontSize: '11px',
                  fontFamily: 'var(--font-mono)',
                  color: isCompleted ? 'var(--status-success)' : 'var(--accent-timeline)',
                  backgroundColor: isCompleted ? 'var(--status-success-bg)' : 'rgba(245, 158, 11, 0.12)',
                  padding: '1px 6px',
                  borderRadius: 'var(--radius-sm)',
                }}
              >
                {progress.percent}%
              </span>
            </div>
            <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
              {progress.message || `Executing Step ${progress.step}/${progress.totalSteps}: ${progress.stepName}`}
            </span>
          </div>
        </div>
      </div>

      {/* Progress Bar */}
      <div
        style={{
          width: '100%',
          height: '6px',
          backgroundColor: 'var(--bg-surface-active)',
          borderRadius: '3px',
          overflow: 'hidden',
          position: 'relative',
        }}
      >
        <div
          style={{
            height: '100%',
            width: `${progress.percent}%`,
            backgroundColor: isCompleted ? 'var(--status-success)' : 'var(--accent-timeline)',
            borderRadius: '3px',
            transition: 'width 0.4s cubic-bezier(0.4, 0, 0.2, 1)',
          }}
        />
      </div>

      {/* Step Indicators */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '6px', marginTop: '2px' }}>
        {STEPS.map((s) => {
          const StepIcon = s.icon
          const isDone = progress.step > s.id || progress.percent === 100
          const isCurrent = progress.step === s.id && progress.percent < 100
          const isPending = progress.step < s.id

          return (
            <div
              key={s.id}
              style={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                textAlign: 'center',
                padding: '6px 4px',
                borderRadius: 'var(--radius-sm)',
                backgroundColor: isCurrent ? 'var(--bg-surface-active)' : 'transparent',
                border: `1px solid ${isCurrent ? 'rgba(245, 158, 11, 0.4)' : 'transparent'}`,
                opacity: isPending ? 0.45 : 1,
              }}
            >
              <div
                style={{
                  width: '22px',
                  height: '22px',
                  borderRadius: '50%',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  marginBottom: '4px',
                  backgroundColor: isDone
                    ? 'var(--status-success-bg)'
                    : isCurrent
                    ? 'rgba(245, 158, 11, 0.15)'
                    : 'var(--bg-surface)',
                  color: isDone
                    ? 'var(--status-success)'
                    : isCurrent
                    ? 'var(--accent-timeline)'
                    : 'var(--text-muted)',
                }}
              >
                {isDone ? <CheckCircle2 size={12} /> : <StepIcon size={12} />}
              </div>
              <span
                style={{
                  fontSize: '10px',
                  fontWeight: isCurrent ? 600 : 500,
                  color: isDone
                    ? 'var(--text-primary)'
                    : isCurrent
                    ? 'var(--accent-timeline)'
                    : 'var(--text-muted)',
                  whiteSpace: 'nowrap',
                }}
              >
                {s.label}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
