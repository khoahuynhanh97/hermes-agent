import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { api } from '../../lib/api'

const STEP_NAMES = [
  'product',
  'analysis',
  'script',
  'storyboard',
  'image_prompt',
  'video_prompt',
  'result',
]

const STEP_LABELS: Record<string, string> = {
  product: '1. Sản phẩm',
  analysis: '2. Phân tích',
  script: '3. Kịch bản',
  storyboard: '4. Storyboard',
  image_prompt: '5. Image Prompt',
  video_prompt: '6. Video Prompt',
  result: '7. Kết quả',
}

export function PromptStudioPage() {
  const { projectId } = useParams<{ projectId: string }>()
  const [steps, setSteps] = useState<Record<string, { approved: boolean; content: Record<string, unknown> }>>(
    Object.fromEntries(STEP_NAMES.map((s) => [s, { approved: false, content: {} }])),
  )

  async function handleApprove(step: string) {
    await api.post(`/api/prompt-studio/${projectId}/approve`, { step, content: steps[step].content })
    setSteps((prev) => ({
      ...prev,
      [step]: { ...prev[step], approved: true },
    }))
  }

  async function handleInvalidate(step: string) {
    await api.post(`/api/prompt-studio/${projectId}/invalidate`, { step, content: {} })
    setSteps((prev) => {
      const next = { ...prev }
      const idx = STEP_NAMES.indexOf(step)
      for (let i = idx; i < STEP_NAMES.length; i++) {
        next[STEP_NAMES[i]] = { approved: false, content: {} }
      }
      return next
    })
  }

  return (
    <div>
      <h1>Prompt Studio — {projectId}</h1>
      {STEP_NAMES.map((step) => (
        <div key={step} style={{ marginBottom: '1rem', padding: '0.5rem', border: '1px solid #ccc' }}>
          <h2>{STEP_LABELS[step]}</h2>
          <p>Status: {steps[step].approved ? 'Approved' : 'Draft'}</p>
          <button onClick={() => handleApprove(step)} disabled={steps[step].approved}>
            Duyệt
          </button>
          <button onClick={() => handleInvalidate(step)}>Invalidate from here</button>
        </div>
      ))}
    </div>
  )
}