import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  RefreshCw,
  Lock,
  ChevronDown,
  Search,
  ExternalLink,
  Sliders,
  FolderGit2,
} from 'lucide-react'
import { VideoFactoryProject, ProjectSummary, StageKey } from '../../types/videoFactory'
import { Badge, BadgeVariant } from '../common/Badge'
import { Button } from '../common/Button'
import { formatDigest } from '../../utils/formatters'

interface WorkflowHeaderProps {
  project: VideoFactoryProject | null
  currentStage: StageKey
  projectsList: ProjectSummary[]
  isRefreshing?: boolean
  inspectorOpen?: boolean
  onToggleInspector?: () => void
  onRefresh: () => void
}

export const WorkflowHeader: React.FC<WorkflowHeaderProps> = ({
  project,
  currentStage,
  projectsList,
  isRefreshing = false,
  inspectorOpen = false,
  onToggleInspector,
  onRefresh,
}) => {
  const navigate = useNavigate()
  const [dropdownOpen, setDropdownOpen] = useState(false)
  const [searchFilter, setSearchFilter] = useState('')

  const filteredProjects = projectsList.filter((p) =>
    p.id.toLowerCase().includes(searchFilter.toLowerCase())
  )

  const getStatusVariant = (status?: string): BadgeVariant => {
    switch (status?.toLowerCase()) {
      case 'ready_to_publish':
      case 'completed':
        return 'success'
      case 'in_progress':
      case 'active':
        return 'active'
      case 'running':
        return 'running'
      case 'failed':
        return 'error'
      default:
        return 'neutral'
    }
  }

  const handleSelectProject = (projectId: string) => {
    setDropdownOpen(false)
    setSearchFilter('')
    navigate(`/projects/${encodeURIComponent(projectId)}/workflow/${currentStage}`)
  }

  const resourcePack = project?.resource_pack
  const productName = resourcePack?.product_identity_description || project?.id || 'Untitled Project'

  return (
    <header
      className="workflow-header"
      style={{
        padding: '10px 20px',
        backgroundColor: 'var(--bg-panel)',
        borderBottom: '1px solid var(--border-default)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        flexWrap: 'wrap',
        gap: '12px',
      }}
    >
      {/* Left: Project Selector & Info */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '14px', position: 'relative' }}>
        {/* Project Switcher Dropdown */}
        <div style={{ position: 'relative' }}>
          <button
            onClick={() => setDropdownOpen(!dropdownOpen)}
            className="project-picker-btn"
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              padding: '6px 12px',
              backgroundColor: 'var(--bg-surface)',
              border: '1px solid var(--border-default)',
              borderRadius: 'var(--radius-md)',
              color: 'var(--text-primary)',
              fontWeight: 600,
              fontSize: '13px',
              transition: 'all 0.15s ease',
            }}
            title="Switch project"
          >
            <FolderGit2 size={15} color="var(--accent-primary)" />
            <span style={{ maxWidth: '200px' }} className="truncate">
              {project?.id || 'Select Project'}
            </span>
            <ChevronDown size={14} color="var(--text-muted)" />
          </button>

          {dropdownOpen && (
            <div
              style={{
                position: 'absolute',
                top: '100%',
                left: 0,
                marginTop: '6px',
                width: '320px',
                backgroundColor: 'var(--bg-panel)',
                border: '1px solid var(--border-strong)',
                borderRadius: 'var(--radius-lg)',
                boxShadow: 'var(--shadow-lg)',
                zIndex: 100,
                overflow: 'hidden',
              }}
            >
              <div style={{ padding: '8px', borderBottom: '1px solid var(--border-subtle)' }}>
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '6px',
                    backgroundColor: 'var(--bg-input)',
                    padding: '4px 8px',
                    borderRadius: 'var(--radius-sm)',
                    border: '1px solid var(--border-default)',
                  }}
                >
                  <Search size={13} color="var(--text-muted)" />
                  <input
                    type="text"
                    placeholder="Search projects..."
                    value={searchFilter}
                    onChange={(e) => setSearchFilter(e.target.value)}
                    autoFocus
                    style={{
                      border: 'none',
                      background: 'none',
                      padding: 0,
                      fontSize: '12px',
                      color: 'var(--text-primary)',
                      outline: 'none',
                      width: '100%',
                    }}
                  />
                </div>
              </div>

              <div style={{ maxHeight: '240px', overflowY: 'auto', padding: '4px' }}>
                {filteredProjects.length === 0 ? (
                  <div style={{ padding: '12px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '12px' }}>
                    No matching projects found
                  </div>
                ) : (
                  filteredProjects.map((p) => (
                    <div
                      key={p.id}
                      onClick={() => handleSelectProject(p.id)}
                      style={{
                        padding: '8px 10px',
                        borderRadius: 'var(--radius-sm)',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        cursor: 'pointer',
                        backgroundColor: p.id === project?.id ? 'var(--bg-surface-active)' : 'transparent',
                      }}
                      className="dropdown-item-hover"
                    >
                      <div style={{ display: 'flex', flexDirection: 'column', minWidth: 0 }}>
                        <span style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-primary)' }} className="truncate">
                          {p.id}
                        </span>
                        <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Status: {p.status}</span>
                      </div>
                      {p.id === project?.id && (
                        <span style={{ width: '6px', height: '6px', borderRadius: '50%', backgroundColor: 'var(--accent-primary)' }} />
                      )}
                    </div>
                  ))
                )}
              </div>
            </div>
          )}
        </div>

        {/* Project Meta Titles */}
        {project && (
          <div style={{ display: 'flex', flexDirection: 'column' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span style={{ fontSize: '14px', fontWeight: 600, color: 'var(--text-primary)' }}>
                {productName}
              </span>
              <Badge variant={getStatusVariant(project.status)} dot size="sm">
                {project.status.replace(/_/g, ' ')}
              </Badge>
            </div>

            {/* Resource Pack Lock Indicator */}
            {resourcePack ? (
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '11px', color: 'var(--text-muted)' }}>
                <Lock size={11} color="var(--status-success)" />
                <span>Lock: <strong style={{ color: 'var(--text-secondary)' }}>{resourcePack.id}</strong></span>
                <span>•</span>
                <span>{resourcePack.product_references?.length || 0} Assets</span>
              </div>
            ) : (
              <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                No Resource Pack bound yet
              </span>
            )}
          </div>
        )}
      </div>

      {/* Right: Actions */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
        <Button
          variant="outline"
          size="sm"
          icon={<RefreshCw size={13} className={isRefreshing ? 'animate-spin' : ''} />}
          onClick={onRefresh}
          title="Refresh project data"
        >
          Refresh
        </Button>

        {onToggleInspector && (
          <Button
            variant={inspectorOpen ? 'primary' : 'outline'}
            size="sm"
            icon={<Sliders size={13} />}
            onClick={onToggleInspector}
            title="Toggle context inspector panel"
          >
            Inspector
          </Button>
        )}
      </div>
    </header>
  )
}
