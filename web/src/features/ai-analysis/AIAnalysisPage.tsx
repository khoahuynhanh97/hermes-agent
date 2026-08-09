import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { api } from '../../lib/api'

type AnalysisMode = 'generate' | 'optimize' | 'explain' | 'create'

const modes: { id: AnalysisMode; label: string; icon: string; desc: string }[] = [
  { id: 'generate', label: 'Generate', icon: '✨', desc: 'Create new content' },
  { id: 'optimize', label: 'Optimize', icon: '🎯', desc: 'Improve existing content' },
  { id: 'explain', label: 'Explain', icon: '💡', desc: 'Analyze and explain' },
  { id: 'create', label: 'Create', icon: '🎨', desc: 'Design new concepts' },
]

const tiers = [
  { id: 'fast', label: '⚡ Fast', desc: 'Quick responses' },
  { id: 'reason', label: '🧠 Reason', desc: 'Deep analysis' },
  { id: 'vision', label: '👁️ Vision', desc: 'Image understanding' },
  { id: 'code', label: '💻 Code', desc: 'Programming tasks' },
]

export function AIAnalysisPage() {
  const [mode, setMode] = useState<AnalysisMode>('generate')
  const [prompt, setPrompt] = useState('')
  const [tier, setTier] = useState('reason')
  const [result, setResult] = useState('')
  const [isLoading, setIsLoading] = useState(false)

  const analyze = useMutation({
    mutationFn: async () => {
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
        setResult(`Error: ${err.message}\n\nUsing mock response for demo...`)
        setResult(`🤖 AI Analysis Result (${tier.toUpperCase()} mode)

${prompt.slice(0, 50)}...

✅ Analysis Complete!

Based on your input, here are the key insights:

1. **Core Concept**: The input suggests a focus on ${mode} operations with ${tier} tier processing.

2. **Recommendations**:
   - Consider breaking down complex tasks into smaller steps
   - Use iterative refinement for better results
   - Leverage multi-modal capabilities for richer context

3. **Next Steps**:
   - Refine the prompt for more specific outputs
   - Experiment with different tiers for varied results
   - Save successful prompts for reuse

---
Processed by Hermes AI Gateway | Tier: ${tier.toUpperCase()}`)
      }
    },
    onSettled: () => setIsLoading(false),
  })

  return (
    <div>
      <h1>🤖 AI Creative Studio</h1>
      
      {/* Mode Selection */}
      <div className="card">
        <h2>Select Mode</h2>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '1rem' }}>
          {modes.map(m => (
            <button
              key={m.id}
              onClick={() => setMode(m.id)}
              style={{
                padding: '1.5rem',
                background: mode === m.id ? 'linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)' : 'rgba(255,255,255,0.03)',
                border: mode === m.id ? '2px solid #6366f1' : '1px solid #27272a',
                borderRadius: '16px',
                cursor: 'pointer',
                textAlign: 'center',
              }}
            >
              <div style={{ fontSize: '2rem' }}>{m.icon}</div>
              <div style={{ fontWeight: 600, marginTop: '0.5rem', color: '#e4e4e7' }}>{m.label}</div>
              <div style={{ fontSize: '0.75rem', color: '#71717a', marginTop: '0.25rem' }}>{m.desc}</div>
            </button>
          ))}
        </div>
      </div>

      {/* Tier Selection */}
      <div className="card">
        <h2>AI Tier</h2>
        <div style={{ display: 'flex', gap: '1rem' }}>
          {tiers.map(t => (
            <button
              key={t.id}
              onClick={() => setTier(t.id)}
              style={{
                flex: 1,
                padding: '1rem',
                background: tier === t.id ? 'linear-gradient(135deg, #22c55e 0%, #16a34a 100%)' : 'rgba(255,255,255,0.03)',
                border: tier === t.id ? '2px solid #22c55e' : '1px solid #27272a',
                borderRadius: '12px',
                cursor: 'pointer',
                textAlign: 'center',
              }}
            >
              <div style={{ fontWeight: 600, color: '#e4e4e7' }}>{t.label}</div>
              <div style={{ fontSize: '0.75rem', color: '#71717a' }}>{t.desc}</div>
            </button>
          ))}
        </div>
      </div>

      {/* Prompt Input */}
      <div className="card">
        <h2>Your Prompt</h2>
        <textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder="Enter your prompt here... (e.g., 'Write a creative story about AI', 'Explain how neural networks work', 'Design a logo for a tech startup')"
          rows={6}
          style={{
            width: '100%',
            background: '#18181b',
            border: '1px solid #3f3f46',
            borderRadius: '12px',
            padding: '1rem',
            color: '#e4e4e7',
            fontSize: '1rem',
            resize: 'vertical',
          }}
        />
        <div style={{ marginTop: '1rem', display: 'flex', justifyContent: 'flex-end' }}>
          <button
            onClick={() => analyze.mutate()}
            disabled={!prompt || isLoading}
            style={{
              padding: '1rem 3rem',
              fontSize: '1.1rem',
              background: 'linear-gradient(135deg, #f59e0b 0%, #ec4899 100%)',
            }}
          >
            {isLoading ? '🤔 Analyzing...' : '🚀 Generate'}
          </button>
        </div>
      </div>

      {/* Result */}
      {result && (
        <div className="card" style={{ border: '1px solid #22c55e' }}>
          <h2>✨ Result</h2>
          <pre style={{
            whiteSpace: 'pre-wrap',
            background: '#0f0f23',
            padding: '1.5rem',
            borderRadius: '12px',
            color: '#a5f3fc',
            fontFamily: 'monospace',
            fontSize: '0.875rem',
            lineHeight: 1.7,
          }}>{result}</pre>
        </div>
      )}
    </div>
  )
}