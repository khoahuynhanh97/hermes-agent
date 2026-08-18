import React, { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Lightbulb, Copy, X, Search, ChevronRight } from 'lucide-react'
import { api } from '../../../lib/api'
import { Badge } from '../../../components/common/Badge'
import { Button } from '../../../components/common/Button'
import { EmptyState } from '../../../components/common/EmptyState'

interface Template {
  id: number
  name: string
  template: string
  category: string
  industry: string
}

const INDUSTRIES = ['All', 'Technology', 'Cosmetics', 'Fashion', 'Home', 'Food', 'General'] as const
const INDUSTRY_VARIANT: Record<string, 'success' | 'active' | 'running' | 'neutral' | 'error' | 'blocked'> = {
  Technology: 'active',
  Cosmetics: 'success',
  Fashion: 'running',
  Home: 'neutral',
  Food: 'error',
  General: 'blocked',
}

export const PromptRecipeLibrary: React.FC = () => {
  const [industry, setIndustry] = useState<string>('All')
  const [search, setSearch] = useState('')
  const [expanded, setExpanded] = useState<Template | null>(null)
  const [copied, setCopied] = useState(false)

  const { data: templates = [], isLoading } = useQuery<Template[]>({
    queryKey: ['knowledge', 'templates', industry],
    queryFn: async () => {
      try {
        const params = industry !== 'All' ? `?industry=${encodeURIComponent(industry)}` : ''
        return await api.get<Template[]>(`/api/knowledge/templates${params}`)
      } catch {
        return []
      }
    },
  })

  const filtered = templates.filter(
    (t) => !search || t.name.toLowerCase().includes(search.toLowerCase()),
  )

  const handleCopy = async (text: string) => {
    await navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  const truncate = (s: string, max: number) => (s.length > max ? s.slice(0, max) + '...' : s)

  return (
    <div style={{ display: 'flex', gap: '16px', minHeight: '500px' }}>
      {/* Sidebar */}
      <div style={{
        width: '200px',
        flexShrink: 0,
        backgroundColor: 'var(--bg-panel)',
        border: '1px solid var(--border-default)',
        borderRadius: 'var(--radius-lg)',
        padding: '14px',
        display: 'flex',
        flexDirection: 'column',
        gap: '4px',
      }}>
        <span style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.5px', padding: '4px 8px' }}>
          Industries
        </span>
        {INDUSTRIES.map((ind) => (
          <button
            key={ind}
            onClick={() => setIndustry(ind)}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              padding: '7px 8px',
              fontSize: '13px',
              borderRadius: 'var(--radius-sm)',
              border: 'none',
              backgroundColor: industry === ind ? 'rgba(56,189,248,0.12)' : 'transparent',
              color: industry === ind ? 'var(--accent-primary)' : 'var(--text-secondary)',
              cursor: 'pointer',
              textAlign: 'left',
              transition: 'all 0.15s',
            }}
          >
            {industry === ind && <ChevronRight size={12} />}
            {ind}
          </button>
        ))}
      </div>

      {/* Main */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '14px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Lightbulb size={16} style={{ color: 'var(--accent-primary)' }} />
          <span style={{ fontSize: '14px', fontWeight: 600, color: 'var(--text-primary)' }}>
            Prompt Recipe Library
          </span>
          <span style={{ fontSize: '12px', color: 'var(--text-muted)', marginLeft: '4px' }}>
            {filtered.length} templates
          </span>
        </div>

        <div style={{ position: 'relative' }}>
          <Search size={14} style={{ position: 'absolute', left: '10px', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }} />
          <input
            type="text"
            placeholder="Search templates..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={{
              width: '100%',
              padding: '7px 10px 7px 30px',
              fontSize: '13px',
              backgroundColor: 'var(--bg-input)',
              border: '1px solid var(--border-default)',
              borderRadius: 'var(--radius-md)',
              color: 'var(--text-primary)',
              outline: 'none',
              boxSizing: 'border-box',
            }}
          />
        </div>

        {isLoading ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            {[1, 2, 3].map((i) => (
              <div key={i} style={{
                height: '80px',
                borderRadius: 'var(--radius-lg)',
                backgroundColor: 'var(--bg-panel)',
                border: '1px solid var(--border-default)',
                opacity: 0.5,
              }} />
            ))}
          </div>
        ) : filtered.length === 0 ? (
          <EmptyState
            icon={Lightbulb}
            title="No Templates Found"
            description="No prompt templates match your filter. Try a different industry or search term."
          />
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            {filtered.map((t) => (
              <div
                key={t.id}
                onClick={() => setExpanded(expanded?.id === t.id ? null : t)}
                style={{
                  padding: '14px 16px',
                  backgroundColor: 'var(--bg-panel)',
                  border: `1px solid ${expanded?.id === t.id ? 'var(--accent-primary)' : 'var(--border-default)'}`,
                  borderRadius: 'var(--radius-lg)',
                  cursor: 'pointer',
                  transition: 'border-color 0.15s',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '6px',
                }}
                onMouseEnter={(e) => { if (expanded?.id !== t.id) e.currentTarget.style.borderColor = 'var(--border-strong)' }}
                onMouseLeave={(e) => { if (expanded?.id !== t.id) e.currentTarget.style.borderColor = 'var(--border-default)' }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <strong style={{ fontSize: '13px', color: 'var(--text-primary)' }}>{t.name}</strong>
                    <Badge variant={INDUSTRY_VARIANT[t.industry] || 'neutral'} size="sm">{t.industry}</Badge>
                  </div>
                  <Badge variant="neutral" size="sm">{t.category}</Badge>
                </div>
                <p style={{ fontSize: '12px', color: 'var(--text-muted)', margin: 0, lineHeight: 1.4 }}>
                  {truncate(t.template, 120)}
                </p>

                {expanded?.id === t.id && (
                  <div style={{ marginTop: '6px' }}>
                    <div style={{
                      padding: '12px',
                      backgroundColor: 'var(--bg-surface)',
                      border: '1px solid var(--border-default)',
                      borderRadius: 'var(--radius-md)',
                      fontSize: '12px',
                      color: 'var(--text-primary)',
                      lineHeight: 1.6,
                      whiteSpace: 'pre-wrap',
                      maxHeight: '300px',
                      overflow: 'auto',
                    }}>
                      {t.template}
                    </div>
                    <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end', marginTop: '10px' }}>
                      <Button
                        variant="outline"
                        size="sm"
                        icon={<Copy size={13} />}
                        onClick={(e) => { e.stopPropagation(); handleCopy(t.template) }}
                      >
                        {copied ? 'Copied!' : 'Copy to Clipboard'}
                      </Button>
                      <Button variant="primary" size="sm" onClick={(e) => e.stopPropagation()}>
                        Create Playbook
                      </Button>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
