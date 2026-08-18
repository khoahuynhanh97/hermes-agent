import React from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  Film,
  Package,
  CheckCircle2,
  Clock,
  ArrowRight,
  Plus,
  RefreshCw,
} from 'lucide-react'
import { useProjectsList } from '../../hooks/useVideoFactory'
import { useProductsList } from '../../hooks/useProducts'
import { useSession } from '../../context/SessionContext'
import { Badge, BadgeVariant } from '../../components/common/Badge'
import { Button } from '../../components/common/Button'
import './DashboardPage.css'

export const DashboardPage: React.FC = () => {
  const navigate = useNavigate()
  const { ownerUserId } = useSession()
  const { data: projectsRes, isLoading: loadingProjects, refetch: refetchProjects } = useProjectsList()
  const { data: productsRes, isLoading: loadingProducts } = useProductsList()

  const projects = projectsRes?.data || []
  const products = productsRes?.products || []

  const completedProjects = projects.filter((p) => p.status === 'ready_to_publish' || p.status === 'completed')
  const activeProjects = projects.filter((p) => p.status !== 'ready_to_publish' && p.status !== 'completed')

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

  return (
    <div className="dashboard-container">
      {/* Top Header */}
      <div className="dashboard-topbar">
        <div>
          <h1 style={{ fontSize: '20px', fontWeight: 600, color: 'var(--text-primary)' }}>
            Hermes Operational Control Plane
          </h1>
          <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginTop: '2px' }}>
            Autonomous AI Video Pipeline • Product Intelligence Orchestration
          </p>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <Button
            variant="outline"
            size="sm"
            icon={<RefreshCw size={13} />}
            onClick={() => refetchProjects()}
          >
            Refresh
          </Button>

          <Button
            variant="primary"
            size="sm"
            icon={<Plus size={14} />}
            onClick={() => navigate('/projects')}
          >
            New Project
          </Button>
        </div>
      </div>

      {/* Real Derived Metrics */}
      <div className="dashboard-metrics-grid">
        <div className="metric-box">
          <div className="metric-header">
            <span className="metric-label">TOTAL WORKSPACES</span>
            <Film size={16} color="var(--accent-primary)" />
          </div>
          <div className="metric-number">{projects.length}</div>
          <span className="metric-subtext">Active Video Factory projects</span>
        </div>

        <div className="metric-box">
          <div className="metric-header">
            <span className="metric-label">LOCKED PRODUCTS</span>
            <Package size={16} color="var(--status-success)" />
          </div>
          <div className="metric-number">{products.length}</div>
          <span className="metric-subtext">Verified ResourcePackLocks</span>
        </div>

        <div className="metric-box">
          <div className="metric-header">
            <span className="metric-label">COMPLETED MASTERS</span>
            <CheckCircle2 size={16} color="var(--status-success)" />
          </div>
          <div className="metric-number">{completedProjects.length}</div>
          <span className="metric-subtext">Ready to publish</span>
        </div>

        <div className="metric-box">
          <div className="metric-header">
            <span className="metric-label">IN PIPELINE</span>
            <Clock size={16} color="var(--accent-timeline)" />
          </div>
          <div className="metric-number">{activeProjects.length}</div>
          <span className="metric-subtext">Drafts in active production</span>
        </div>
      </div>

      {/* Recent Production Workspaces Table */}
      <div className="dashboard-table-card">
        <div className="table-card-header">
          <div>
            <h3 style={{ fontSize: '14px', fontWeight: 600, color: 'var(--text-primary)' }}>
              Recent Production Pipelines
            </h3>
            <p style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
              Continue working directly in active project workspaces
            </p>
          </div>

          <Link to="/projects" style={{ fontSize: '12px', color: 'var(--accent-primary)', display: 'flex', alignItems: 'center', gap: '4px' }}>
            <span>View All ({projects.length})</span>
            <ArrowRight size={13} />
          </Link>
        </div>

        <div className="table-container">
          <table className="production-data-table">
            <thead>
              <tr>
                <th>Project Workspace ID</th>
                <th>Pipeline Format</th>
                <th>Status</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {projects.length === 0 ? (
                <tr>
                  <td colSpan={4} style={{ textAlign: 'center', padding: '32px', color: 'var(--text-muted)' }}>
                    No production projects yet. Create a project to begin.
                  </td>
                </tr>
              ) : (
                projects.slice(0, 5).map((p) => (
                  <tr key={p.id}>
                    <td>
                      <strong style={{ color: 'var(--text-primary)' }}>{p.id}</strong>
                    </td>
                    <td>
                      <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                        30s Commercial Video (9:16)
                      </span>
                    </td>
                    <td>
                      <Badge variant={getStatusVariant(p.status)} dot size="sm">
                        {p.status.replace(/_/g, ' ')}
                      </Badge>
                    </td>
                    <td>
                      <Button
                        variant="outline"
                        size="sm"
                        icon={<ArrowRight size={12} />}
                        onClick={() => navigate(`/projects/${encodeURIComponent(p.id)}/workflow/resources`)}
                      >
                        Continue Pipeline
                      </Button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
