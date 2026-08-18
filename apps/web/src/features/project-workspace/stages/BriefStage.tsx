import React, { useState, useEffect } from 'react'
import {
  FileText,
  CheckCircle2,
  Save,
  Check,
  AlertCircle,
  Layers,
  Sparkles,
} from 'lucide-react'
import { VideoFactoryProject } from '../../../types/videoFactory'
import { useSaveBrief, useApproveBrief } from '../../../hooks/useVideoFactory'
import { Badge } from '../../../components/common/Badge'
import { Button } from '../../../components/common/Button'
import { DependencyNotice } from '../../../components/pipeline/DependencyNotice'

interface BriefStageProps {
  project: VideoFactoryProject
}

export const BriefStage: React.FC<BriefStageProps> = ({ project }) => {
  const [objective, setObjective] = useState('')
  const [targetAudience, setTargetAudience] = useState('')
  const [coreMessage, setCoreMessage] = useState('')
  const [saveNotice, setSaveNotice] = useState<{ text: string; ok: boolean } | null>(null)

  const saveMutation = useSaveBrief()
  const approveMutation = useApproveBrief()

  const brief = project.creative_brief
  const isApproved = project.brief_approval === 'approved'
  const isBlocked = !project.resource_pack

  useEffect(() => {
    if (brief) {
      setObjective(brief.objective || '')
      setTargetAudience(brief.target_audience || '')
      setCoreMessage(brief.core_message || '')
    } else if (project.resource_pack) {
      // Default initial objective from product identity
      const desc = project.resource_pack.product_identity_description || 'Product'
      setObjective(`High-converting 30s TikTok/Reels review showcasing ${desc}`)
      setTargetAudience('Tech-savvy everyday consumers looking for reliable audio')
      setCoreMessage(`Experience premium audio clarity, long battery life, and ergonomic comfort with ${desc}.`)
    }
  }, [project.id, brief, project.resource_pack])

  const handleSave = async () => {
    setSaveNotice(null)
    try {
      await saveMutation.mutateAsync({
        projectId: project.id,
        objective: objective.trim(),
        targetAudience: targetAudience.trim(),
        coreMessage: coreMessage.trim(),
      })
      setSaveNotice({ text: 'Creative Brief saved successfully.', ok: true })
    } catch (err: any) {
      setSaveNotice({ text: err.message || 'Failed to save brief', ok: false })
    }
  }

  const handleApprove = async () => {
    setSaveNotice(null)
    try {
      await approveMutation.mutateAsync(project.id)
      setSaveNotice({ text: 'Creative Brief approved. Scene Plan unlocked.', ok: true })
    } catch (err: any) {
      setSaveNotice({ text: err.message || 'Failed to approve brief', ok: false })
    }
  }

  const hasFormChanges =
    objective !== (brief?.objective || '') ||
    targetAudience !== (brief?.target_audience || '') ||
    coreMessage !== (brief?.core_message || '')

  const isFormValid = objective.trim().length > 0 && targetAudience.trim().length > 0 && coreMessage.trim().length > 0

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      {isBlocked && <DependencyNotice projectId={project.id} currentStage="brief" />}

      <section
        style={{
          padding: '20px',
          backgroundColor: 'var(--bg-panel)',
          border: '1px solid var(--border-default)',
          borderRadius: 'var(--radius-lg)',
          display: 'flex',
          flexDirection: 'column',
          gap: '18px',
          opacity: isBlocked ? 0.6 : 1,
          pointerEvents: isBlocked ? 'none' : 'auto',
        }}
      >
        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '10px' }}>
          <div>
            <h3 style={{ fontSize: '15px', fontWeight: 600, color: 'var(--text-primary)' }}>
              Creative Brief & Narrative Direction
            </h3>
            <p style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
              Define the strategic goals, target audience persona, and core hook message for this 30s video.
            </p>
          </div>

          <Badge variant={isApproved ? 'success' : 'neutral'} dot size="md">
            {isApproved ? 'Brief Approved' : 'Draft Mode'}
          </Badge>
        </div>

        {saveNotice && (
          <div
            style={{
              padding: '10px 14px',
              backgroundColor: saveNotice.ok ? 'var(--status-success-bg)' : 'var(--status-error-bg)',
              border: `1px solid ${saveNotice.ok ? 'var(--status-success-border)' : 'var(--status-error-border)'}`,
              borderRadius: 'var(--radius-sm)',
              fontSize: '12px',
              color: saveNotice.ok ? 'var(--status-success)' : 'var(--status-error)',
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
            }}
          >
            {saveNotice.ok ? <CheckCircle2 size={14} /> : <AlertCircle size={14} />}
            <span>{saveNotice.text}</span>
          </div>
        )}

        {/* Brief Fields */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
          {/* Objective */}
          <div>
            <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '6px' }}>
              Strategic Objective *
            </label>
            <input
              type="text"
              placeholder="e.g. Highlight ANC performance and ergonomic design for commuters"
              value={objective}
              onChange={(e) => setObjective(e.target.value)}
              style={{ width: '100%' }}
            />
            {!objective.trim() && (
              <span style={{ fontSize: '11px', color: 'var(--status-error)', marginTop: '4px', display: 'block' }}>
                Objective is required.
              </span>
            )}
          </div>

          {/* Target Audience */}
          <div>
            <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '6px' }}>
              Target Audience *
            </label>
            <input
              type="text"
              placeholder="e.g. Young professionals, students, mobile gaming and music listeners"
              value={targetAudience}
              onChange={(e) => setTargetAudience(e.target.value)}
              style={{ width: '100%' }}
            />
            {!targetAudience.trim() && (
              <span style={{ fontSize: '11px', color: 'var(--status-error)', marginTop: '4px', display: 'block' }}>
                Target audience is required.
              </span>
            )}
          </div>

          {/* Core Message */}
          <div>
            <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '6px' }}>
              Core Message / Script Tone *
            </label>
            <textarea
              rows={3}
              placeholder="e.g. Punchy, confident product review focusing on sound immersion and seamless portability..."
              value={coreMessage}
              onChange={(e) => setCoreMessage(e.target.value)}
              style={{ width: '100%', resize: 'vertical' }}
            />
            {!coreMessage.trim() && (
              <span style={{ fontSize: '11px', color: 'var(--status-error)', marginTop: '4px', display: 'block' }}>
                Core message is required.
              </span>
            )}
          </div>

          {/* Canonical Content Blocks */}
          <div style={{ paddingTop: '8px', borderTop: '1px solid var(--border-subtle)' }}>
            <span style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-primary)', display: 'block', marginBottom: '8px' }}>
              Standard 30s Content Blocks
            </span>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
              {(brief?.content_blocks || ['Hook (0-6s)', 'Use Case (6-14s)', 'Highlights (14-22s)', 'Call to Action (22-30s)']).map(
                (block, idx) => (
                  <div
                    key={idx}
                    style={{
                      padding: '4px 10px',
                      backgroundColor: 'var(--bg-surface)',
                      border: '1px solid var(--border-default)',
                      borderRadius: 'var(--radius-sm)',
                      fontSize: '12px',
                      color: 'var(--text-secondary)',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '6px',
                    }}
                  >
                    <span style={{ color: 'var(--accent-primary)', fontWeight: 600 }}>{idx + 1}.</span>
                    <span>{block}</span>
                  </div>
                )
              )}
            </div>
          </div>
        </div>

        {/* Action Buttons: Distinct Save and Approve Commands */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'flex-end',
            gap: '12px',
            paddingTop: '14px',
            borderTop: '1px solid var(--border-subtle)',
          }}
        >
          <Button
            variant="secondary"
            size="md"
            icon={<Save size={14} />}
            disabled={!isFormValid || saveMutation.isPending}
            loading={saveMutation.isPending}
            onClick={handleSave}
            title="Save changes to Creative Brief"
          >
            Save Brief
          </Button>

          <Button
            variant="success"
            size="md"
            icon={<Check size={14} />}
            disabled={!brief || isApproved || approveMutation.isPending}
            loading={approveMutation.isPending}
            onClick={handleApprove}
            title="Approve Brief to unlock Scene Plan"
          >
            {isApproved ? 'Brief Approved' : 'Approve Brief'}
          </Button>
        </div>
      </section>
    </div>
  )
}
