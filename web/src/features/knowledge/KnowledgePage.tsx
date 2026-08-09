import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../../lib/api'

interface Knowledge {
  id: string
  title: string
  source: string
  category: string
  status: string
}

export function KnowledgePage() {
  const queryClient = useQueryClient()
  const [title, setTitle] = useState('')
  const [source, setSource] = useState('')
  const [category, setCategory] = useState('general')

  const { data: knowledge = [], isLoading } = useQuery<Knowledge[]>({
    queryKey: ['knowledge'],
    queryFn: () => api.get<Knowledge[]>('/api/knowledge'),
  })

  const createKnowledge = useMutation({
    mutationFn: (data: { title: string; source: string; category: string }) =>
      api.post('/api/knowledge', data),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['knowledge'] }),
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    createKnowledge.mutate({ title, source, category })
    setTitle('')
    setSource('')
  }

  if (isLoading) return <div className="loading">Loading knowledge...</div>

  return (
    <div>
      <h1>📚 Knowledge Base</h1>
      
      <div className="card">
        <h2>Add New Knowledge</h2>
        <form onSubmit={handleSubmit} style={{ display: 'grid', gap: '1rem', gridTemplateColumns: '1fr 1fr auto' }}>
          <input
            type="text"
            placeholder="Title"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            required
          />
          <input
            type="text"
            placeholder="Source URL"
            value={source}
            onChange={(e) => setSource(e.target.value)}
            required
          />
          <select value={category} onChange={(e) => setCategory(e.target.value)}>
            <option value="general">General</option>
            <option value="technology">Technology</option>
            <option value="workflow">Workflow</option>
            <option value="tool">Tool</option>
          </select>
          <button type="submit" disabled={createKnowledge.isPending}>
            {createKnowledge.isPending ? 'Adding...' : 'Add Knowledge'}
          </button>
        </form>
      </div>

      <div className="card">
        <h2>All Knowledge ({knowledge.length})</h2>
        {knowledge.length === 0 ? (
          <p style={{ color: '#71717a' }}>No knowledge entries yet.</p>
        ) : (
          <div style={{ display: 'grid', gap: '0.75rem' }}>
            {knowledge.map((item) => (
              <div
                key={item.id}
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  padding: '1rem',
                  background: 'rgba(255,255,255,0.03)',
                  borderRadius: '12px',
                  border: '1px solid #27272a',
                }}
              >
                <div>
                  <div style={{ fontWeight: 600, color: '#e4e4e7' }}>{item.title}</div>
                  <div style={{ fontSize: '0.75rem', color: '#71717a', marginTop: '0.25rem' }}>
                    {item.source} • {item.category}
                  </div>
                </div>
                <span className={`badge ${item.status === 'approved' ? 'badge-success' : 'badge-warning'}`}>
                  {item.status}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}