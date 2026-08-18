import React from 'react'
import { useNavigate } from 'react-router-dom'
import { ChevronLeft, ChevronRight, Loader2, CheckCircle2 } from 'lucide-react'
import { StageKey, VideoFactoryProject } from '../../types/videoFactory'
import { getNextStage, getPrevStage, isStageCompleted } from '../../utils/stageDerivation'
import { Button } from '../common/Button'

interface WorkflowFooterProps {
  projectId: string
  currentStage: StageKey
  project: VideoFactoryProject | null
  activeJob?: { id: string; status: string; task_name?: string } | null
}

export const WorkflowFooter: React.FC<WorkflowFooterProps> = ({
  projectId,
  currentStage,
  project,
  activeJob,
}) => {
  const navigate = useNavigate()

  const prev = getPrevStage(currentStage)
  const next = getNextStage(currentStage)
  const currentCompleted = isStageCompleted(currentStage, project)

  const handleNavigate = (target: StageKey) => {
    navigate(`/projects/${encodeURIComponent(projectId)}/workflow/${target}`)
  }

  return (
    <footer
      className="workflow-footer"
      style={{
        padding: '10px 24px',
        backgroundColor: 'var(--bg-panel)',
        borderTop: '1px solid var(--border-default)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        flexShrink: 0,
        zIndex: 10,
      }}
    >
      {/* Back Button */}
      <div>
        {prev ? (
          <Button
            variant="outline"
            size="md"
            icon={<ChevronLeft size={16} />}
            onClick={() => handleNavigate(prev)}
            title={`Back to ${prev}`}
          >
            Back ({prev})
          </Button>
        ) : (
          <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>First Stage</span>
        )}
      </div>

      {/* Middle: Active Job / Stage State indicator */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
        {activeJob && ['queued', 'running'].includes(activeJob.status.toLowerCase()) ? (
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              padding: '4px 12px',
              backgroundColor: 'var(--status-running-bg)',
              border: '1px solid var(--status-running-border)',
              borderRadius: 'var(--radius-sm)',
              fontSize: '12px',
              color: 'var(--status-running)',
            }}
          >
            <Loader2 size={14} className="animate-spin" />
            <span>
              Job in progress: <strong>{activeJob.task_name || activeJob.id.slice(0, 10)}</strong> ({activeJob.status})
            </span>
          </div>
        ) : currentCompleted ? (
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              fontSize: '12px',
              color: 'var(--status-success)',
            }}
          >
            <CheckCircle2 size={14} />
            <span>Stage Completed</span>
          </div>
        ) : null}
      </div>

      {/* Next Button */}
      <div>
        {next ? (
          <Button
            variant="primary"
            size="md"
            onClick={() => handleNavigate(next)}
            title={`Continue to ${next}`}
          >
            <span>Next ({next})</span>
            <ChevronRight size={16} />
          </Button>
        ) : (
          <span style={{ fontSize: '12px', color: 'var(--status-success)', fontWeight: 600 }}>
            End of Pipeline
          </span>
        )}
      </div>
    </footer>
  )
}
