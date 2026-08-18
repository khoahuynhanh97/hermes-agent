import React from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Check,
  Lock,
  Loader2,
  AlertCircle,
  Package,
  FileText,
  ListOrdered,
  Image as ImageIcon,
  Film,
  SlidersHorizontal,
  Share2,
} from 'lucide-react'
import {
  CANONICAL_STAGES,
  StageKey,
  StageState,
  VideoFactoryProject,
} from '../../types/videoFactory'
import { deriveStageState } from '../../utils/stageDerivation'

interface PipelineStepperProps {
  projectId: string
  currentStage: StageKey
  project: VideoFactoryProject | null
  activeJobTask?: string
}

export const PipelineStepper: React.FC<PipelineStepperProps> = ({
  projectId,
  currentStage,
  project,
  activeJobTask,
}) => {
  const navigate = useNavigate()

  const getStageIcon = (key: StageKey) => {
    switch (key) {
      case 'resources':
        return <Package size={14} />
      case 'brief':
        return <FileText size={14} />
      case 'scenes':
        return <ListOrdered size={14} />
      case 'storyboard':
        return <ImageIcon size={14} />
      case 'generation':
        return <Film size={14} />
      case 'timeline':
        return <SlidersHorizontal size={14} />
      case 'export':
        return <Share2 size={14} />
    }
  }

  const getStateStyle = (state: StageState, isCurrent: boolean) => {
    if (isCurrent) {
      return {
        bg: 'var(--bg-surface-active)',
        border: 'var(--accent-primary)',
        text: 'var(--text-primary)',
        iconColor: 'var(--accent-primary)',
      }
    }
    switch (state) {
      case 'completed':
        return {
          bg: 'var(--status-success-bg)',
          border: 'var(--status-success-border)',
          text: 'var(--text-primary)',
          iconColor: 'var(--status-success)',
        }
      case 'running':
        return {
          bg: 'var(--status-running-bg)',
          border: 'var(--status-running-border)',
          text: 'var(--text-primary)',
          iconColor: 'var(--status-running)',
        }
      case 'blocked':
        return {
          bg: 'var(--bg-input)',
          border: 'var(--border-subtle)',
          text: 'var(--text-muted)',
          iconColor: 'var(--text-muted)',
        }
      case 'failed':
        return {
          bg: 'var(--status-error-bg)',
          border: 'var(--status-error-border)',
          text: 'var(--text-primary)',
          iconColor: 'var(--status-error)',
        }
      default: // not_started
        return {
          bg: 'var(--bg-surface)',
          border: 'var(--border-default)',
          text: 'var(--text-secondary)',
          iconColor: 'var(--text-muted)',
        }
    }
  }

  const handleStageClick = (stageKey: StageKey) => {
    navigate(`/projects/${encodeURIComponent(projectId)}/workflow/${stageKey}`)
  }

  return (
    <nav
      className="pipeline-stepper-container"
      aria-label="Workflow Pipeline"
      style={{
        padding: '8px 20px',
        backgroundColor: 'var(--bg-panel)',
        borderBottom: '1px solid var(--border-subtle)',
        display: 'flex',
        alignItems: 'center',
        gap: '6px',
        overflowX: 'auto',
        WebkitOverflowScrolling: 'touch',
      }}
    >
      {CANONICAL_STAGES.map((meta, index) => {
        const state = deriveStageState(meta.key, project, currentStage, activeJobTask)
        const isCurrent = currentStage === meta.key
        const style = getStateStyle(state, isCurrent)

        return (
          <React.Fragment key={meta.key}>
            <button
              onClick={() => handleStageClick(meta.key)}
              title={`${meta.label} - ${state.replace('_', ' ')}`}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                padding: '6px 12px',
                backgroundColor: style.bg,
                border: `1px solid ${style.border}`,
                borderRadius: 'var(--radius-md)',
                color: style.text,
                fontSize: '12px',
                fontWeight: isCurrent ? 600 : 500,
                transition: 'all 0.15s ease',
                flexShrink: 0,
              }}
              className="stepper-item-btn"
            >
              {/* Status Indicator Icon */}
              <span
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  color: style.iconColor,
                }}
              >
                {state === 'completed' ? (
                  <Check size={13} strokeWidth={2.5} />
                ) : state === 'running' ? (
                  <Loader2 size={13} className="animate-spin" />
                ) : state === 'blocked' ? (
                  <Lock size={12} />
                ) : state === 'failed' ? (
                  <AlertCircle size={13} />
                ) : (
                  getStageIcon(meta.key)
                )}
              </span>

              {/* Stage Name */}
              <span>{meta.shortLabel}</span>

              {/* Status Dot for Current */}
              {isCurrent && (
                <span
                  style={{
                    width: '5px',
                    height: '5px',
                    borderRadius: '50%',
                    backgroundColor: 'var(--accent-primary)',
                  }}
                />
              )}
            </button>

            {/* Separator line between stages */}
            {index < CANONICAL_STAGES.length - 1 && (
              <span
                style={{
                  width: '12px',
                  height: '1px',
                  backgroundColor: 'var(--border-subtle)',
                  flexShrink: 0,
                }}
              />
            )}
          </React.Fragment>
        )
      })}
    </nav>
  )
}
