import React, { useState } from 'react'
import {
  ListOrdered,
  Clock,
  CheckCircle2,
  Camera,
  Layers,
  Sparkles,
  Check,
  AlertCircle,
} from 'lucide-react'
import { VideoFactoryProject } from '../../../types/videoFactory'
import { useApproveScenes } from '../../../hooks/useVideoFactory'
import { Badge } from '../../../components/common/Badge'
import { Button } from '../../../components/common/Button'
import { DependencyNotice } from '../../../components/pipeline/DependencyNotice'
import { EmptyState } from '../../../components/common/EmptyState'

interface ScenesStageProps {
  project: VideoFactoryProject
}

export const ScenesStage: React.FC<ScenesStageProps> = ({ project }) => {
  const [notice, setNotice] = useState<{ text: string; ok: boolean } | null>(null)
  const approveScenesMutation = useApproveScenes()

  const isBriefApproved = project.brief_approval === 'approved'
  const isSceneApproved = project.scene_plan_approval === 'approved'
  const scenes = project.scene_plan?.scenes || []

  const totalDuration = scenes.reduce((acc, s) => acc + (s.duration_seconds || 0), 0)
  const isTargetMet = totalDuration === 30

  const handleApprovePlan = async () => {
    setNotice(null)
    try {
      await approveScenesMutation.mutateAsync(project.id)
      setNotice({ text: 'Scene plan created and approved. Storyboard keyframes unlocked.', ok: true })
    } catch (err: any) {
      setNotice({ text: err.message || 'Failed to approve scene plan', ok: false })
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      {!isBriefApproved && <DependencyNotice projectId={project.id} currentStage="scenes" />}

      {/* Overview & Approval Header */}
      <section
        style={{
          padding: '18px 20px',
          backgroundColor: 'var(--bg-panel)',
          border: '1px solid var(--border-default)',
          borderRadius: 'var(--radius-lg)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: '14px',
          opacity: !isBriefApproved ? 0.6 : 1,
          pointerEvents: !isBriefApproved ? 'none' : 'auto',
        }}
      >
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <h3 style={{ fontSize: '15px', fontWeight: 600, color: 'var(--text-primary)' }}>
              30-Second Commercial Scene Structure
            </h3>
            <Badge variant={isSceneApproved ? 'success' : 'neutral'} dot size="md">
              {isSceneApproved ? 'Scene Plan Approved' : 'Plan Draft'}
            </Badge>
          </div>
          <p style={{ fontSize: '12px', color: 'var(--text-secondary)', marginTop: '2px' }}>
            Standard 4-beat rhythm designed for viral vertical video retention (Hook → Use Case → Feature Highlights → CTA).
          </p>
        </div>

        {/* 30s Target Counter & Action */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              padding: '6px 12px',
              backgroundColor: isTargetMet ? 'var(--status-success-bg)' : 'var(--status-running-bg)',
              border: `1px solid ${isTargetMet ? 'var(--status-success-border)' : 'var(--status-running-border)'}`,
              borderRadius: 'var(--radius-md)',
              fontSize: '12px',
              fontFamily: 'var(--font-mono)',
            }}
          >
            <Clock size={14} color={isTargetMet ? 'var(--status-success)' : 'var(--accent-timeline)'} />
            <strong style={{ color: isTargetMet ? 'var(--status-success)' : 'var(--accent-timeline)' }}>
              {totalDuration}s / 30s
            </strong>
            <span style={{ color: 'var(--text-secondary)' }}>
              {isTargetMet ? '(Target Met)' : '(Incomplete)'}
            </span>
          </div>

          <Button
            variant="success"
            size="md"
            icon={<Check size={14} />}
            disabled={!isBriefApproved || isSceneApproved || approveScenesMutation.isPending}
            loading={approveScenesMutation.isPending}
            onClick={handleApprovePlan}
            title="Create and approve the 30s scene plan"
          >
            {isSceneApproved ? 'Scene Plan Approved' : 'Create & Approve 30s Plan'}
          </Button>
        </div>
      </section>

      {notice && (
        <div
          style={{
            padding: '10px 14px',
            backgroundColor: notice.ok ? 'var(--status-success-bg)' : 'var(--status-error-bg)',
            border: `1px solid ${notice.ok ? 'var(--status-success-border)' : 'var(--status-error-border)'}`,
            borderRadius: 'var(--radius-sm)',
            fontSize: '12px',
            color: notice.ok ? 'var(--status-success)' : 'var(--status-error)',
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
          }}
        >
          {notice.ok ? <CheckCircle2 size={14} /> : <AlertCircle size={14} />}
          <span>{notice.text}</span>
        </div>
      )}

      {/* Scenes List */}
      {scenes.length > 0 ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          {scenes.map((scene) => (
            <div
              key={scene.scene_id}
              style={{
                padding: '16px 20px',
                backgroundColor: 'var(--bg-panel)',
                border: '1px solid var(--border-default)',
                borderRadius: 'var(--radius-lg)',
                display: 'grid',
                gridTemplateColumns: '80px 1fr 120px',
                alignItems: 'center',
                gap: '16px',
              }}
              className="scene-row-card"
            >
              {/* Scene Number & Order */}
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start' }}>
                <span style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>
                  Beat {scene.order}
                </span>
                <span
                  style={{
                    fontFamily: 'var(--font-mono)',
                    fontSize: '16px',
                    fontWeight: 700,
                    color: 'var(--accent-primary)',
                  }}
                >
                  #{scene.order}
                </span>
              </div>

              {/* Scene Content & Description */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <h4 style={{ fontSize: '14px', fontWeight: 600, color: 'var(--text-primary)' }}>
                    {scene.title}
                  </h4>
                  <Badge variant="neutral" size="sm">
                    {scene.purpose}
                  </Badge>
                </div>
                <p style={{ fontSize: '13px', color: 'var(--text-secondary)', lineHeight: 1.4 }}>
                  {scene.content}
                </p>

                {/* Camera Intention & Setting */}
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginTop: '4px', fontSize: '11px', color: 'var(--text-muted)' }}>
                  {scene.camera_movement && (
                    <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                      <Camera size={11} color="var(--text-secondary)" /> {scene.camera_movement}
                    </span>
                  )}
                  {scene.setting && (
                    <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                      <Layers size={11} color="var(--text-secondary)" /> {scene.setting}
                    </span>
                  )}
                </div>
              </div>

              {/* Duration Badge */}
              <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                <Badge variant="timeline" size="md">
                  {scene.duration_seconds} seconds
                </Badge>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <EmptyState
          icon={ListOrdered}
          title="Scene Plan Not Created Yet"
          description="Click 'Create & Approve 30s Plan' above to generate the structured 4-scene timeline beats according to the approved Creative Brief."
          actionLabel={isBriefApproved ? 'Create 30s Scene Plan' : undefined}
          onAction={handleApprovePlan}
        />
      )}
    </div>
  )
}
