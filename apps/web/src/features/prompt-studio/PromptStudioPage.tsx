import React, { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import {
  FileText,
  Sparkles,
  ArrowLeft,
  Copy,
  Check,
  CheckCircle2,
  AlertCircle,
  Package,
  Layers,
  Film,
} from 'lucide-react'
import { Button } from '../../components/common/Button'
import { Badge } from '../../components/common/Badge'

interface StepItem {
  name: string
  content: Record<string, any>
  approved: boolean
  updated_at?: string
}

export const PromptStudioPage: React.FC = () => {
  const { projectId } = useParams<{ projectId: string }>()
  const [steps, setSteps] = useState<Record<string, StepItem>>({})
  const [loading, setLoading] = useState<boolean>(true)
  const [error, setError] = useState<string>('')
  const [copiedKey, setCopiedKey] = useState<string>('')

  const fetchWorkflow = () => {
    if (!projectId) return
    setLoading(true)
    fetch(`/api/prompt-studio/${projectId}`)
      .then((res) => {
        if (!res.ok) throw new Error('Prompt Studio data not available for this project')
        return res.json()
      })
      .then((data) => {
        const stepMap: Record<string, StepItem> = {}
        ;(data.steps || []).forEach((s: any) => {
          stepMap[s.name] = s
        })
        setSteps(stepMap)
        setError('')
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    fetchWorkflow()
  }, [projectId])

  const copyToClipboard = (key: string, text: string) => {
    navigator.clipboard.writeText(text)
    setCopiedKey(key)
    setTimeout(() => setCopiedKey(''), 2000)
  }

  return (
    <div style={{ padding: '24px 32px', maxWidth: '1200px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '20px', width: '100%' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '12px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <Link to={`/projects/${encodeURIComponent(projectId || '')}/workflow/resources`}>
            <Button variant="outline" size="sm" icon={<ArrowLeft size={14} />}>
              Back to Workflow
            </Button>
          </Link>
          <div>
            <h1 style={{ fontSize: '18px', fontWeight: 600, color: 'var(--text-primary)' }}>
              Prompt Studio: {projectId}
            </h1>
            <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
              Structured Prompt Inspection & Creative Beats
            </span>
          </div>
        </div>
      </div>

      {error ? (
        <div style={{ padding: '20px', backgroundColor: 'var(--bg-panel)', border: '1px solid var(--border-default)', borderRadius: 'var(--radius-lg)', textAlign: 'center', color: 'var(--text-secondary)' }}>
          <p>{error}</p>
          <div style={{ marginTop: '12px' }}>
            <Link to={`/projects/${encodeURIComponent(projectId || '')}/workflow/resources`}>
              <Button variant="primary" size="sm">
                Open Project Workspace
              </Button>
            </Link>
          </div>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          {Object.entries(steps).map(([stepKey, item]) => (
            <div
              key={stepKey}
              style={{
                padding: '18px 20px',
                backgroundColor: 'var(--bg-panel)',
                border: '1px solid var(--border-default)',
                borderRadius: 'var(--radius-lg)',
                display: 'flex',
                flexDirection: 'column',
                gap: '10px',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <strong style={{ fontSize: '14px', color: 'var(--text-primary)', textTransform: 'capitalize' }}>
                  {stepKey.replace(/_/g, ' ')}
                </strong>
                <Badge variant={item.approved ? 'success' : 'neutral'} dot size="sm">
                  {item.approved ? 'Approved' : 'Draft'}
                </Badge>
              </div>

              <div
                style={{
                  backgroundColor: 'var(--bg-app)',
                  padding: '12px',
                  borderRadius: 'var(--radius-md)',
                  border: '1px solid var(--border-subtle)',
                  fontFamily: 'var(--font-mono)',
                  fontSize: '12px',
                  color: 'var(--text-primary)',
                  maxHeight: '180px',
                  overflowY: 'auto',
                }}
              >
                <pre style={{ margin: 0 }}>{JSON.stringify(item.content, null, 2)}</pre>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}