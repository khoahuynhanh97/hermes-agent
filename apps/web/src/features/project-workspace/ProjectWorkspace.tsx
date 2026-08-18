import React, { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  StageKey,
  StoryboardFrame,
  GeneratedScene,
  CANONICAL_STAGES,
} from '../../types/videoFactory'
import { useProjectDetail, useProjectsList } from '../../hooks/useVideoFactory'
import { useJobPoller } from '../../hooks/useJobs'
import { WorkflowHeader } from '../../components/pipeline/WorkflowHeader'
import { PipelineStepper } from '../../components/pipeline/PipelineStepper'
import { WorkflowFooter } from '../../components/pipeline/WorkflowFooter'
import { InspectorPanel } from '../../components/common/InspectorPanel'
import { MediaViewerModal } from '../../components/common/MediaViewerModal'
import { Badge } from '../../components/common/Badge'
import { Button } from '../../components/common/Button'
import { deriveActiveStage } from '../../utils/stageDerivation'

// Stages
import { ResourcesStage } from './stages/ResourcesStage'
import { BriefStage } from './stages/BriefStage'
import { ScenesStage } from './stages/ScenesStage'
import { StoryboardStage } from './stages/StoryboardStage'
import { GenerationStage } from './stages/GenerationStage'
import { TimelineStage } from './stages/TimelineStage'
import { ExportStage } from './stages/ExportStage'

import './ProjectWorkspace.css'
import { useSession } from '../../context/SessionContext'

