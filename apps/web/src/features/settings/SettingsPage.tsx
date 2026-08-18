import React, { useState } from 'react'
import { Settings as SettingsIcon, Database, Server, Key, Save, CheckCircle2 } from 'lucide-react'
import { Button } from '../../components/common/Button'

export const SettingsPage: React.FC = () => {
  const [settings, setSettings] = useState({
    dbPath: 'video_factory.sqlite (Hermes Data Root)',
    routerUrl: 'http://localhost:9000',
    routerApiKey: '••••••••••••••••',
    defaultTier: 'reason',
  })
  const [saved, setSaved] = useState(false)

  const handleSave = (e: React.FormEvent) => {
    e.preventDefault()
    setSaved(true)
    setTimeout(() => setSaved(false), 3000)
  }

  return (
    <div style={{ padding: '24px 32px', maxWidth: '800px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '20px', width: '100%' }}>
      <div>
        <h1 style={{ fontSize: '20px', fontWeight: 600, color: 'var(--text-primary)' }}>
          Platform Settings
        </h1>
        <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginTop: '2px' }}>
          Runtime configuration, storage paths, and AI model routing endpoints.
        </p>
      </div>

      {saved && (
        <div style={{ padding: '10px 14px', backgroundColor: 'var(--status-success-bg)', border: '1px solid var(--status-success-border)', borderRadius: 'var(--radius-sm)', color: 'var(--status-success)', display: 'flex', alignItems: 'center', gap: '8px', fontSize: '12px' }}>
          <CheckCircle2 size={14} />
          <span>Configuration saved successfully.</span>
        </div>
      )}

      <form onSubmit={handleSave} style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
        {/* Database & Storage */}
        <div style={{ padding: '20px', backgroundColor: 'var(--bg-panel)', border: '1px solid var(--border-default)', borderRadius: 'var(--radius-lg)', display: 'flex', flexDirection: 'column', gap: '14px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', borderBottom: '1px solid var(--border-subtle)', paddingBottom: '8px' }}>
            <Database size={16} color="var(--accent-primary)" />
            <h3 style={{ fontSize: '14px', fontWeight: 600, color: 'var(--text-primary)' }}>
              Canonical Database Layout
            </h3>
          </div>

          <div>
            <label style={{ display: 'block', fontSize: '12px', color: 'var(--text-muted)', marginBottom: '4px' }}>
              Video Factory SQLite Store
            </label>
            <input
              type="text"
              value={settings.dbPath}
              disabled
              style={{ width: '100%', opacity: 0.8 }}
            />
            <span style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '4px', display: 'block' }}>
              Managed automatically via <code>runtime_layout.py</code>.
            </span>
          </div>
        </div>

        {/* AI Model Routing */}
        <div style={{ padding: '20px', backgroundColor: 'var(--bg-panel)', border: '1px solid var(--border-default)', borderRadius: 'var(--radius-lg)', display: 'flex', flexDirection: 'column', gap: '14px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', borderBottom: '1px solid var(--border-subtle)', paddingBottom: '8px' }}>
            <Server size={16} color="var(--accent-primary)" />
            <h3 style={{ fontSize: '14px', fontWeight: 600, color: 'var(--text-primary)' }}>
              LLM Orchestrator & Multi-Modal Routing
            </h3>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '14px' }}>
            <div>
              <label style={{ display: 'block', fontSize: '12px', color: 'var(--text-muted)', marginBottom: '4px' }}>
                Router Endpoint
              </label>
              <input
                type="text"
                value={settings.routerUrl}
                onChange={(e) => setSettings({ ...settings, routerUrl: e.target.value })}
                style={{ width: '100%' }}
              />
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '12px', color: 'var(--text-muted)', marginBottom: '4px' }}>
                API Access Key
              </label>
              <input
                type="password"
                value={settings.routerApiKey}
                onChange={(e) => setSettings({ ...settings, routerApiKey: e.target.value })}
                style={{ width: '100%' }}
              />
            </div>
          </div>
        </div>

        <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
          <Button type="submit" variant="primary" size="md" icon={<Save size={14} />}>
            Save Configuration
          </Button>
        </div>
      </form>
    </div>
  )
}
