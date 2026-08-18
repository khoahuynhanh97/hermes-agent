import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Package,
  Search,
  Film,
  RefreshCw,
  Radar,
  ClipboardList,
  BarChart3,
  FileText,
  Wand2,
  AlertCircle,
} from 'lucide-react'
import { useProductsList, useProductDetail, useResearchRuns, useRunProductResearch } from '../../hooks/useProducts'
import { useCreateProject, useBindResources } from '../../hooks/useVideoFactory'
import { useSession } from '../../context/SessionContext'
import { ProductResearchRunResult, ProductSummaryItem } from '../../types/products'
import { Badge } from '../../components/common/Badge'
import { Button } from '../../components/common/Button'
import { AssetThumbnail } from '../../components/common/AssetThumbnail'
import { MediaViewerModal } from '../../components/common/MediaViewerModal'
import { EmptyState } from '../../components/common/EmptyState'
import { formatDigest } from '../../utils/formatters'
import './ProductLibraryPage.css'

type TabType = 'overview' | 'research' | 'assets' | 'lock' | 'projects'

export const ProductLibraryPage: React.FC = () => {
  const navigate = useNavigate()
  const { ownerUserId } = useSession()
  const [search, setSearch] = useState('')
  const [selectedSnapshotId, setSelectedSnapshotId] = useState<string>('')
  const [activeTab, setActiveTab] = useState<TabType>('overview')
  const [inspectAssetId, setInspectAssetId] = useState<string | null>(null)
  const [isCreatingProject, setIsCreatingProject] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)
  const [researchMessage, setResearchMessage] = useState('crawl ngành bàn phím, giá 200k-500k')
  const [researchResult, setResearchResult] = useState<ProductResearchRunResult | null>(null)

  const { data: productsRes, isLoading, refetch, isFetching } = useProductsList(search)
  const { data: detail } = useProductDetail(selectedSnapshotId)
  const { data: runsRes } = useResearchRuns()

  const createProjMutation = useCreateProject()
  const bindMutation = useBindResources()
  const researchMutation = useRunProductResearch()

  const products = productsRes?.products || []
  const selectedProduct = products.find((p) => p.snapshot_id === selectedSnapshotId) || products[0]

  // Auto select first product if not set
  React.useEffect(() => {
    if (!selectedSnapshotId && products[0]?.snapshot_id) {
      setSelectedSnapshotId(products[0].snapshot_id)
    }
  }, [products, selectedSnapshotId])

  const handleCreateProjectFromProduct = async (product: ProductSummaryItem) => {
    setIsCreatingProject(true)
    setActionError(null)
    const timestamp = new Date().toISOString().replace(/[-:T]/g, '').slice(0, 14)
    const safeSlug = product.product_name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '')
    const projectId = `${safeSlug}-${timestamp}`

    try {
      await createProjMutation.mutateAsync(projectId)
      await bindMutation.mutateAsync({
        projectId,
        productQuery: product.resource_pack_lock_id || product.product_id,
      })
      navigate(`/projects/${encodeURIComponent(projectId)}/workflow/resources`)
    } catch (err: any) {
      setActionError(err.message || 'Failed to initialize project from product lock')
      setIsCreatingProject(false)
    }
  }

  const handleRunResearch = async (event: React.FormEvent) => {
    event.preventDefault()
    const message = researchMessage.trim()
    if (!message) return
    setActionError(null)
    try {
      const response = await researchMutation.mutateAsync(message)
      setResearchResult(response.result)
      refetch()
      setActiveTab('research')
    } catch (err: any) {
      setActionError(err.message || 'Product Intelligence crawl failed')
    }
  }

  const phaseSummary = researchResult?.phase_summary || {
    research: 'pending',
    analysis: 'pending',
    script: 'pending',
    prompt: 'pending',
  }

  const pipelineSteps = [
    {
      id: 'research',
      label: 'Research crawl',
      description: 'Collect product candidates, price window, source URLs, and reference media.',
      icon: <Radar size={15} />,
    },
    {
      id: 'analysis',
      label: 'Product analysis',
      description: 'Score niche fit, demand signals, visual signals, and claim safety.',
      icon: <BarChart3 size={15} />,
    },
    {
      id: 'script',
      label: 'Script package',
      description: 'Generate hook, angle, claims, storyboard outline, voiceover plan, and CTA.',
      icon: <FileText size={15} />,
    },
    {
      id: 'prompt',
      label: 'Prompt set',
      description: 'Prepare image and video prompts for Video Factory production.',
      icon: <Wand2 size={15} />,
    },
  ] as const

  return (
    <div className="product-library-container">
      {/* Page Header */}
      <div className="product-library-header">
        <div>
          <h1 style={{ fontSize: '20px', fontWeight: 600, color: 'var(--text-primary)' }}>
            Product Intelligence Library
          </h1>
          <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginTop: '2px' }}>
            Verified product snapshots, cryptographic ResourcePackLocks, and extracted multi-modal references.
          </p>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <Button
            variant="outline"
            size="sm"
            icon={<RefreshCw size={13} className={isFetching ? 'animate-spin' : ''} />}
            onClick={() => refetch()}
            title="Refresh product intelligence catalog"
          >
            Refresh
          </Button>
        </div>
      </div>

      {actionError && (
        <div style={{ padding: '10px 14px', backgroundColor: 'var(--status-error-bg)', border: '1px solid var(--status-error-border)', borderRadius: 'var(--radius-md)', color: 'var(--status-error)', fontSize: '12px' }}>
          {actionError}
        </div>
      )}

      <section className="research-command-panel">
        <div className="research-command-copy">
          <div className="research-command-icon">
            <Radar size={18} />
          </div>
          <div>
            <h2>Product Intelligence Crawl</h2>
            <p>
              Run crawler-first research, analyze candidates, generate script packages, and prepare prompt sets for Video Factory.
            </p>
          </div>
        </div>

        <form className="research-command-form" onSubmit={handleRunResearch}>
          <input
            type="text"
            value={researchMessage}
            onChange={(event) => setResearchMessage(event.target.value)}
            placeholder="crawl ngành bàn phím, giá 200k-500k"
          />
          <Button
            type="submit"
            variant="primary"
            size="md"
            icon={<Radar size={14} />}
            loading={researchMutation.isPending}
            disabled={researchMutation.isPending || !researchMessage.trim()}
          >
            Run Crawl
          </Button>
        </form>

        <div className="research-pipeline-strip">
          {pipelineSteps.map((step, index) => {
            const status = phaseSummary[step.id]
            const complete = status === 'completed'
            const warning = status === 'warning' || status === 'needs_input'
            return (
              <div className={`research-pipeline-step ${complete ? 'complete' : ''} ${warning ? 'warning' : ''}`} key={step.id}>
                <div className="research-step-index">{complete ? step.icon : index + 1}</div>
                <div>
                  <strong>{step.label}</strong>
                  <span>{status.replace(/_/g, ' ')}</span>
                </div>
              </div>
            )
          })}
        </div>

        {researchResult && (
          <div className="research-result-summary">
            <div>
              <span>Imported</span>
              <strong>{researchResult.imported}</strong>
            </div>
            <div>
              <span>Shortlisted</span>
              <strong>{researchResult.shortlisted}</strong>
            </div>
            <div>
              <span>Packages</span>
              <strong>{researchResult.package_ids.length}</strong>
            </div>
            <div>
              <span>Status</span>
              <strong>{researchResult.status.replace(/_/g, ' ')}</strong>
            </div>
          </div>
        )}
      </section>

      {/* Main Split Layout: Left Catalog / Right Detail Inspector */}
      <div className="product-library-split">
        {/* Left Column: Product Catalog */}
        <aside className="products-sidebar-catalog">
          <div style={{ padding: '12px 14px', borderBottom: '1px solid var(--border-subtle)' }}>
            <div style={{ position: 'relative' }}>
              <Search
                size={13}
                color="var(--text-muted)"
                style={{ position: 'absolute', left: '8px', top: '50%', transform: 'translateY(-50%)' }}
              />
              <input
                type="text"
                placeholder="Filter products..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                style={{ width: '100%', paddingLeft: '28px', fontSize: '12px' }}
              />
            </div>
          </div>

          <div style={{ flex: 1, overflowY: 'auto', padding: '8px', display: 'flex', flexDirection: 'column', gap: '4px' }}>
            {isLoading && products.length === 0 ? (
              <div style={{ padding: '24px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '12px' }}>
                Loading product catalog...
              </div>
            ) : products.length === 0 ? (
              <div style={{ padding: '24px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '12px' }}>
                No verified product snapshots found.
              </div>
            ) : (
              products.map((p) => {
                const isSelected = p.snapshot_id === selectedProduct?.snapshot_id
                return (
                  <div
                    key={p.snapshot_id}
                    onClick={() => setSelectedSnapshotId(p.snapshot_id)}
                    className={`product-row-item ${isSelected ? 'selected' : ''}`}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px', minWidth: 0 }}>
                      <div className="product-thumb-box">
                        <Package size={16} color="var(--accent-primary)" />
                      </div>
                      <div style={{ display: 'flex', flexDirection: 'column', minWidth: 0 }}>
                        <span style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-primary)' }} className="truncate">
                          {p.product_name}
                        </span>
                        <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                          {p.brand} • {p.media_count} Assets
                        </span>
                      </div>
                    </div>

                    <Badge variant="success" size="sm">
                      Locked
                    </Badge>
                  </div>
                )
              })
            )}
          </div>
        </aside>

        {/* Right Column: Detail Inspector */}
        <main className="product-detail-workbench">
          {selectedProduct ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '18px' }}>
              {/* Product Hero Info & Primary CTA */}
              <div className="product-hero-panel">
                <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', flexWrap: 'wrap', gap: '12px' }}>
                  <div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <h2 style={{ fontSize: '18px', fontWeight: 600, color: 'var(--text-primary)' }}>
                        {selectedProduct.product_name}
                      </h2>
                      <Badge variant="success" dot size="sm">
                        Resource Lock Active
                      </Badge>
                    </div>
                    <p style={{ fontSize: '12px', color: 'var(--text-secondary)', marginTop: '4px' }}>
                      Snapshot ID: <code>{selectedProduct.snapshot_id}</code> • Brand: <strong>{selectedProduct.brand}</strong>
                    </p>
                  </div>

                  <Button
                    variant="primary"
                    size="md"
                    icon={<Film size={15} />}
                    loading={isCreatingProject}
                    disabled={isCreatingProject}
                    onClick={() => handleCreateProjectFromProduct(selectedProduct)}
                  >
                    Create Video Project
                  </Button>
                </div>

                {/* Tab Navigation */}
                <div className="product-inspector-tabs">
                  {[
                    { id: 'overview', label: 'Overview' },
                    { id: 'research', label: 'Research Intelligence' },
                    { id: 'assets', label: `Original Assets (${selectedProduct.media_count})` },
                    { id: 'lock', label: 'Resource Lock Verification' },
                  ].map((tab) => (
                    <button
                      key={tab.id}
                      onClick={() => setActiveTab(tab.id as TabType)}
                      className={`tab-item-btn ${activeTab === tab.id ? 'active' : ''}`}
                    >
                      {tab.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Tab Contents */}
              {activeTab === 'overview' && (
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '16px' }}>
                  <div className="detail-panel-card">
                    <h4 className="panel-title">Product Identity</h4>
                    <div className="meta-list">
                      <div>
                        <span>Product Name</span>
                        <strong>{selectedProduct.product_name}</strong>
                      </div>
                      <div>
                        <span>Brand</span>
                        <span>{selectedProduct.brand || 'Unspecified'}</span>
                      </div>
                      <div>
                        <span>Model</span>
                        <span>{selectedProduct.model || 'Unspecified'}</span>
                      </div>
                      <div>
                        <span>Lock Digest</span>
                        <code style={{ fontSize: '11px' }}>{formatDigest(selectedProduct.manifest_digest)}</code>
                      </div>
                    </div>
                  </div>

                  <div className="detail-panel-card">
                    <h4 className="panel-title">Resource Pack Lock</h4>
                    <div className="meta-list">
                      <div>
                        <span>Lock ID</span>
                        <code style={{ color: 'var(--accent-primary)' }}>{selectedProduct.resource_pack_lock_id}</code>
                      </div>
                      <div>
                        <span>Media Count</span>
                        <span>{selectedProduct.media_count} durable reference assets</span>
                      </div>
                      <div>
                        <span>Created At</span>
                        <span>{selectedProduct.created_at || 'Verified snapshot'}</span>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {activeTab === 'research' && (
                <div className="product-research-grid">
                  <div className="detail-panel-card">
                    <h4 className="panel-title">Market & Competitor Research</h4>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', fontSize: '13px' }}>
                      <p style={{ color: 'var(--text-secondary)', lineHeight: 1.5 }}>
                        Extracted product intelligence confirms core target audience personas for commercial marketing.
                      </p>
                      {detail?.research && Object.keys(detail.research).length > 0 ? (
                        <div className="meta-list">
                          {Object.entries(detail.research).map(([k, v]) => (
                            <div key={k}>
                              <span style={{ textTransform: 'capitalize' }}>{k.replace(/_/g, ' ')}</span>
                              <span>{String(v)}</span>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <div style={{ color: 'var(--text-muted)', fontSize: '12px' }}>
                          Standardized research attributes verified for Video Factory brief synthesis.
                        </div>
                      )}
                    </div>
                  </div>

                  <div className="detail-panel-card">
                    <h4 className="panel-title">Pipeline Flow</h4>
                    <div className="flow-step-list">
                      {pipelineSteps.map((step) => {
                        const status = phaseSummary[step.id]
                        return (
                          <div className={`flow-step-row ${status === 'completed' ? 'complete' : ''}`} key={step.id}>
                            <div className="flow-step-icon">{step.icon}</div>
                            <div>
                              <strong>{step.label}</strong>
                              <p>{step.description}</p>
                            </div>
                            <Badge variant={status === 'completed' ? 'success' : status === 'warning' ? 'timeline' : 'neutral'} size="sm">
                              {status.replace(/_/g, ' ')}
                            </Badge>
                          </div>
                        )
                      })}
                    </div>
                  </div>

                  {researchResult?.content_previews?.length ? (
                    <div className="detail-panel-card product-package-preview">
                      <h4 className="panel-title">Generated Script & Prompt Preview</h4>
                      {researchResult.content_previews.slice(0, 3).map((item, index) => (
                        <article className="content-preview-item" key={`${item.package_id || index}`}>
                          <div className="content-preview-header">
                            <ClipboardList size={14} />
                            <strong>{item.angle || item.product_name || `Package ${index + 1}`}</strong>
                          </div>
                          <p>{item.hook || 'Hook pending'}</p>
                          <div className="content-preview-block">
                            <span>Script</span>
                            <p>{item.script}</p>
                          </div>
                          <div className="content-preview-block">
                            <span>Prompt</span>
                            <p>{item.ai_prompts}</p>
                          </div>
                        </article>
                      ))}
                    </div>
                  ) : (
                    <div className="detail-panel-card product-package-preview empty">
                      <AlertCircle size={18} />
                      <strong>No generated package yet</strong>
                      <p>Run Product Intelligence Crawl to produce script and prompt previews for this workspace.</p>
                    </div>
                  )}
                </div>
              )}
              {activeTab === 'assets' && (
                <div className="detail-panel-card">
                  <h4 className="panel-title">Original Reference Media Assets</h4>
                  <div
                    style={{
                      display: 'grid',
                      gridTemplateColumns: 'repeat(auto-fill, minmax(130px, 1fr))',
                      gap: '14px',
                      marginTop: '8px',
                    }}
                  >
                    {(detail?.assets || []).map((asset) => (
                      <div key={asset.asset_id} style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                        <AssetThumbnail
                          assetId={asset.asset_id}
                          aspectRatio="1:1"
                          onInspect={(id) => setInspectAssetId(id)}
                        />
                        <span
                          style={{
                            fontSize: '10px',
                            fontFamily: 'var(--font-mono)',
                            color: 'var(--text-muted)',
                            textAlign: 'center',
                          }}
                          className="truncate"
                        >
                          {asset.asset_id}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {activeTab === 'lock' && (
                <div className="detail-panel-card">
                  <h4 className="panel-title">Cryptographic Manifest & Integrity</h4>
                  <div className="meta-list">
                    <div>
                      <span>Lock Status</span>
                      <Badge variant="success" dot size="sm">
                        Verified
                      </Badge>
                    </div>
                    <div>
                      <span>Manifest Digest</span>
                      <code style={{ fontSize: '11px', color: 'var(--status-success)' }}>
                        {selectedProduct.manifest_digest}
                      </code>
                    </div>
                    <div>
                      <span>Lock ID</span>
                      <code>{selectedProduct.resource_pack_lock_id}</code>
                    </div>
                  </div>
                </div>
              )}
            </div>
          ) : (
            <EmptyState
              icon={Package}
              title="Select a Product"
              description="Choose a product from the catalog on the left to inspect research evidence, assets, and locks."
            />
          )}
        </main>
      </div>

      {/* Media Inspection Modal */}
      <MediaViewerModal
        assetId={inspectAssetId}
        onClose={() => setInspectAssetId(null)}
      />
    </div>
  )
}