export const ProjectWorkspace: React.FC = () => {
  const { projectId, stage } = useParams<{ projectId: string; stage?: string }>()
  const navigate = useNavigate()
  const { authenticated, ownerUserId, isLoading: sessionLoading } = useSession()
  const [inspectorOpen, setInspectorOpen] = useState(false)
  const [inspectorContent, setInspectorContent] = useState<{
    type: 'frame' | 'scene' | 'lock'
    title: string
    subtitle?: string
    data: any
  } | null>(null)
  const [activeJobId, setActiveJobId] = useState<string | null>(null)
  const [mediaInspectId, setMediaInspectId] = useState<string | null>(null)

  const { data: projectRes, isLoading, isFetching, refetch } = useProjectDetail(projectId)
  const { data: listRes } = useProjectsList()

  const project = projectRes?.data || null
  const projectsList = listRes?.data || []

  // Job Polling
  const { job: polledJob } = useJobPoller(activeJobId, () => {
    refetch()
  })

  // Canonical stage validation & normalization
  const currentStage: StageKey = (
    stage && CANONICAL_STAGES.some((s) => s.key === stage) ? stage : 'resources'
  ) as StageKey

  // If no stage in URL, redirect to active stage
  useEffect(() => {
    if (projectId && !stage && project) {
      const target = deriveActiveStage(project)
      navigate(`/projects/${encodeURIComponent(projectId)}/workflow/${target}`, { replace: true })
    }
  }, [projectId, stage, project])

  const handleSelectFrame = (frame: StoryboardFrame) => {
    setInspectorContent({
      type: 'frame',
      title: `Beat #${frame.order}: ${frame.label}`,
      subtitle: `Frame Prompt & Visual Constraints`,
      data: frame,
    })
    setInspectorOpen(true)
  }

  const handleSelectScene = (scene: GeneratedScene) => {
    setInspectorContent({
      type: 'scene',
      title: `Scene: ${scene.scene_id}`,
      subtitle: `Video Synthesis Prompt & QC`,
      data: scene,
    })
    setInspectorOpen(true)
  }

  const renderStageContent = () => {
    if (!project) return null

    switch (currentStage) {
      case 'resources':
        return (
          <ResourcesStage
            project={project}
            onInspectAsset={(id) => setMediaInspectId(id)}
          />
        )
      case 'brief':
        return <BriefStage project={project} />
      case 'scenes':
        return <ScenesStage project={project} />
      case 'storyboard':
        return (
          <StoryboardStage
            project={project}
            onInspectAsset={(id) => setMediaInspectId(id)}
            onSelectFrameForInspector={handleSelectFrame}
            onTrackJob={(id) => setActiveJobId(id)}
          />
        )
      case 'generation':
        return (
          <GenerationStage
            project={project}
            onInspectAsset={(id) => setMediaInspectId(id)}
            onSelectSceneForInspector={handleSelectScene}
          />
        )
      case 'timeline':
        return (
          <TimelineStage
            project={project}
            onInspectAsset={(id) => setMediaInspectId(id)}
            onTrackJob={(id) => setActiveJobId(id)}
          />
        )
      case 'export':
        return (
          <ExportStage
            project={project}
            onInspectAsset={(id) => setMediaInspectId(id)}
            onTrackJob={(id) => setActiveJobId(id)}
          />
        )
      default:
        return null
    }
  }

  if (isLoading && !project) {
    return (
      <div className="workspace-loading-screen">
        <div className="spinner-indicator" />
        <span>Loading Project Workspace...</span>
      </div>
    )
  }

  if (!project && !isLoading) {
    return (
      <div className="workspace-not-found">
        <h3>Project '{projectId}' Not Found</h3>
        <p>The requested project workspace does not exist or has not been initialized.</p>
        <Button variant="primary" onClick={() => navigate('/projects')}>
          Return to Projects
        </Button>
      </div>
    )
  }

  return (
    <div className="project-workspace-container">
      {/* Header */}
      <WorkflowHeader
        project={project}
        currentStage={currentStage}
        projectsList={projectsList}
        isRefreshing={isFetching}
        inspectorOpen={inspectorOpen}
        onToggleInspector={() => setInspectorOpen(!inspectorOpen)}
        onRefresh={() => refetch()}
      />

      {/* 7-Stage Stepper Navigation */}
      {projectId && (
        <PipelineStepper
          projectId={projectId}
          currentStage={currentStage}
          project={project}
          activeJobTask={polledJob?.task_name}
        />
      )}

      {/* Main Split Workbench */}
      <div className="workspace-main-split">
        {/* Stage Content Canvas */}
        <main className="workspace-canvas">
          {renderStageContent()}
        </main>

        {/* Context Inspector Panel */}
        <InspectorPanel
          title={inspectorContent?.title}
          subtitle={inspectorContent?.subtitle}
          isOpen={inspectorOpen}
          onClose={() => setInspectorOpen(false)}
        >
          {inspectorContent?.type === 'frame' && (
            <div className="inspector-details-flow">
              <div>
                <span className="inspector-label">POSITIVE PROMPT</span>
                <div className="inspector-code-block">
                  {inspectorContent.data.prompt?.positive_prompt || 'No prompt specified'}
                </div>
              </div>

              <div>
                <span className="inspector-label">IDENTITY CONSTRAINTS</span>
                <div className="inspector-code-block">
                  {inspectorContent.data.prompt?.product_identity_constraints || 'None'}
                </div>
              </div>

              <div>
                <span className="inspector-label">NEGATIVE CONSTRAINTS</span>
                <div className="inspector-code-block">
                  {inspectorContent.data.prompt?.negative_constraints || 'No geometry changes, no invented typography'}
                </div>
              </div>

              <div className="inspector-meta-row">
                <div>
                  <span className="inspector-label">ASPECT RATIO</span>
                  <Badge variant="neutral">{inspectorContent.data.prompt?.aspect_ratio || '9:16'}</Badge>
                </div>
                <div>
                  <span className="inspector-label">GENERATION STATUS</span>
                  <Badge variant="active">{inspectorContent.data.generation_status}</Badge>
                </div>
              </div>
            </div>
          )}

          {inspectorContent?.type === 'scene' && (
            <div className="inspector-details-flow">
              <div>
                <span className="inspector-label">START / END VISUAL STATE</span>
                <div className="inspector-code-block">
                  {inspectorContent.data.video_prompt?.start_visual_state || 'None'}
                </div>
              </div>

              <div>
                <span className="inspector-label">CAMERA MOVEMENT & FRAMING</span>
                <div className="inspector-code-block">
                  {inspectorContent.data.video_prompt?.camera_movement} • {inspectorContent.data.video_prompt?.camera_framing}
                </div>
              </div>

              <div>
                <span className="inspector-label">NEGATIVE MOTION CONSTRAINTS</span>
                <div className="inspector-code-block">
                  {inspectorContent.data.video_prompt?.negative_constraints || 'No text, no morphing'}
                </div>
              </div>

              <div className="inspector-meta-row">
                <div>
                  <span className="inspector-label">DURATION</span>
                  <Badge variant="timeline">{inspectorContent.data.video_prompt?.duration_seconds || 8}s</Badge>
                </div>
                <div>
                  <span className="inspector-label">STATUS</span>
                  <Badge variant="success">{inspectorContent.data.generation_status}</Badge>
                </div>
              </div>
            </div>
          )}
        </InspectorPanel>
      </div>

      {/* Fixed Footer */}
      {projectId && (
        <WorkflowFooter
          projectId={projectId}
          currentStage={currentStage}
          project={project}
          activeJob={polledJob}
        />
      )}

      {/* Media Inspection Modal */}
      <MediaViewerModal
        assetId={mediaInspectId}
        onClose={() => setMediaInspectId(null)}
      />
    </div>
  )
}
