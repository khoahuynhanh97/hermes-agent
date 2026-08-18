import React from 'react'
import { useNavigate } from 'react-router-dom'
import { AlertCircle, ArrowLeft } from 'lucide-react'
import { StageKey } from '../../types/videoFactory'
import { getStageDependency } from '../../utils/stageDerivation'
import { Button } from '../common/Button'

interface DependencyNoticeProps {
  projectId: string
  currentStage: StageKey
}

export const DependencyNotice: React.FC<DependencyNoticeProps> = ({ projectId, currentStage }) => {
  const navigate = useNavigate()
  const dep = getStageDependency(currentStage)

  if (!dep) return null

  return (
    <div
      style={{
        padding: '16px 20px',
        backgroundColor: 'var(--status-blocked-bg)',
        border: '1px solid var(--status-blocked-border)',
        borderRadius: 'var(--radius-lg)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        flexWrap: 'wrap',
        gap: '12px',
        margin: '16px 0',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: '10px', maxWidth: '600px' }}>
        <AlertCircle size={18} color="var(--status-running)" style={{ marginTop: '2px', flexShrink: 0 }} />
        <div>
          <h4 style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-primary)' }}>
            Dependency Requirement: {dep.label}
          </h4>
          <p style={{ fontSize: '12px', color: 'var(--text-secondary)', marginTop: '2px' }}>
            {dep.reason}
          </p>
        </div>
      </div>

      <Button
        variant="secondary"
        size="sm"
        icon={<ArrowLeft size={14} />}
        onClick={() => navigate(`/projects/${encodeURIComponent(projectId)}/workflow/${dep.dependsOn}`)}
      >
        Go to {dep.label}
      </Button>
    </div>
  )
}
