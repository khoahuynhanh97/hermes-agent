import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { BookOpen, Plus, RefreshCw } from 'lucide-react'
import { api } from '../../lib/api'
import { Button } from '../../components/common/Button'
import { PlaybookExplorer } from './components/PlaybookExplorer'
import { PromptRecipeLibrary } from './components/PromptRecipeLibrary'
import { BrandIdentityRules } from './components/BrandIdentityRules'

const TABS = ['Playbooks', 'Prompt Recipes', 'Brand Rules'] as const
type Tab = (typeof TABS)[number]

interface Knowledge {
  id: string
  title: string
  source: string
  category: string
  status: string
}

export const KnowledgePage: React.FC = () => {
  const queryClient = useQueryClient()
  const [activeTab, setActiveTab] = useState<Tab>('Playbooks')
  const [title, setTitle] = useState('')
  const [source, setSource] = useState('')
  const [category, setCategory] = useState('general')
  const [showAdd, setShowAdd] = useState(false)

  const { data: knowledge = [], refetch } = useQuery<Knowledge[]>({
    queryKey: ['knowledge'],
    queryFn: async () => {
      try {
        return await api.get<Knowledge[]>('/api/knowledge')
      } catch {
        return []
      }
    },
  })

  const createKnowledge = useMutation({
    mutationFn: (data: { title: string; source: string; category: string }) =>
      api.post('/api/knowledge', data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['knowledge'] })
      setTitle('')
      setSource('')
      setShowAdd(false)
    },
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!title.trim() || !source.trim()) return
    createKnowledge.mutate({ title, source, category })
  }

  return (
    <div style={{ padding: '24px 32px', maxWidth: '1200px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '20px', width: '100%' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '12px' }}>
        <div>
          <h1 style={{ fontSize: '20px', fontWeight: 600, color: 'var(--text-primary)' }}>
            Knowledge Hub
          </h1>
          <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginTop: '2px' }}>
            Viral video playbooks, prompt recipes, and brand identity rules.
          </p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <Button variant="outline" size="sm" icon={<RefreshCw size={13} />} onClick={() => refetch()}>
            Refresh
          </Button>
          <Button variant="primary" size="sm" icon={<Plus size={14} />} onClick={() => setShowAdd(!showAdd)}>
            {showAdd ? 'Close' : 'Add Knowledge'}
          </Button>
        </div>
      </div>

      {/* Add Knowledge Form */}
      {showAdd && (
        <form
          onSubmit={handleSubmit}
          style={{
            padding: '18px 20px',
            backgroundColor: 'var(--bg-panel)',
            border: '1px solid var(--border-default)',
            borderRadius: 'var(--radius-lg)',
            display: 'flex',
            flexDirection: 'column',
            gap: '12px',
          }}
        >
          <h3 style={{ fontSize: '14px', fontWeight: 600, color: 'var(--text-primary)' }}>
            Register New Knowledge Source
          </h3>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '10px' }}>
            <input
              type="text"
              placeholder="Title (e.g. Brand Identity Guidelines)"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              required
              style={{
                padding: '7px 10px',
                fontSize: '13px',
                backgroundColor: 'var(--bg-input)',
                border: '1px solid var(--border-default)',
                borderRadius: 'var(--radius-md)',
                color: 'var(--text-primary)',
                outline: 'none',
              }}
            />
            <input
              type="text"
              placeholder="Source URL or Reference ID"
              value={source}
              onChange={(e) => setSource(e.target.value)}
              required
              style={{
                padding: '7px 10px',
                fontSize: '13px',
                backgroundColor: 'var(--bg-input)',
                border: '1px solid var(--border-default)',
                borderRadius: 'var(--radius-md)',
                color: 'var(--text-primary)',
                outline: 'none',
              }}
            />
            <select
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              style={{
                padding: '7px 10px',
                fontSize: '13px',
                backgroundColor: 'var(--bg-input)',
                border: '1px solid var(--border-default)',
                borderRadius: 'var(--radius-md)',
                color: 'var(--text-primary)',
                outline: 'none',
              }}
            >
              <option value="general">General</option>
              <option value="brand">Brand Guidelines</option>
              <option value="product">Product Research</option>
              <option value="creative">Creative Prompts</option>
            </select>
          </div>
          <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '4px' }}>
            <Button type="submit" variant="primary" size="sm" disabled={createKnowledge.isPending} loading={createKnowledge.isPending}>
              Save Knowledge
            </Button>
          </div>
        </form>
      )}

      {/* Tabs */}
      <div style={{ display: 'flex', gap: '0', borderBottom: '1px solid var(--border-default)' }}>
        {TABS.map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            style={{
              padding: '8px 16px',
              fontSize: '13px',
              fontWeight: activeTab === tab ? 600 : 400,
              color: activeTab === tab ? 'var(--accent-primary)' : 'var(--text-secondary)',
              backgroundColor: 'transparent',
              border: 'none',
              borderBottom: activeTab === tab ? '2px solid var(--accent-primary)' : '2px solid transparent',
              cursor: 'pointer',
              transition: 'all 0.15s',
              marginBottom: '-1px',
            }}
          >
            {tab}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      {activeTab === 'Playbooks' && <PlaybookExplorer />}
      {activeTab === 'Prompt Recipes' && <PromptRecipeLibrary />}
      {activeTab === 'Brand Rules' && <BrandIdentityRules />}
    </div>
  )
}
