import React, { useState } from 'react'
import {
  Activity,
  Search,
  CheckCircle2,
  AlertCircle,
  Clock,
  Terminal,
  Cpu,
  RefreshCw,
} from 'lucide-react'
import { api } from '../../lib/api'
import { Badge, BadgeVariant } from '../../components/common/Badge'
import { Button } from '../../components/common/Button'
import { EmptyState } from '../../components/common/EmptyState'
import './OperationsPage.css'

interface JobDetail {
  id: string
  task_name: string
  status: string
  error_message?: string
}

export const OperationsPage: React.FC = () => {
  const [lookupId, setLookupId] = useState('')
  const [searchedJob, setSearchedJob] = useState<JobDetail | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [lookupError, setLookupError] = useState<string | null>(null)

  const handleLookup = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!lookupId.trim()) return
    setIsLoading(true)
    setLookupError(null)
    setSearchedJob(null)

    try {
      const res = await api.get<{ id: string; task_name: string; status: string }>(
        `/api/jobs/${encodeURIComponent(lookupId.trim())}`
      )
      setSearchedJob({
        id: res.id,
        task_name: res.task_name,
        status: res.status,
      })
    } catch (err: any) {
      setLookupError(err.message || 'Job ID not found in worker registry')
    } finally {
      setIsLoading(false)
    }
  }

  const getStatusVariant = (status?: string): BadgeVariant => {
    switch (status?.toLowerCase()) {
      case 'succeeded':
      case 'completed':
        return 'success'
      case 'running':
        return 'running'
      case 'failed':
      case 'cancelled':
        return 'error'
      default:
        return 'neutral'
    }
  }

  return (
    <div className="operations-container">
      {/* Topbar */}
      <div className="operations-topbar">
        <div>
          <h1 style={{ fontSize: '20px', fontWeight: 600, color: 'var(--text-primary)' }}>
            Operations & Worker Diagnostics
          </h1>
          <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginTop: '2px' }}>
            Inspect background tasks, AI synthesis worker status, and Video Factory rendering jobs.
          </p>
        </div>
      </div>

      {/* System Status Banner */}
      <div className="system-status-grid">
        <div className="status-metric-card">
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span style={{ fontSize: '11px', fontFamily: 'var(--font-mono)', color: 'var(--text-muted)' }}>
              API RUNTIME
            </span>
            <Cpu size={15} color="var(--status-success)" />
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginTop: '6px' }}>
            <Badge variant="success" dot size="md">
              FastAPI Healthy
            </Badge>
            <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>Port 8000</span>
          </div>
        </div>

        <div className="status-metric-card">
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span style={{ fontSize: '11px', fontFamily: 'var(--font-mono)', color: 'var(--text-muted)' }}>
              STORAGE ROOT
            </span>
            <Activity size={15} color="var(--accent-primary)" />
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginTop: '6px' }}>
            <Badge variant="neutral" size="md">
              Canonical Layout
            </Badge>
            <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>Durable Projections</span>
          </div>
        </div>
      </div>

      {/* Diagnostic Job Inspector */}
      <div className="job-inspector-card">
        <h3 style={{ fontSize: '14px', fontWeight: 600, color: 'var(--text-primary)' }}>
          Job Diagnostic Lookup
        </h3>
        <p style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
          Query a specific durable job ID produced during storyboard generation, TTS audio synthesis, or video timeline rendering.
        </p>

        <form onSubmit={handleLookup} style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
          <div style={{ position: 'relative', flex: 1, minWidth: '280px' }}>
            <Search
              size={14}
              color="var(--text-muted)"
              style={{ position: 'absolute', left: '10px', top: '50%', transform: 'translateY(-50%)' }}
            />
            <input
              type="text"
              placeholder="Paste Job UUID or Task ID..."
              value={lookupId}
              onChange={(e) => setLookupId(e.target.value)}
              style={{ width: '100%', paddingLeft: '32px' }}
            />
          </div>
          <Button
            type="submit"
            variant="primary"
            disabled={!lookupId.trim() || isLoading}
            loading={isLoading}
          >
            Inspect Job
          </Button>
        </form>

        {lookupError && (
          <div style={{ padding: '10px 14px', backgroundColor: 'var(--status-error-bg)', border: '1px solid var(--status-error-border)', borderRadius: 'var(--radius-sm)', color: 'var(--status-error)', fontSize: '12px' }}>
            {lookupError}
          </div>
        )}

        {searchedJob && (
          <div className="job-result-box">
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderBottom: '1px solid var(--border-subtle)', paddingBottom: '10px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Terminal size={16} color="var(--accent-primary)" />
                <strong style={{ color: 'var(--text-primary)', fontSize: '14px' }}>
                  {searchedJob.task_name}
                </strong>
              </div>
              <Badge variant={getStatusVariant(searchedJob.status)} dot size="md">
                {searchedJob.status}
              </Badge>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', fontSize: '12px', marginTop: '10px' }}>
              <div>
                <span style={{ color: 'var(--text-muted)', display: 'block' }}>JOB ID</span>
                <code style={{ color: 'var(--text-primary)' }}>{searchedJob.id}</code>
              </div>
              <div>
                <span style={{ color: 'var(--text-muted)', display: 'block' }}>STATUS</span>
                <span style={{ color: 'var(--text-secondary)' }}>{searchedJob.status}</span>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
