import { useEffect, useState } from 'react'
import { api } from '../../lib/api'

interface ProjectData { id: string; status: string }

type Project = Record<string, any>

const EMPTY: Project = { id: '', status: 'draft' }

const STAGES = ['Resources', 'Idea', 'Brief', 'Scenes', 'Storyboard', 'Video', 'Timeline', 'Export']

export function VideoFactoryPage() {
  const [projects, setProjects] = useState<ProjectData[]>([])
  const [project, setProject] = useState<Project>(EMPTY)
  const [owner, setOwner] = useState('web_owner')
  const [newId, setNewId] = useState('')
  const [pollJobId, setPollJobId] = useState<string | null>(null)
  const [jobState, setJobState] = useState<string>('')
  const [jobError, setJobError] = useState<string>('')
  const [msg, setMsg] = useState<{ text: string; ok: boolean } | null>(null)
  const [busy, setBusy] = useState(false)
  const [imgFile, setImgFile] = useState<{ name: string; b64: string } | null>(null)
  const [frame, setFrame] = useState({ prompt: '', label: 'frame_1', scene: 'scene_1' })
  const [video, setVideo] = useState({ prompt: '', duration: 4 })
  const [tts, setTts] = useState({ text: '', style: '' })
  const [ttsResult, setTtsResult] = useState<{ wav: string; voice: string } | null>(null)
  const [mixed, setMixed] = useState<string>('')
  const [caption, setCaption] = useState('')
  const [pubStatus, setPubStatus] = useState('not_published')
  const [pubPostId, setPubPostId] = useState('')
  const [pubError, setPubError] = useState('')

  async function loadPub() {
    try {
      const r = await api.get<any>(`/api/vf/projects/${project.id}/publication?owner_user_id=${owner}`)
      setPubStatus(r.data?.status || 'not_published')
      setPubPostId(r.data?.post_id || '')
      setPubError(r.data?.last_error || '')
    } catch { /* not published yet */ }
  }

  // ---------- data ----------
  async function refreshList() {
    const data = await api.get<any>(`/api/vf/projects?owner_user_id=${owner}`)
    setProjects((data.data || []).map((p: any) => ({ id: p.id, status: p.status })))
  }
  async function open(pid: string) {
    const data = await api.get<any>(`/api/vf/projects/${pid}?owner_user_id=${owner}`)
    setProject(data.data)
    setPollJobId(null)
    setJobState('')
    setJobError('')
  }
  async function create() {
    const data = await api.post<any>(`/api/vf/projects?owner_user_id=${owner}`, { project_id: newId })
    setProject(data.data)
    refreshList()
  }
  async function post(path: string, body: any) {
    setBusy(true)
    try {
      const data = await api.post<any>(`/api/vf/projects/${project.id}${path}?owner_user_id=${owner}`, body)
      if (data.data) setProject(data.data)
      setMsg({ text: `${path} ok`, ok: true })
      refreshList()
    } catch (e: any) {
      setMsg({ text: `error: ${e?.message || e}`, ok: false })
    } finally { setBusy(false) }
  }
  async function postRaw(path: string, body: any) {
    setBusy(true)
    try {
      return await api.post<any>(`/api/vf/projects/${project.id}${path}?owner_user_id=${owner}`, body)
    } finally { setBusy(false) }
  }

  // ---------- job polling: stop on terminal, refetch project once ----------
  function poll(jobId: string) {
    setPollJobId(jobId)
    setJobState('queued')
    setJobError('')
    setMsg({ text: 'job queued…', ok: true })
  }
  useEffect(() => {
    if (!pollJobId) return
    let stopped = false
    const t = setInterval(async () => {
      try {
        const data = await api.get<any>(`/api/vf/jobs/${pollJobId}`)
        const j = data.data
        if (stopped) return
        setJobState(j.state)
        setJobError(j.error || '')
        if (j.state === 'completed' || j.state === 'failed') {
          stopped = true
          clearInterval(t)
          setPollJobId(null)
          setMsg(j.state === 'completed'
            ? { text: 'job completed', ok: true }
            : { text: `job failed: ${(j.error || '').slice(0, 120)}`, ok: false })
          if (j.state === 'completed') {
            // map durable job result into Video Factory domain state, then refetch once
            try { await api.post<any>(`/api/vf/projects/${project.id}/jobs/${pollJobId}/apply?owner_user_id=${owner}`, {}) } catch { /* ignore */ }
          }
          await open(project.id)  // single refetch of project detail
        }
      } catch { clearInterval(t); stopped = true }
    }, 3000)
    return () => { stopped = true; clearInterval(t) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pollJobId])

  useEffect(() => { refreshList() }, [owner])
  useEffect(() => { if (project.id) loadPub() }, [project.id])

  // ---------- stage derived from backend state (single source of truth) ----------
  const p = project
  const stageDone: boolean[] = [
    Boolean(p.resource_pack?.locked_at),
    p.idea_version > 0,
    p.brief_approval === 'approved',
    p.scene_plan_approval === 'approved',
    p.storyboard?.approval_status === 'approved',
    p.generated_scenes?.some((s: any) => s.generated_asset_id),
    Boolean(p.draft_video_asset_id),
    p.status === 'ready_to_publish',
  ]
  const currentIdx = stageDone.findIndex((d) => !d) === -1 ? stageDone.length - 1 : stageDone.findIndex((d) => !d)

  // ---------- file picker → base64 ----------
  function onPickFile(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0]
    if (!f) return
    const reader = new FileReader()
    reader.onload = () => {
      const b64 = String(reader.result || '').split(',')[1] || ''
      setImgFile({ name: f.name, b64 })
      setMsg({ text: `selected ${f.name}`, ok: true })
    }
    reader.readAsDataURL(f)
  }

  const s = p.status
  const imgPath = (rel: string) => `/media/${rel}`

  return (
    <div style={{ fontFamily: 'Inter, sans-serif', maxWidth: 920, margin: '0 auto', padding: 16 }}>
      <h1>Video Factory</h1>

      {/* project bar */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 12, alignItems: 'center' }}>
        <select value={owner} onChange={(e) => setOwner(e.target.value)}>
          <option value="web_owner">web_owner</option>
          <option value="e2e_owner">e2e_owner</option>
        </select>
        <select value={project.id} onChange={(e) => e.target.value && open(e.target.value)}>
          <option value="">-- open project --</option>
          {projects.map((x) => <option key={x.id} value={x.id}>{x.id} ({x.status})</option>)}
        </select>
        <input placeholder="new project id" value={newId} onChange={(e) => setNewId(e.target.value)} />
        <button onClick={create}>Create</button>
      </div>

      {project.id && <p><b>{project.id}</b> — {s}{pollJobId ? ` | job: ${jobState}${jobError ? ` (${jobError})` : ''}` : ''}</p>}

      {/* stage navigation */}
      {project.id && (
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 16 }}>
          {STAGES.map((name, i) => {
            const done = stageDone[i]
            const current = i === currentIdx
            return (
              <span key={name} style={{
                padding: '4px 10px', borderRadius: 12, fontSize: 12,
                background: done ? '#e8f5e9' : current ? '#fff3e0' : '#f5f5f5',
                border: current ? '2px solid #fb8c00' : '1px solid #ccc',
                color: done ? '#2e7d32' : current ? '#e65100' : '#777',
              }}>{done ? '✅' : current ? '●' : '○'} {name}</span>
            )
          })}
        </div>
      )}

      {msg && <p style={{ color: msg.ok ? '#0a7d2c' : '#c62828', fontSize: 13 }}>{msg.text}</p>}

      {/* B1 Resources */}
      <Card title="1. Resources">
        <Row label="Identity"><input value={(p.resource_pack as any)?.product_identity_description || ''} disabled placeholder="saved" /></Row>
        <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginBottom: 8 }}>
          <input type="file" accept="image/png,image/jpeg,image/webp" onChange={onPickFile} />
          {imgFile && <span style={{ fontSize: 12 }}>{imgFile.name}</span>}
          {imgFile && <img src={`data:image/png;base64,${imgFile.b64}`} alt="preview" style={{ width: 48, border: '1px solid #ddd' }} />}
          {imgFile && <button onClick={() => setImgFile(null)}>remove</button>}
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <Btn onClick={async () => {
            await post('/resources', { product_identity_description: 'blue water bottle', product_image_b64: imgFile?.b64 || '' })
            setImgFile(null)
          }}>Save Resource Pack</Btn>
          <Btn warn disabled={!p.resource_pack || !!p.resource_pack?.locked_at} onClick={async () => {
            const identityDesc = (p.resource_pack as any)?.product_identity_description || 'blue water bottle'
            if (window.confirm(`Confirm locking product identity: "${identityDesc}"?`)) {
              await post('/resources/lock', {
                description: identityDesc,
                color: 'blue',
              })
            }
          }}>Lock Resource Identity</Btn>
        </div>
        {p.resource_pack?.locked_at && <p style={{ fontSize: 12, color: '#0a7d2c', marginTop: 4 }}>Locked at: {p.resource_pack.locked_at}</p>}
      </Card>

      {/* B2 Idea */}
      <Card title="2. Idea">
        <Row label="Idea"><TextInput value={(p.raw_idea as any)?.text || ''} placeholder="show the bottle" disabled={p.idea_version > 0} onChange={(v) => post('/idea', { text: v, duration_seconds: 4, platform: 'tiktok', aspect_ratio: '9:16' })} /></Row>
      </Card>

      {/* B3 Brief */}
      <Card title="3. Creative Brief">
        <Row label="Objective"><TextInput value={(p.creative_brief as any)?.objective || ''} placeholder="present the bottle" disabled={p.brief_approval === 'approved'} onChange={(v) => post('/brief', { objective: v, target_audience: 'viewers', core_message: 'bottle', content_blocks: ['establish'] })} /></Row>
        <Btn warn disabled={p.brief_approval === 'approved'} onClick={() => post('/brief/approve', {})}>Approve Creative Brief</Btn>
        <span style={{ fontSize: 12, marginLeft: 8 }}>{p.brief_approval}</span>
      </Card>

      {/* B4 Scenes */}
      <Card title="4. Scene Plan">
        {(p.scene_plan?.scenes || []).map((sc: any, i: number) => (
          <div key={sc.scene_id} style={{ fontSize: 13, border: '1px solid #eee', padding: 8, marginBottom: 6 }}>
            Scene {i + 1}: {sc.title} · {sc.duration_seconds}s · {sc.objective} · {sc.camera_intention}
          </div>
        ))}
        <Btn warn disabled={p.scene_plan_approval === 'approved'} onClick={() => post('/scenes', { scenes: [{ title: 'Bottle on table', objective: 'present bottle', main_action: 'static, slow pan', camera_intention: 'front', duration_seconds: 4 }] }).then(() => post('/scenes/approve', {}))}>Save + Approve Scene Plan</Btn>
      </Card>

      {/* B5 Storyboard */}
      <Card title="5. Storyboard">
        <Row label="Frame prompt"><textarea value={frame.prompt} onChange={(e) => setFrame({ ...frame, prompt: e.target.value })} rows={2} /></Row>
        <Btn onClick={async () => {
          await post('/storyboard', { frames: [{ frame_id: 'frame_1', scene_id: 'scene_1', order: 1, label: frame.label, prompt: { positive_prompt: frame.prompt, aspect_ratio: '9:16' } }] })
          const r = await postRaw('/storyboard/generate', {})
          const j = r.data?.jobs?.[0]
          if (j) poll(j.job_id)
        }}>Generate Image (1x)</Btn>
        <Btn warn disabled={!p.storyboard?.frames?.some((f: any) => f.generated_asset_id) || p.storyboard?.approval_status === 'approved'} onClick={() => post('/storyboard/approve', {})}>Approve Storyboard</Btn>
        <div style={{ fontSize: 12 }}>
          approval: {p.storyboard?.approval_status}
          {p.storyboard?.frames?.map((f: any) => (
            <div key={f.frame_id}>{f.frame_id}: {f.generation_status}{f.generated_asset_id ? ' ✅' : ''}</div>
          ))}
        </div>
        {p.storyboard?.frames?.some((f: any) => f.generated_asset_id) && (
          <img src={imgPath('images/vfe2e_frame_1.png')} alt="frame" style={{ width: 160, border: '1px solid #ddd' }} />
        )}
      </Card>

      {/* B6/B7/B8 Video */}
      <Card title="6. Video">
        <Row label="Video prompt"><textarea value={video.prompt} onChange={(e) => setVideo({ ...video, prompt: e.target.value })} rows={2} /></Row>
        <Btn onClick={async () => {
          const r = await postRaw('/video', { scene_id: 'scene_1', prompt: video.prompt, duration_seconds: video.duration, aspect_ratio: '9:16' })
          const j = r.data?.job_id
          if (j) poll(j)
        }}>Generate Video (1x)</Btn>
        <div style={{ fontSize: 12 }}>
          {p.generated_scenes?.map((sc: any) => (
            <div key={sc.scene_id}>{sc.scene_id}: {sc.generation_status}{sc.generated_asset_id ? ' ✅' : ''}</div>
          ))}
        </div>
      </Card>

      {/* B9 Timeline */}
      <Card title="7. Timeline">
        <Btn onClick={async () => {
          await post('/timeline', { clips: [{ source_asset_id: 'scene_asset_scene_1', duration_seconds: 4 }] })
          const r = await postRaw('/timeline/render', {})
          const j = r.data?.job_id
          if (j) poll(j)
        }}>Build + Render Draft</Btn>
        <span style={{ fontSize: 12, marginLeft: 8 }}>draft: {p.draft_video_asset_id || 'pending'}</span>
        {p.draft_video_asset_id && <video src={imgPath('videos/draft_video.mp4')} controls style={{ width: 240, display: 'block', marginTop: 8 }} />}
      </Card>

      {/* TTS Voiceover */}
      <Card title="Voiceover (TTS)">
        <Row label="Voiceover text"><textarea value={tts.text} onChange={(e) => setTts({ ...tts, text: e.target.value })} rows={2} /></Row>
        <Row label="Style prompt"><textarea value={tts.style} onChange={(e) => setTts({ ...tts, style: e.target.value })} rows={2} /></Row>
        <div style={{ fontSize: 12, marginBottom: 8 }}>voice: Zephyr (configured)</div>
        <Btn onClick={async () => {
          const r = await postRaw('/tts', { text: tts.text, style_prompt: tts.style, voice: 'Zephyr' })
          if (r.status === 'error') setMsg({ text: r.message, ok: false })
          else setTtsResult({ wav: r.data.wav_path, voice: r.data.voice })
        }}>Generate Voiceover (1x)</Btn>
        <Btn disabled={!ttsResult} onClick={async () => {
          const r = await postRaw('/tts/mix', {})
          if (r.data?.output_path) { setMixed(r.data.output_path); setMsg({ text: 'mixed', ok: true }) }
        }}>Render with Voiceover</Btn>
        {ttsResult && <div style={{ fontSize: 12, marginTop: 6 }}>wav: {ttsResult.wav} ({ttsResult.voice})</div>}
        {ttsResult && <audio src={imgPath('audio/tts1_acceptance.wav')} controls style={{ marginTop: 6 }} />}
        {mixed && <video src={imgPath('videos/final_video_with_voiceover.mp4')} controls style={{ width: 240, display: 'block', marginTop: 6 }} />}
      </Card>

      {/* B10 Export */}
      <Card title="8. Final Review / Export">
        <Btn warn disabled={p.final_approval === 'approved'} onClick={() => post('/final/approve', {})}>Approve Final</Btn>
        <Btn disabled={p.final_approval !== 'approved'} onClick={async () => {
          const r = await postRaw('/final/export', {})
          const j = r.data?.job_id
          if (j) poll(j)
        }}>Export Final</Btn>
        <div style={{ fontSize: 12 }}>final: {p.final_approval} | status: {s}</div>
        {p.status === 'ready_to_publish' && <p style={{ color: '#0a7d2c' }}><b>✅ ready_to_publish</b></p>}
        {p.final_video_asset_id && <video src={imgPath('videos/final_video.mp4')} controls style={{ width: 240, display: 'block', marginTop: 8 }} />}
      </Card>

      {/* Publishing */}
      <Card title="9. Publish to TikTok">
        <div style={{ fontSize: 12, marginBottom: 8 }}>
          TikTok status: {pubStatus}
          {pubPostId ? ` | post: ${pubPostId}` : ''}
          {pubError ? ` | ${pubError}` : ''}
        </div>
        <Row label="Caption"><TextInput value={caption} placeholder="Video caption" onChange={(v) => setCaption(v)} /></Row>
        <Btn onClick={async () => {
          const r = await postRaw('/publish', { caption })
          if (r.status === 'error') setMsg({ text: r.message, ok: false })
          else setMsg({ text: `publish initiated: ${r.data.post_id}`, ok: true })
          loadPub()
        }}>Publish to TikTok</Btn>
        <Btn onClick={loadPub}>Refresh status</Btn>
      </Card>

      {busy && <p style={{ fontSize: 12, color: '#888' }}>working…</p>}
    </div>
  )
}

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <fieldset style={{ marginBottom: 16, border: '1px solid #ccc', borderRadius: 8, padding: 12 }}>
      <legend style={{ fontWeight: 700 }}>{title}</legend>
      {children}
    </fieldset>
  )
}
function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
      <label style={{ width: 120, fontSize: 13 }}>{label}</label>
      <div style={{ flex: 1 }}>{children}</div>
    </div>
  )
}
function TextInput({ value, placeholder, onChange, disabled }: { value: string; placeholder?: string; onChange: (v: string) => void; disabled?: boolean }) {
  const [draft, setDraft] = useState(value)
  useEffect(() => setDraft(value), [value])
  return (
    <input
      value={draft}
      placeholder={placeholder}
      disabled={disabled}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={() => { if (!disabled && draft !== value) onChange(draft) }}
      style={{ width: '100%' }}
    />
  )
}
function Btn({ children, onClick, warn, disabled }: { children: React.ReactNode; onClick: () => void; warn?: boolean; disabled?: boolean }) {
  return (
    <button onClick={onClick} disabled={disabled} style={{
      marginRight: 8, padding: '6px 12px', cursor: disabled ? 'not-allowed' : 'pointer',
      opacity: disabled ? 0.5 : 1,
      background: warn ? '#c62828' : '#1565c0', color: '#fff', border: 'none', borderRadius: 6,
    }}>{children}</button>
  )
}
