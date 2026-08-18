import React, { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { BookOpen, Copy, X, LayoutGrid, ChevronDown } from 'lucide-react'
import { api } from '../../../lib/api'
import { Badge } from '../../../components/common/Badge'
import { Button } from '../../../components/common/Button'
import { EmptyState } from '../../../components/common/EmptyState'

interface Playbook {
  id: number
  name: string
  structure: string
  description: string
  category: string
}

const CATEGORIES = ['All', 'Hook', 'CTA', 'Structure', 'Trend'] as const
const CATEGORY_VARIANT: Record<string, 'success' | 'active' | 'running' | 'neutral'> = {
  Hook: 'success',
  CTA: 'active',
  Structure: 'running',
  Trend: 'neutral',
}

export const PlaybookExplorer: React.FC = () => {
  const [category, setCategory] = useState<string>('All')
  const [selected, setSelected] = useState<Playbook | null>(null)
  const [copied, setCopied] = useState(false)

  const { data: playbooks = [], isLoading } = useQuery<Playbook[]>({
    queryKey: ['knowledge', 'playbooks', category],
    queryFn: async () => {
      try {
        const params = category !== 'All' ? `?category=${encodeURIComponent(category)}` : ''
        return await api.get<Playbook[]>(`/api/knowledge/playbooks${params}`)
      } catch {
        return []
      }
    },
  })

  const handleCopy = async (text: string) => {
    await navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  const truncate = (s: string, max: number) => (s.length > max ? s.slice(0, max) + '...' : s)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '10px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <LayoutGrid size={16} style={{ color: 'var(--accent-primary)' }} />
          <span style={{ fontSize: '14px', fontWeight: 600, color: 'var(--text-primary)' }}>
            Playbook Explorer
          </span>
        </div>
        <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
          {CATEGORIES.map((c) => (
            <button
              key={c}
              onClick={() => setCategory(c)}
              style={{
                padding: '3px 10px',
                fontSize: '12px',
                borderRadius: 'var(--radius-sm)',
                border: `1px solid ${category === c ? 'var(--accent-primary)' : 'var(--border-default)'}`,
                backgroundColor: category === c ? 'rgba(56,189,248,0.12)' : 'transparent',
                color: category === c ? 'var(--accent-primary)' : 'var(--text-secondary)',
                cursor: 'pointer',
                transition: 'all 0.15s',
              }}
            >
              {c}
            </button>
          ))}
        </div>
      </div>

      {isLoading ? (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: '14px' }}>
          {[1, 2, 3].map((i) => (
            <div key={i} style={{
              height: '140px',
              borderRadius: 'var(--radius-lg)',
              backgroundColor: 'var(--bg-panel)',
              border: '1px solid var(--border-default)',
              opacity: 0.5,
              animation: 'pulse 1.5s ease-in-out infinite',
            }} />
          ))}
        </div>
      ) : playbooks.length === 0 ? (
        <EmptyState
          icon={BookOpen}
          title="No Playbooks Found"
          description="No viral video playbooks available. Create one to get started."
        />
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: '14px' }}>
          {playbooks.map((pb) => (
            <div
              key={pb.id}
              onClick={() => setSelected(pb)}
              style={{
                padding: '16px',
                backgroundColor: 'var(--bg-panel)',
                border: '1px solid var(--border-default)',
                borderRadius: 'var(--radius-lg)',
                cursor: 'pointer',
                transition: 'border-color 0.15s, box-shadow 0.15s',
                display: 'flex',
                flexDirection: 'column',
                gap: '8px',
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.borderColor = 'var(--accent-primary)'
                e.currentTarget.style.boxShadow = '0 0 0 1px rgba(56,189,248,0.15)'
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.borderColor = 'var(--border-default)'
                e.currentTarget.style.boxShadow = 'none'
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <strong style={{ fontSize: '13px', color: 'var(--text-primary)' }}>{pb.name}</strong>
                <Badge variant={CATEGORY_VARIANT[pb.category] || 'neutral'} size="sm">
                  {pb.category}
                </Badge>
              </div>
              <p style={{ fontSize: '12px', color: 'var(--text-muted)', lineHeight: 1.4, margin: 0 }}>
                {truncate(pb.structure, 80)}
              </p>
              <p style={{ fontSize: '12px', color: 'var(--text-secondary)', lineHeight: 1.4, margin: 0 }}>
                {truncate(pb.description, 100)}
              </p>
            </div>
          ))}
        </div>
      )}

      {selected && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            backgroundColor: 'var(--bg-overlay)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
            padding: '24px',
          }}
          onClick={() => setSelected(null)}
        >
          <div
            style={{
              backgroundColor: 'var(--bg-panel)',
              border: '1px solid var(--border-default)',
              borderRadius: 'var(--radius-lg)',
              padding: '24px',
              maxWidth: '600px',
              width: '100%',
              maxHeight: '80vh',
              overflow: 'auto',
              display: 'flex',
              flexDirection: 'column',
              gap: '16px',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
              <div>
                <h3 style={{ fontSize: '16px', fontWeight: 600, color: 'var(--text-primary)', margin: 0 }}>
                  {selected.name}
                </h3>
                <Badge variant={CATEGORY_VARIANT[selected.category] || 'neutral'} size="sm" style={{ marginTop: '6px' }}>
                  {selected.category}
                </Badge>
              </div>
              <Button variant="ghost" size="icon" onClick={() => setSelected(null)}>
                <X size={16} />
              </Button>
            </div>

            <div>
              <label style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                Structure
              </label>
              <div style={{
                marginTop: '6px',
                padding: '12px',
                backgroundColor: 'var(--bg-surface)',
                border: '1px solid var(--border-default)',
                borderRadius: 'var(--radius-md)',
                fontSize: '13px',
                color: 'var(--text-primary)',
                lineHeight: 1.6,
                whiteSpace: 'pre-wrap',
              }}>
                {selected.structure}
              </div>
            </div>

            <div>
              <label style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                Description
              </label>
              <p style={{
                marginTop: '6px',
                fontSize: '13px',
                color: 'var(--text-primary)',
                lineHeight: 1.6,
                margin: 0,
              }}>
                {selected.description}
              </p>
            </div>

            <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end', marginTop: '4px' }}>
              <Button
                variant="outline"
                size="sm"
                icon={<Copy size={13} />}
                onClick={() => handleCopy(selected.structure)}
              >
                {copied ? 'Copied!' : 'Copy Structure'}
              </Button>
              <Button variant="primary" size="sm">
                Use in Project
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
