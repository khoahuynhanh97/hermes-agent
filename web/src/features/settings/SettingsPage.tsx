import { useState } from 'react'

export function SettingsPage() {
  const [settings, setSettings] = useState({
    dbPath: 'D:\\HermesData\\hermes.db',
    routerUrl: 'http://localhost:9000',
    routerApiKey: '••••••••••••••••',
    telegramToken: '••••••••••••••••••••••••',
    defaultTier: 'reason',
    autoSave: true,
    darkMode: true,
  })

  const handleSave = () => {
    alert('Settings saved! (Demo)')
  }

  return (
    <div>
      <h1>⚙️ Settings</h1>

      <div className="card">
        <h2>Database</h2>
        <div style={{ display: 'grid', gap: '1rem' }}>
          <div>
            <label style={{ display: 'block', marginBottom: '0.5rem', color: '#a1a1aa' }}>
              Database Path
            </label>
            <input
              type="text"
              value={settings.dbPath}
              onChange={(e) => setSettings({ ...settings, dbPath: e.target.value })}
            />
          </div>
        </div>
      </div>

      <div className="card">
        <h2>AI Router (9Router)</h2>
        <div style={{ display: 'grid', gap: '1rem' }}>
          <div>
            <label style={{ display: 'block', marginBottom: '0.5rem', color: '#a1a1aa' }}>
              Router URL
            </label>
            <input
              type="text"
              value={settings.routerUrl}
              onChange={(e) => setSettings({ ...settings, routerUrl: e.target.value })}
            />
          </div>
          <div>
            <label style={{ display: 'block', marginBottom: '0.5rem', color: '#a1a1aa' }}>
              API Key
            </label>
            <input
              type="password"
              value={settings.routerApiKey}
              onChange={(e) => setSettings({ ...settings, routerApiKey: e.target.value })}
            />
          </div>
        </div>
      </div>

      <div className="card">
        <h2>Telegram Bot</h2>
        <div style={{ display: 'grid', gap: '1rem' }}>
          <div>
            <label style={{ display: 'block', marginBottom: '0.5rem', color: '#a1a1aa' }}>
              Bot Token
            </label>
            <input
              type="password"
              value={settings.telegramToken}
              onChange={(e) => setSettings({ ...settings, telegramToken: e.target.value })}
            />
          </div>
        </div>
      </div>

      <div className="card">
        <h2>Preferences</h2>
        <div style={{ display: 'grid', gap: '1rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span>Default AI Tier</span>
            <select
              value={settings.defaultTier}
              onChange={(e) => setSettings({ ...settings, defaultTier: e.target.value })}
              style={{ width: 'auto' }}
            >
              <option value="fast">Fast</option>
              <option value="reason">Reason</option>
              <option value="vision">Vision</option>
              <option value="code">Code</option>
            </select>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span>Auto-save drafts</span>
            <input
              type="checkbox"
              checked={settings.autoSave}
              onChange={(e) => setSettings({ ...settings, autoSave: e.target.checked })}
            />
          </div>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span>Dark Mode</span>
            <input
              type="checkbox"
              checked={settings.darkMode}
              onChange={(e) => setSettings({ ...settings, darkMode: e.target.checked })}
            />
          </div>
        </div>
      </div>

      <div style={{ marginTop: '2rem' }}>
        <button onClick={handleSave} style={{ padding: '1rem 3rem' }}>
          Save Settings
        </button>
      </div>
    </div>
  )
}