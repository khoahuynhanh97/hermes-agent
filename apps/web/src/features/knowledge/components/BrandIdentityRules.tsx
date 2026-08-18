import React, { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Palette, Save, Check } from 'lucide-react'
import { api } from '../../../lib/api'
import { Button } from '../../../components/common/Button'

interface BrandGuideline {
  project_id: string
  primary_color: string | null
  secondary_color: string | null
  accent_color: string | null
  tone_of_voice: string | null
}

const TONES = ['Friendly', 'Professional', 'Energetic', 'Calm', 'Bold'] as const

const DEFAULT_BRAND: BrandGuideline = {
  project_id: '',
  primary_color: '#38bdf8',
  secondary_color: '#10b981',
  accent_color: '#f59e0b',
  tone_of_voice: 'Friendly',
}

export const BrandIdentityRules: React.FC = () => {
  const queryClient = useQueryClient()
  const [projectId, setProjectId] = useState('')
  const [form, setForm] = useState<BrandGuideline>(DEFAULT_BRAND)
  const [saved, setSaved] = useState(false)

  const { data: brand } = useQuery<BrandGuideline>({
    queryKey: ['knowledge', 'brand', projectId],
    queryFn: async () => {
      if (!projectId.trim()) return DEFAULT_BRAND
      try {
        const result = await api.get<BrandGuideline>(`/api/knowledge/brands/${encodeURIComponent(projectId)}`)
        return result.project_id ? result : { ...DEFAULT_BRAND, project_id: projectId }
      } catch {
        return { ...DEFAULT_BRAND, project_id: projectId }
      }
    },
    enabled: !!projectId.trim(),
  })

  useEffect(() => {
    if (brand) {
      setForm(brand)
    }
  }, [brand])

  const saveMutation = useMutation({
    mutationFn: (data: BrandGuideline) => api.post('/api/knowledge/brands', data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['knowledge', 'brand', projectId] })
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    },
  })

  const handleSave = () => {
    if (!projectId.trim()) return
    saveMutation.mutate({ ...form, project_id: projectId })
  }

  const ColorPicker: React.FC<{ label: string; value: string; onChange: (v: string) => void }> = ({ label, value, onChange }) => (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
      <label style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-secondary)' }}>{label}</label>
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
        <input
          type="color"
          value={value || '#38bdf8'}
          onChange={(e) => onChange(e.target.value)}
          style={{
            width: '32px',
            height: '32px',
            border: '1px solid var(--border-default)',
            borderRadius: 'var(--radius-sm)',
            cursor: 'pointer',
            padding: 0,
            backgroundColor: 'transparent',
          }}
        />
        <input
          type="text"
          value={value || ''}
          onChange={(e) => onChange(e.target.value)}
          placeholder="#000000"
          style={{
            flex: 1,
            padding: '6px 10px',
            fontSize: '13px',
            fontFamily: 'var(--font-mono)',
            backgroundColor: 'var(--bg-input)',
            border: '1px solid var(--border-default)',
            borderRadius: 'var(--radius-md)',
            color: 'var(--text-primary)',
            outline: 'none',
          }}
        />
      </div>
    </div>
  )

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', maxWidth: '600px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
        <Palette size={16} style={{ color: 'var(--accent-primary)' }} />
        <span style={{ fontSize: '14px', fontWeight: 600, color: 'var(--text-primary)' }}>
          Brand Identity Rules
        </span>
      </div>

      <div style={{
        padding: '16px',
        backgroundColor: 'var(--bg-panel)',
        border: '1px solid var(--border-default)',
        borderRadius: 'var(--radius-lg)',
        display: 'flex',
        flexDirection: 'column',
        gap: '14px',
      }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
          <label style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-secondary)' }}>Project ID</label>
          <input
            type="text"
            placeholder="Enter project ID to load brand settings..."
            value={projectId}
            onChange={(e) => setProjectId(e.target.value)}
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
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '12px' }}>
          <ColorPicker
            label="Primary Color"
            value={form.primary_color || ''}
            onChange={(v) => setForm({ ...form, primary_color: v })}
          />
          <ColorPicker
            label="Secondary Color"
            value={form.secondary_color || ''}
            onChange={(v) => setForm({ ...form, secondary_color: v })}
          />
          <ColorPicker
            label="Accent Color"
            value={form.accent_color || ''}
            onChange={(v) => setForm({ ...form, accent_color: v })}
          />
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
          <label style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-secondary)' }}>Tone of Voice</label>
          <select
            value={form.tone_of_voice || 'Friendly'}
            onChange={(e) => setForm({ ...form, tone_of_voice: e.target.value })}
            style={{
              padding: '7px 10px',
              fontSize: '13px',
              backgroundColor: 'var(--bg-input)',
              border: '1px solid var(--border-default)',
              borderRadius: 'var(--radius-md)',
              color: 'var(--text-primary)',
              outline: 'none',
              cursor: 'pointer',
            }}
          >
            {TONES.map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
        </div>

        <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '4px' }}>
          <Button
            variant={saved ? 'success' : 'primary'}
            size="sm"
            icon={saved ? <Check size={14} /> : <Save size={14} />}
            onClick={handleSave}
            disabled={!projectId.trim() || saveMutation.isPending}
            loading={saveMutation.isPending}
          >
            {saved ? 'Saved!' : 'Save Brand Rules'}
          </Button>
        </div>
      </div>

      <div style={{
        padding: '14px',
        backgroundColor: 'var(--bg-panel)',
        border: '1px solid var(--border-default)',
        borderRadius: 'var(--radius-lg)',
      }}>
        <span style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
          Preview
        </span>
        <div style={{
          marginTop: '10px',
          display: 'flex',
          gap: '8px',
          alignItems: 'center',
        }}>
          <div style={{ width: '40px', height: '40px', borderRadius: 'var(--radius-md)', backgroundColor: form.primary_color || '#38bdf8', border: '1px solid var(--border-default)' }} />
          <div style={{ width: '40px', height: '40px', borderRadius: 'var(--radius-md)', backgroundColor: form.secondary_color || '#10b981', border: '1px solid var(--border-default)' }} />
          <div style={{ width: '40px', height: '40px', borderRadius: 'var(--radius-md)', backgroundColor: form.accent_color || '#f59e0b', border: '1px solid var(--border-default)' }} />
          <span style={{ fontSize: '13px', color: 'var(--text-secondary)', marginLeft: '8px' }}>
            Tone: {form.tone_of_voice || 'Friendly'}
          </span>
        </div>
      </div>
    </div>
  )
}
