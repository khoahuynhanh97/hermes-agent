import React, { useState } from 'react'
import {
  Package,
  Lock,
  Search,
  Palette,
} from 'lucide-react'
import { VideoFactoryProject } from '../../../types/videoFactory'
import { useBindResources } from '../../../hooks/useVideoFactory'
import { Badge } from '../../../components/common/Badge'
import { Button } from '../../../components/common/Button'
import { AssetThumbnail } from '../../../components/common/AssetThumbnail'
import { EmptyState } from '../../../components/common/EmptyState'

interface ResourcesStageProps {
  project: VideoFactoryProject
  onInspectAsset: (assetId: string) => void
}

export const ResourcesStage: React.FC<ResourcesStageProps> = ({
  project,
  onInspectAsset,
}) => {
  const [productQuery, setProductQuery] = useState('')
  const [bindError, setBindError] = useState<string | null>(null)
  const bindMutation = useBindResources()

  const resourcePack = project.resource_pack
  const productRefs = resourcePack?.product_references || []
  const identity = resourcePack?.locked_product_identity

  const handleBind = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!productQuery.trim()) return
    setBindError(null)
    try {
      await bindMutation.mutateAsync({
        projectId: project.id,
        productQuery: productQuery.trim(),
      })
      setProductQuery('')
    } catch (err: any) {
      setBindError(err.message || 'Failed to bind resource pack lock')
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      {/* Top Banner / Bind Box */}
      <section
        style={{
          padding: '16px 20px',
          backgroundColor: 'var(--bg-panel)',
          border: '1px solid var(--border-default)',
          borderRadius: 'var(--radius-lg)',
          display: 'flex',
          flexDirection: 'column',
          gap: '12px',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '10px' }}>
          <div>
            <h3 style={{ fontSize: '14px', fontWeight: 600, color: 'var(--text-primary)' }}>
              Product Intelligence Resource Lock
            </h3>
            <p style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
              Bind verified product snapshots, identity constraints, and reference media into this workspace.
            </p>
          </div>

          {resourcePack && (
            <Badge variant="success" dot size="md">
              Resource Pack Locked (v{resourcePack.version || 1})
            </Badge>
          )}
        </div>

        {/* Bind Search Form */}
        <form onSubmit={handleBind} style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
          <div style={{ position: 'relative', flex: 1, minWidth: '260px' }}>
            <Search
              size={14}
              color="var(--text-muted)"
              style={{ position: 'absolute', left: '10px', top: '50%', transform: 'translateY(-50%)' }}
            />
            <input
              type="text"
              placeholder="Search product name, snapshot ID, or ResourcePackLock ID..."
              value={productQuery}
              onChange={(e) => setProductQuery(e.target.value)}
              style={{ width: '100%', paddingLeft: '32px' }}
            />
          </div>
          <Button
            type="submit"
            variant="primary"
            disabled={!productQuery.trim() || bindMutation.isPending}
            loading={bindMutation.isPending}
            icon={<Lock size={14} />}
          >
            {resourcePack ? 'Rebind Resources' : 'Bind Locked Resources'}
          </Button>
        </form>

        {bindError && (
          <div
            style={{
              padding: '8px 12px',
              backgroundColor: 'var(--status-error-bg)',
              border: '1px solid var(--status-error-border)',
              borderRadius: 'var(--radius-sm)',
              fontSize: '12px',
              color: 'var(--status-error)',
            }}
          >
            {bindError}
          </div>
        )}
      </section>

      {/* Main Resource Information & Assets */}
      {resourcePack ? (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '20px' }}>
          {/* Identity & Lock Metadata */}
          <div
            style={{
              padding: '16px 20px',
              backgroundColor: 'var(--bg-panel)',
              border: '1px solid var(--border-default)',
              borderRadius: 'var(--radius-lg)',
              display: 'flex',
              flexDirection: 'column',
              gap: '14px',
            }}
          >
            <h4 style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-primary)', borderBottom: '1px solid var(--border-subtle)', paddingBottom: '8px' }}>
              Locked Product Identity
            </h4>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', fontSize: '13px' }}>
              <div>
                <span style={{ color: 'var(--text-muted)', fontSize: '11px', display: 'block' }}>PRODUCT NAME</span>
                <strong style={{ color: 'var(--text-primary)', fontSize: '14px' }}>
                  {resourcePack.product_identity_description}
                </strong>
              </div>

              <div>
                <span style={{ color: 'var(--text-muted)', fontSize: '11px', display: 'block' }}>RESOURCE LOCK ID</span>
                <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--accent-primary)' }}>
                  {resourcePack.id}
                </span>
              </div>

              {identity?.color && (
                <div>
                  <span style={{ color: 'var(--text-muted)', fontSize: '11px', display: 'block' }}>COLOR / VARIANT</span>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginTop: '2px' }}>
                    <Palette size={13} color="var(--text-secondary)" />
                    <span style={{ color: 'var(--text-primary)' }}>{identity.color}</span>
                  </div>
                </div>
              )}

              {identity?.distinctive_features && identity.distinctive_features.length > 0 && (
                <div>
                  <span style={{ color: 'var(--text-muted)', fontSize: '11px', display: 'block', marginBottom: '4px' }}>
                    DISTINCTIVE FEATURES
                  </span>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                    {identity.distinctive_features.map((feat, idx) => (
                      <Badge key={idx} variant="neutral" size="sm">
                        {feat}
                      </Badge>
                    ))}
                  </div>
                </div>
              )}

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px', paddingTop: '8px', borderTop: '1px solid var(--border-subtle)' }}>
                <div>
                  <span style={{ color: 'var(--text-muted)', fontSize: '11px', display: 'block' }}>TOTAL ASSETS</span>
                  <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{productRefs.length} files</span>
                </div>
                <div>
                  <span style={{ color: 'var(--text-muted)', fontSize: '11px', display: 'block' }}>LOCK TIMESTAMP</span>
                  <span style={{ color: 'var(--text-secondary)', fontSize: '12px' }}>{resourcePack.locked_at || 'Verified'}</span>
                </div>
              </div>
            </div>
          </div>

          {/* Original Assets Gallery */}
          <div
            style={{
              padding: '16px 20px',
              backgroundColor: 'var(--bg-panel)',
              border: '1px solid var(--border-default)',
              borderRadius: 'var(--radius-lg)',
              display: 'flex',
              flexDirection: 'column',
              gap: '12px',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <h4 style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-primary)' }}>
                Original Product References ({productRefs.length})
              </h4>
              <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Click asset to inspect</span>
            </div>

            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fill, minmax(100px, 1fr))',
                gap: '12px',
              }}
            >
              {productRefs.map((asset, idx) => {
                const isPrimary = asset.asset_id === resourcePack.primary_product_asset_id
                return (
                  <div key={asset.asset_id || idx} style={{ position: 'relative' }}>
                    <AssetThumbnail
                      assetId={asset.asset_id}
                      aspectRatio="1:1"
                      roleLabel={isPrimary ? 'Primary' : undefined}
                      onInspect={onInspectAsset}
                    />
                    <div
                      style={{
                        fontSize: '10px',
                        fontFamily: 'var(--font-mono)',
                        color: 'var(--text-muted)',
                        marginTop: '4px',
                        textAlign: 'center',
                      }}
                      className="truncate"
                      title={asset.asset_id}
                    >
                      {asset.asset_id}
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        </div>
      ) : (
        <EmptyState
          icon={Package}
          title="No Product Resources Bound"
          description="Bind a verified Product Intelligence Resource Pack Lock above to initialize product references, visual identity, and constraints for this pipeline."
        />
      )}
    </div>
  )
}
