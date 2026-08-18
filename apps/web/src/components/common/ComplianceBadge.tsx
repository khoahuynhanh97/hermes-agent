import React, { useState } from 'react'
import { Check, AlertTriangle, X, Clock, ChevronDown, ChevronUp } from 'lucide-react'

export type ComplianceStatus = 'passed' | 'warning' | 'failed' | 'pending'

interface ComplianceBadgeProps {
  status: ComplianceStatus
  label?: string
  issues?: string[]
  showDetails?: boolean
}

const STATUS_CONFIG: Record<ComplianceStatus, {
  bg: string
  border: string
  color: string
  defaultLabel: string
}> = {
  passed: {
    bg: 'var(--status-success-bg)',
    border: 'var(--status-success-border)',
    color: 'var(--status-success)',
    defaultLabel: 'Passed',
  },
  warning: {
    bg: 'rgba(245, 158, 11, 0.12)',
    border: 'rgba(245, 158, 11, 0.3)',
    color: 'var(--accent-timeline)',
    defaultLabel: 'Warning',
  },
  failed: {
    bg: 'var(--status-error-bg)',
    border: 'var(--status-error-border)',
    color: 'var(--status-error)',
    defaultLabel: 'Failed',
  },
  pending: {
    bg: 'var(--bg-surface-hover)',
    border: 'var(--border-default)',
    color: 'var(--text-muted)',
    defaultLabel: 'Pending',
  },
}

export const ComplianceBadge: React.FC<ComplianceBadgeProps> = ({
  status,
  label,
  issues = [],
  showDetails = false,
}) => {
  const [expanded, setExpanded] = useState(false)
  const config = STATUS_CONFIG[status]
  const displayLabel = label || config.defaultLabel
  const hasIssues = issues.length > 0

  const Icon =
    status === 'passed' ? Check
    : status === 'warning' ? AlertTriangle
    : status === 'failed' ? X
    : Clock

  return (
    <div style={{ display: 'inline-flex', flexDirection: 'column', gap: '4px' }}>
      <div
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: '5px',
          backgroundColor: config.bg,
          border: `1px solid ${config.border}`,
          color: config.color,
          borderRadius: 'var(--radius-sm)',
          padding: '2px 8px',
          fontSize: '11px',
          fontWeight: 600,
          lineHeight: 1.3,
          whiteSpace: 'nowrap',
          cursor: hasIssues && showDetails ? 'pointer' : 'default',
        }}
        onClick={() => hasIssues && showDetails && setExpanded(!expanded)}
      >
        <Icon size={12} />
        <span>{displayLabel}</span>
        {hasIssues && showDetails && (
          expanded ? <ChevronUp size={10} /> : <ChevronDown size={10} />
        )}
      </div>

      {expanded && hasIssues && (
        <div
          style={{
            padding: '6px 10px',
            backgroundColor: 'var(--bg-panel)',
            border: '1px solid var(--border-default)',
            borderRadius: 'var(--radius-sm)',
            fontSize: '11px',
            color: 'var(--text-secondary)',
            maxWidth: '280px',
          }}
        >
          <ul style={{ margin: 0, paddingLeft: '14px' }}>
            {issues.map((issue, i) => (
              <li key={i} style={{ marginBottom: '2px' }}>{issue}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
