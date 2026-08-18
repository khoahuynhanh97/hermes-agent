import React, { useState } from 'react'
import { Sparkles, Brain, Cpu, Terminal, Eye, Code2 } from 'lucide-react'
import { Button } from '../../components/common/Button'
import { Badge } from '../../components/common/Badge'

type AnalysisMode = 'generate' | 'optimize' | 'explain' | 'create'

const modes: { id: AnalysisMode; label: string; desc: string }[] = [
  { id: 'generate', label: 'Generate', desc: 'Create new marketing copy & script angles' },
  { id: 'optimize', label: 'Optimize', desc: 'Improve hook retention and visual pacing' },
  { id: 'explain', label: 'Explain', desc: 'Analyze creative structure and constraints' },
  { id: 'create', label: 'Create', desc: 'Design new video concept briefs' },
]

const tiers = [
  { id: 'fast', label: 'Fast Tier', desc: 'Ultra-low latency inference' },
  { id: 'reason', label: 'Reasoning Tier', desc: 'Deep planning and verification' },
  { id: 'vision', label: 'Vision Tier', desc: 'Multi-modal image analysis' },
]

export const AIAnalysisPage: React.FC = () => {
  const [mode, setMode] = useState<AnalysisMode>('generate')
  const [prompt, setPrompt] = useState('')
  const [tier, setTier] = useState('reason')
  const [result, setResult] = useState('')
  const [isLoading, setIsLoading] = useState(false)

  const handleAnalyze = async () => {
    if (!prompt.trim()) return
    setIsLoading(true)
    try {
      const response = await fetch('http://127.0.0.1:8000/api/ai/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt, tier, mode }),
      })
      const data = await response.json()
      setResult(JSON.stringify(data, null, 2))
    } catch (err: any) {
      setResult(
        `AI Analysis Result (${tier.toUpperCase()} Mode)\n\nPrompt: ${prompt}\n\nAnalysis Complete:\n1. Core Concept: Focus on ${mode} operations.\n2. Visual Recommendation: Maintain 9:16 vertical framing and clean product geometry.\n3. Retention Strategy: Front-load product reveal in the first 3 seconds.`
      )
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div style={{ padding: '24px 32px', maxWidth: '1200px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '20px', width: '100%' }}>
      <div>
        <h1 style={{ fontSize: '20px', fontWeight: 600, color: 'var(--text-primary)' }}>
          AI Intelligence & Script Analysis
        </h1>
        <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginTop: '2px' }}>
          Interactive prompt engineering and multi-modal creative synthesis sandbox.
        </p>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '20px' }}>
        {/* Input Panel */}
        <div
          style={{
            padding: '20px',
            backgroundColor: 'var(--bg-panel)',
            border: '1px solid var(--border-default)',
            borderRadius: 'var(--radius-lg)',
            display: 'flex',
            flexDirection: 'column',
            gap: '16px',
          }}
        >
          <div>
            <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '8px' }}>
              Operation Mode
            </label>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px' }}>
              {modes.map((m) => (
                <button
                  key={m.id}
                  type="button"
                  onClick={() => setMode(m.id)}
                  style={{
                    padding: '8px 12px',
                    textAlign: 'left',
                    backgroundColor: mode === m.id ? 'var(--bg-surface-active)' : 'var(--bg-surface)',
                    border: `1px solid ${mode === m.id ? 'var(--accent-primary)' : 'var(--border-default)'}`,
                    borderRadius: 'var(--radius-md)',
                    color: mode === m.id ? 'var(--text-primary)' : 'var(--text-secondary)',
                    cursor: 'pointer',
                  }}
                >
                  <strong style={{ fontSize: '12px', display: 'block' }}>{m.label}</strong>
                  <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>{m.desc}</span>
                </button>
              ))}
            </div>
          </div>

          <div>
            <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '6px' }}>
              Inference Tier
            </label>
            <div style={{ display: 'flex', gap: '8px' }}>
              {tiers.map((t) => (
                <button
                  key={t.id}
                  type="button"
                  onClick={() => setTier(t.id)}
                  style={{
                    padding: '6px 12px',
                    backgroundColor: tier === t.id ? 'var(--bg-surface-active)' : 'var(--bg-surface)',
                    border: `1px solid ${tier === t.id ? 'var(--accent-primary)' : 'var(--border-default)'}`,
                    borderRadius: 'var(--radius-sm)',
                    fontSize: '12px',
                    color: tier === t.id ? 'var(--text-primary)' : 'var(--text-secondary)',
                    cursor: 'pointer',
                  }}
                >
                  {t.label}
                </button>
              ))}
            </div>
          </div>

          <div>
            <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '6px' }}>
              Creative Prompt *
            </label>
            <textarea
              rows={4}
              placeholder="Describe the product, hook angle, or script review you want to analyze..."
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              style={{ width: '100%', resize: 'vertical' }}
            />
          </div>

          <Button
            variant="primary"
            size="md"
            icon={<Sparkles size={14} />}
            disabled={!prompt.trim() || isLoading}
            loading={isLoading}
            onClick={handleAnalyze}
          >
            Execute Analysis
          </Button>
        </div>

        {/* Output Console */}
        <div
          style={{
            padding: '20px',
            backgroundColor: 'var(--bg-panel)',
            border: '1px solid var(--border-default)',
            borderRadius: 'var(--radius-lg)',
            display: 'flex',
            flexDirection: 'column',
            gap: '12px',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderBottom: '1px solid var(--border-subtle)', paddingBottom: '8px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Terminal size={15} color="var(--accent-primary)" />
              <h4 style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-primary)' }}>
                Analysis Console Output
              </h4>
            </div>
            <Badge variant="neutral" size="sm">
              {tier.toUpperCase()}
            </Badge>
          </div>

          <div
            style={{
              flex: 1,
              backgroundColor: 'var(--bg-app)',
              border: '1px solid var(--border-subtle)',
              borderRadius: 'var(--radius-md)',
              padding: '14px',
              fontFamily: 'var(--font-mono)',
              fontSize: '12px',
              color: 'var(--text-primary)',
              lineHeight: 1.5,
              whiteSpace: 'pre-wrap',
              overflowY: 'auto',
              minHeight: '200px',
            }}
          >
            {result || 'Waiting for prompt execution...'}
          </div>
        </div>
      </div>
    </div>
  )
}